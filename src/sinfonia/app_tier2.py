#
# Sinfonia
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import socket
from pathlib import Path
from uuid import uuid4

import connexion
import typer
from attrs import define
from connexion.resolver import MethodViewResolver
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import get_interface_ip
from yarl import URL
from zeroconf import ServiceInfo, Zeroconf

from .app_common import (
    OptionalBool,
    OptionalPath,
    OptionalStr,
    StrList,
    port_option,
    recipes_option,
    version_option,
)
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

    # These are initialized by the wsgi app factory from the config
    # UUID: UUID
    # deployment_repository: DeploymentRepository | None = None     # RECIPES
    # K8S_CLUSTER : Cluster | None = None   # KUBECONFIG KUBECONTEXT PROMETHEUS


def tier2_app_factory(**args) -> connexion.FlaskApp:
    """Sinfonia Tier 2 API server"""
    app = connexion.FlaskApp(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.config.from_object(Tier2DefaultConfig)
    flask_app.config.from_envvar("SINFONIA_SETTINGS", silent=True)
    flask_app.config.from_prefixed_env(prefix="SINFONIA")

    cmdargs = {k.upper(): v for k, v in args.items() if v}
    flask_app.config.from_mapping(cmdargs)

    flask_app.config["UUID"] = uuid4()
    flask_app.config["deployment_repository"] = DeploymentRepository(
        flask_app.config["RECIPES"]
    )

    # connect to local kubernetes cluster
    cluster = Cluster.connect(
        flask_app.config.get("KUBECONFIG"), flask_app.config.get("KUBECONTEXT")
    )
    cluster.prometheus_url = (
        URL(flask_app.config["PROMETHEUS"]) / "api" / "v1" / "query"
    )
    flask_app.config["K8S_CLUSTER"] = cluster

    # start background jobs to expire deployments and report to Tier1
    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_deployments_job()
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


cli = typer.Typer()


@cli.command()
def tier2_server(
    version: OptionalBool = version_option,
    port: int = port_option,
    recipes: OptionalStr = recipes_option,
    kubeconfig: OptionalPath = typer.Option(
        None,
        help="Path to kubeconfig file",
        show_default=False,
        exists=True,
        dir_okay=False,
        resolve_path=True,
        rich_help_panel="Kubernetes cluster config",
    ),
    kubecontext: str = typer.Option(
        "",
        help="Name of kubeconfig context to use",
        show_default=False,
        rich_help_panel="Kubernetes cluster config",
    ),
    prometheus: OptionalStr = typer.Option(
        None,
        metavar="URL",
        help="Prometheus endpoint",
        show_default=False,
        rich_help_panel="Kubernetes cluster config",
    ),
    tier1_urls: StrList = typer.Option(
        [],
        "--tier1-url",
        metavar="URL",
        help="Base URL of Tier 1 instances to report to (may be repeated)",
        rich_help_panel="Sinfonia Tier1 reporting",
    ),
    tier2_url: OptionalStr = typer.Option(
        None,
        metavar="URL",
        help="Base URL of this Tier 2 instance",
        show_default=False,
        rich_help_panel="Sinfonia Tier1 reporting",
    ),
    zeroconf: bool = typer.Option(
        False,
        help="Announce cloudlet on local network(s) with zeroconf mdns",
    ),
):
    """Run Sinfonia TIer2 with Flask's builtin server (for development)"""
    app = tier2_app_factory(
        recipes=recipes,
        kubeconfig=kubeconfig,
        kubecontext=kubecontext,
        prometheus=prometheus,
        tier1_urls=tier1_urls,
        tier2_url=tier2_url,
    )

    # run application, optionally announcing availability with MDNS
    zeroconf_mdns = ZeroconfMDNS()
    if zeroconf:
        zeroconf_mdns.announce(port)
    try:
        app.run(port=port)
    except KeyboardInterrupt:
        pass
    finally:
        zeroconf_mdns.withdraw()
