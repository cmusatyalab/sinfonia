#
# Sinfonia
#
# deploy helm charts to a cloudlet kubernetes cluster for edge-native applications
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

import ipaddress
import os
import string
import sys
from contextlib import contextmanager
from typing import Any, Dict, List, Sequence
from uuid import UUID

import importlib_resources
import randomname
import requests
import typer
import wgconfig
import wgconfig.wgexec
import yaml
from openapi_core import create_spec
from openapi_core.contrib.requests import (
    RequestsOpenAPIRequest,
    RequestsOpenAPIResponse,
)
from openapi_core.validation.response.validators import ResponseValidator
from plumbum import FG, local
from plumbum.cmd import echo, ip, mkdir, rm, rmdir, sudo, tee
from requests.exceptions import ConnectionError, HTTPError
from xdg import xdg_cache_home
from yarl import URL
from zeroconf import Zeroconf

from .wireguard_key import WireguardKey

app = typer.Typer()

wg = local.get("wg", "echo")


def load_application_keys(application_uuid: UUID) -> Dict[str, str]:
    """Return a new public/private for the application

    Reuse a cached copy from ~/.cache/sinfonia/<application-uuid> if it exists.
    """
    cache_file = xdg_cache_home() / "sinfonia" / str(application_uuid)
    if cache_file.exists():
        return yaml.safe_load(cache_file.read_text())

    keys = {}
    keys["private_key"], keys["public_key"] = wgconfig.wgexec.generate_keypair()

    cache_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with cache_file.open("w") as fh:
        yaml.dump(keys, fh)

    return keys


class WireguardKeyFormatter:
    """For validating wireguard keys in the server response"""

    def validate(self, value: str) -> bool:
        try:
            WireguardKey(value)
            return True
        except ValueError:
            return False

    def unmarshal(self, value):
        return value


def deploy_backend(deployment_url: URL) -> Sequence[Dict[str, Any]]:
    """Request a backend (re)deployment from the orchestrator"""
    # fire off deployment request
    response = requests.post(str(deployment_url))
    response.raise_for_status()

    # load openapi specification to validate the response
    spec_dict = yaml.safe_load(
        importlib_resources.files("sinfonia.openapi")
        .joinpath("sinfonia_tier2.yaml")
        .read_text()
    )
    spec = create_spec(spec_dict)
    custom_formatters = {
        "wireguard_public_key": WireguardKeyFormatter(),
    }

    # validate the response
    openapi_request = RequestsOpenAPIRequest(response.request)
    openapi_response = RequestsOpenAPIResponse(response)

    validator = ResponseValidator(spec, custom_formatters=custom_formatters)
    result = validator.validate(openapi_request, openapi_response)
    result.raise_for_errors()

    return result.data


def create_wireguard_config(interface_name, tunnel_config):
    """Create wireguard tunnel configuration"""
    wireguard_config = wgconfig.WGConfig(f"./{interface_name}.conf")

    # [Interface]
    wireguard_config.add_attr(None, "PrivateKey", tunnel_config["privateKey"])

    peer_public_key = tunnel_config["publicKey"]
    wireguard_config.add_peer(peer_public_key)
    allowed_ips = ", ".join(tunnel_config["allowedIPs"])
    wireguard_config.add_attr(peer_public_key, "AllowedIPs", allowed_ips)
    wireguard_config.add_attr(peer_public_key, "Endpoint", tunnel_config["endpoint"])

    wireguard_config.write_file()


def is_ipaddress(entry):
    try:
        return ipaddress.ip_address(entry) is not None
    except ValueError:
        return False


@contextmanager
def network_namespace(namespace, tunnel_config):
    dns_config = tunnel_config["dns"]
    name_servers = [
        f"nameserver {entry}" for entry in dns_config if is_ipaddress(entry)
    ]
    search_domains = [entry for entry in dns_config if not is_ipaddress(entry)]

    resolvconf_config = "\n".join(name_servers)
    if search_domains:
        resolvconf_config += " ".join(["\nsearch"] + search_domains)
    resolvconf_config += "\noptions ndots:5"

    resolvconf = local.path(f"/etc/netns/{namespace}/resolv.conf")
    try:
        with local.as_root():
            # resolvconf.parent.mkdir()
            # resolvconf.write(resolvconf_config)
            mkdir("-p", resolvconf.parent)
            (echo[resolvconf_config] | tee[resolvconf])()

            ip("netns", "add", namespace)

        yield ip["netns", "exec", namespace]

    finally:
        with local.as_root():
            ip("netns", "delete", namespace)

            rm("-f", resolvconf)
            rmdir(resolvconf.parent)


config_option = typer.Option(False, help="Only create wireguard config")
debug_option = typer.Option(False, help="Print logs for debugging")
zeroconf_option = typer.Option(False, help="Try to discover local Tier2 with MDNS")


@app.command()
def main(
    tier1_url: str,
    application_uuid: UUID,
    application: List[str],
    config_only: bool = config_option,
    debug: bool = debug_option,
    zeroconf: bool = zeroconf_option,
) -> None:
    application_keys = load_application_keys(application_uuid)

    if zeroconf:
        zc = Zeroconf()
        info = zc.get_service_info(
            "_sinfonia._tcp.local.", "cloudlet._sinfonia._tcp.local."
        )
        if info is not None:
            addresses = info.parsed_addresses()
            tier1_url = f"http://{addresses[0]}:{info.port}"

    deployment_key = WireguardKey(application_keys["public_key"])
    deployment_url = (
        URL(tier1_url)
        / "api/v1/deploy"
        / str(application_uuid)
        / deployment_key.urlsafe
    )

    if debug:
        typer.echo(f"deployment_url: {deployment_url}")

    try:
        typer.echo("Deploying... ", nl=False)
        deployments = deploy_backend(deployment_url)
        typer.echo("done")
    except ConnectionError:
        typer.echo("failed to connect to sinfonia-tier1/-tier2")
        sys.exit(1)
    except HTTPError as e:
        typer.echo(f'failed to deploy backend: "{e.response.text}"')
        sys.exit(1)

    deployment_data = deployments[0]
    deployment_name = deployment_data.get("DeploymentName", "")
    NS = "".join(
        c for c in deployment_name.lower() if c in string.ascii_lowercase
    ) or randomname.get_name(sep="")
    WG = f"wg-{NS}"[:15]

    tunnel_config = deployment_data["TunnelConfig"]
    IPADDRS = map(ipaddress.ip_interface, tunnel_config["address"])

    # inject our private key
    tunnel_config["privateKey"] = application_keys["private_key"]

    create_wireguard_config(WG, tunnel_config)

    if config_only:
        sys.exit(0)

    with network_namespace(NS, tunnel_config) as netns_exec:
        with local.as_root():
            ip("link", "add", WG, "type", "wireguard")
            ip("link", "set", WG, "netns", NS)

            netns_exec(wg, "setconf", WG, f"{WG}.conf")
            for IPADDR in IPADDRS:
                netns_exec(ip, "addr", "add", str(IPADDR), "dev", WG)
            netns_exec(ip, "link", "set", WG, "up")
            netns_exec(ip, "route", "add", "default", "dev", WG)

        uid, gid = os.getuid(), os.getgid()
        (
            sudo[
                "-E",
                netns_exec,
                "sudo",
                "-E",
                "-u",
                f"#{uid}",
                "-g",
                f"#{gid}",
            ].bound_command(*application)
            & FG(retcode=None)
        )
