#
# Sinfonia
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import logging
import socket
from pathlib import Path
from typing import Any

import click
import connexion
from attrs import define
from connexion.resolver import MethodViewResolver
from plumbum.colors import warn
from plumbum.commands.processes import ProcessExecutionError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import get_interface_ip
from yarl import URL
from zeroconf import ServiceInfo, Zeroconf

from .cluster import Cluster
from .deployment_repository import DeploymentRepository
from .jobs import scheduler, start_expire_deployments_job, start_reporting_job
from .openapi import load_spec


class Tier2DefaultConfig:
    RECIPES: str | Path | URL = "RECIPES"
    KUBECONFIG: str = ""
    KUBECONTEXT: str = ""
    PROMETHEUS: str = "http://kube-prometheus-stack-prometheus.monitoring:9090"
    TIER1_URLS: list[str] = []
    TIER2_URL: str | None = None

    # these are initialized by the tier2 app factory from the defined config
    # deployment_repository: DeploymentRepository | None = None
    # k8s_cluster : Cluster | None = None


def tier2_app_factory(**args: dict[str, Any]) -> connexion.FlaskApp:
    """Sinfonia Tier 2 API server"""
    app = connexion.FlaskApp(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.config.from_object(Tier2DefaultConfig)
    flask_app.config.from_envvar("SINFONIA_SETTINGS", silent=True)
    flask_app.config.from_prefixed_env(prefix="SINFONIA")

    cmdargs = {k.upper(): v for k, v in args.items() if v}
    print(cmdargs)
    flask_app.config.from_mapping(cmdargs)

    flask_app.config["deployment_repository"] = DeploymentRepository(
        flask_app.config["RECIPES"]
    )

    # connect to local kubernetes cluster
    try:
        cluster = Cluster.connect(
            flask_app.config["KUBECONFIG"], flask_app.config["KUBECONTEXT"]
        )
        cluster.prometheus_url = (
            URL(flask_app.config["PROMETHEUS"]) / "api" / "v1" / "query"
        )

        flask_app.config["k8s_cluster"] = cluster
    except (ProcessExecutionError, ValueError):
        logging.warn(warn | "Failed to connect to cloudlet kubernetes instance")

    # start background jobs to expire deployments and report to Tier1
    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_deployments_job()

    if flask_app.config["TIER1_URLS"] and flask_app.config["TIER2_URL"] is not None:
        logging.info("Reporting cloudlet status to Tier1 endpoints")
        start_reporting_job()

    # handle running behind reverse proxy (should this be made configurable?)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)

    # add Tier1 APIs
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier2.yaml"),
        resolver=MethodViewResolver("sinfonia.api_tier2"),
        validate_responses=True,
    )

    @app.route("/")
    def index():
        return ""

    return app


@define
class ZeroconfMDNS:
    """Wrapper helping with zeroconf service registration"""

    zeroconf: Zeroconf | None = None

    def announce(self, port: int) -> None:
        """Try to announce our service on IPv4 and IPv6 on all interfaces"""
        if self.zeroconf is not None:
            self.withdraw()

        # werkzeug uses this function to figure out the ip address of the interface
        # that handles the default route. This should work as long as we don't
        # happen to have a secondary interface on the 10.0.0.0/8 network, I think.
        # either way, this seems to be about the best we can do for now because
        # when we just give a list of all known local addresses, it seems like
        # only the last IPv4 and IPv6 addresses end up being resolvable, and
        # these tend to be local-only docker or kvm network addresses on my system.
        address = get_interface_ip(socket.AF_INET)

        info = ServiceInfo(
            "_sinfonia._tcp.local.",
            "cloudlet._sinfonia._tcp.local.",
            parsed_addresses=[address],
            port=port,
            properties=dict(path="/"),
        )
        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(info, allow_name_change=True)

    def withdraw(self) -> None:
        """Withdraw service registration"""
        if self.zeroconf is not None:
            self.zeroconf.unregister_all_services()
            self.zeroconf.close()
            self.zeroconf = None


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option()
@click.option(
    "-p",
    "--port",
    type=int,
    default=5000,
    help="Port to listen for requests",
    show_default=True,
)
@click.option(
    "--recipes",
    type=str,
    help="Location of Sinfonia deployment recipes (directory or url)",
)
@click.option(
    "--kubeconfig",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to kubeconfig file",
)
@click.option("--kubecontext", type=str, help="Name of kubeconfig context to use")
@click.option(
    "--prometheus",
    type=str,
    help="Prometheus endpoint",
)
@click.option(
    "tier1_urls",
    "--tier1-url",
    type=str,
    help="Base URL of Tier 1 instance to report to (may be repeated)",
    multiple=True,
)
@click.option(
    "--tier2-url",
    type=str,
    help="Base URL of this Tier 2 instance",
)
@click.option(
    "enable_zeroconf",
    "--zeroconf/--no-zeroconf",
    default=False,
    help="Announce cloudlet on local network(s) with zeroconf mdns",
)
def main(
    port,
    recipes,
    kubeconfig,
    kubecontext,
    prometheus,
    tier1_urls,
    tier2_url,
    enable_zeroconf,
):
    """Run with flask builtin server (development)"""
    app = tier2_app_factory(
        recipes=recipes,
        kubeconfig=kubeconfig,
        kubecontext=kubecontext,
        prometheus=prometheus,
        tier1_urls=tier1_urls,
        tier2_url=tier2_url,
    )

    # run application, optionally announcing availability with MDNS
    zeroconf = ZeroconfMDNS()
    if enable_zeroconf:
        zeroconf.announce(port)
    try:
        app.run(port=port)
    except KeyboardInterrupt:
        pass
    finally:
        zeroconf.withdraw()
