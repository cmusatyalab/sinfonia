#
# Sinfonia
#
# deploy helm charts to a cloudlet kubernetes cluster for edge-native applications
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

import logging
from pathlib import Path
from typing import Any, Dict

import click
import connexion
import prance
from connexion.resolver import MethodViewResolver
from flask_executor import Executor
from geolite2 import geolite2
from importlib_metadata import entry_points
from plumbum.colors import warn
from plumbum.commands.processes import ProcessExecutionError
from werkzeug.middleware.proxy_fix import ProxyFix
from yarl import URL

from .cloudlets import load as cloudlets_load
from .cluster import Cluster
from .deployment_repository import DeploymentRepository
from .jobs import (
    scheduler,
    start_expire_cloudlets_job,
    start_expire_deployments_job,
    start_reporting_job,
)
from .zeroconf import ZeroconfMDNS

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "auto_envvar_prefix": "SINFONIA",
}


def load_spec(specfile: Path) -> Dict[str, Any]:
    parser = prance.ResolvingParser(
        str(specfile.absolute()),
        lazy=True,
        strict=True,
        backend="openapi-spec-validator",
    )
    parser.parse()
    return parser.specification


def list_matchers(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    matchers = [ep.name for ep in entry_points(group="sinfonia.tier1_matchers")]

    click.echo("Available tier1 match functions:")
    for matcher in sorted(matchers):
        click.echo(f"\t{matcher}")
    ctx.exit()


@click.command(context_settings=CONTEXT_SETTINGS)
@click.version_option()
@click.option(
    "-c",
    "--cloudlets",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing known Tier2 cloudlets",
)
@click.option(
    "--recipes",
    type=str,
    default="RECIPES",
    help="Location of Sinfonia deployment recipes (directory or url)",
    show_default=True,
    show_envvar=True,
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=5000,
    help="Port to listen for requests",
    show_default=True,
    show_envvar=True,
)
@click.option(
    "--list-matchers",
    is_flag=True,
    callback=list_matchers,
    expose_value=False,
    is_eager=True,
    help="Show available matchers",
)
@click.option(
    "matchers",
    "-m",
    "--matcher",
    type=str,
    multiple=True,
    default=["network", "location", "random"],
    help="Select Tier1 best match functions",
    show_default=True,
    show_envvar=True,
)
def tier1(cloudlets, recipes, port, matchers):
    """Run Sinfonia Tier 1 API server"""
    # load pluggable functions to select Tier2 cloudlets
    try:
        tier1_matchers = {
            ep.name: ep for ep in entry_points(group="sinfonia.tier1_matchers")
        }
        match_functions = [tier1_matchers[matcher].load() for matcher in matchers]
    except KeyError as e:
        raise click.UsageError(f"Unknown matcher {e.args[0]} selected")

    app = connexion.App(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)
    flask_app.config["EXECUTOR"] = Executor(flask_app)
    flask_app.config["GEOLITE2_READER"] = geolite2.reader()
    flask_app.config["MATCHERS"] = match_functions
    flask_app.config["RECIPES"] = DeploymentRepository(recipes)

    if cloudlets is not None:
        with flask_app.app_context():
            with open(cloudlets) as stream:
                CLOUDLETS = cloudlets_load(stream)
    else:
        CLOUDLETS = []
    flask_app.config["CLOUDLETS"] = {cloudlet.uuid: cloudlet for cloudlet in CLOUDLETS}

    # start background job to expire Tier2 cloudlets that are no longer reporting
    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_cloudlets_job()

    # add APIs
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier1.yaml"),
        resolver=MethodViewResolver("sinfonia.api_tier1"),
        validate_responses=True,
    )

    @app.app.route("/")
    def index():
        return ""

    app.run(port=port)


@click.command(context_settings=CONTEXT_SETTINGS)
@click.version_option()
@click.option(
    "--recipes",
    type=str,
    default="RECIPES",
    help="Location of Sinfonia deployment recipes (directory or url)",
    show_default=True,
    show_envvar=True,
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
    default="http://kube-prometheus-stack-prometheus.monitoring:9090",
    help="Prometheus endpoint",
)
@click.option(
    "tier1_urls",
    "--tier1-url",
    type=str,
    help="Base URL of Tier 1 instance to report to (may be repeated)",
    show_envvar=True,
    multiple=True,
    default=[],
)
@click.option(
    "--tier2-url",
    type=str,
    help="Base URL of this Tier 2 instance",
    show_envvar=True,
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=5000,
    help="Port to listen for requests",
    show_default=True,
    show_envvar=True,
)
@click.option(
    "enable_zeroconf",
    "--zeroconf/--no-zeroconf",
    default=False,
    help="Announce cloudlet on local network(s) with zeroconf mdns",
)
def tier2(
    recipes,
    kubeconfig,
    kubecontext,
    prometheus,
    tier1_urls,
    tier2_url,
    port,
    enable_zeroconf,
):
    """Run Sinfonia Tier 2 API server"""

    app = connexion.App(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)
    flask_app.config["RECIPES"] = DeploymentRepository(recipes)
    flask_app.config["TIER1_URLS"] = tier1_urls
    flask_app.config["TIER2_URL"] = tier2_url

    # connect to local kubernetes cluster
    try:
        cluster = Cluster.connect(kubeconfig or "", kubecontext or "")
        if prometheus is not None:
            cluster.prometheus_url = URL(prometheus) / "api" / "v1" / "query"

        flask_app.config["K8S_CLUSTER"] = cluster
    except (ProcessExecutionError, ValueError):
        logging.warn(warn | "Failed to connect to cloudlet kubernetes instance")

    # start background jobs to cleanup expired/unused deployments and report
    # availability and metrics to Tier1 instances
    scheduler.init_app(app.app)
    scheduler.start()

    start_expire_deployments_job()

    if len(tier1_urls) != 0 and tier2_url is not None:
        logging.info("Reporting cloudlet status to Tier1 endpoints")
        start_reporting_job()

    # add APIs
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier2.yaml"),
        resolver=MethodViewResolver("sinfonia.api_tier2"),
        validate_responses=True,
    )

    @app.app.route("/")
    def index():
        return ""

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
