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
import pendulum
import prance
from connexion.resolver import MethodViewResolver
from flask_executor import Executor
from geolite2 import geolite2
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


@click.command(context_settings=CONTEXT_SETTINGS)
@click.version_option()
@click.option(
    "-c",
    "--cloudlets",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing known cloudlets",
)
@click.option(
    "--scores",
    type=str,
    default="SCORES",
    help="Location of Sinfonia deployment scores (directory or url)",
    show_default=True,
    show_envvar=True,
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=5000,
    help="Port to listen for requests",
)
def tier1(cloudlets, scores, port):
    """Run Sinfonia Tier 1 API server"""
    # add APIs
    app = connexion.App(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)
    flask_app.config["EXECUTOR"] = Executor(flask_app)
    flask_app.config["GEOLITE2_READER"] = geolite2.reader()
    flask_app.config["SCORES"] = DeploymentRepository(scores)

    if cloudlets is not None:
        with flask_app.app_context():
            with open(cloudlets) as stream:
                CLOUDLETS = cloudlets_load(stream)
    else:
        CLOUDLETS = []
    flask_app.config["CLOUDLETS"] = {cloudlet.uuid: cloudlet for cloudlet in CLOUDLETS}

    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_cloudlets_job()

    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier1.yaml"),
        resolver=MethodViewResolver("sinfonia.api_tier1"),
        validate_responses=True,
    )

    @app.app.route("/")
    def index():
        return ""

    app.run(port=port)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option()
@click.option(
    "--scores",
    type=str,
    default="SCORES",
    help="Location of Sinfonia deployment scores (directory or url)",
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
    "--tier1-url",
    type=str,
    help="Base URL of Tier 1 instance to report to",
    show_envvar=True,
)
@click.option(
    "--tier2-url",
    type=str,
    help="Base URL of this Tier 2 instance",
    show_envvar=True,
)
@click.pass_context
def tier2(ctx, scores, kubeconfig, kubecontext, prometheus, tier1_url, tier2_url):
    ctx.obj = connexion.App(__name__, specification_dir="openapi/")

    flask_app = ctx.obj.app
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)
    flask_app.config["SCORES"] = DeploymentRepository(scores)
    flask_app.config["TIER1_URL"] = tier1_url
    flask_app.config["TIER2_URL"] = tier2_url

    try:
        cluster = Cluster.connect(kubeconfig or "", kubecontext or "")
        if prometheus is not None:
            cluster.prometheus_url = URL(prometheus) / "api" / "v1" / "query"

        flask_app.config["K8S_CLUSTER"] = cluster
    except (ProcessExecutionError, ValueError):
        logging.warn(warn | "Failed to connect to cloudlet kubernetes instance")


@tier2.command()
@click.option(
    "-p",
    "--port",
    type=int,
    default=5000,
    help="Port to listen for requests",
)
@click.pass_obj
def serve(app, port):
    """Run Sinfonia Tier 2 API server"""
    # add APIs
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier2.yaml"),
        resolver=MethodViewResolver("sinfonia.api_tier2"),
        validate_responses=True,
    )

    @app.app.route("/")
    def index():
        return ""

    scheduler.init_app(app.app)
    scheduler.start()

    start_expire_deployments_job()

    tier1_url = app.app.config["TIER1_URL"]
    tier2_url = app.app.config["TIER2_URL"]
    if tier1_url is not None and tier2_url is not None:
        logging.info(f"Reporting cloudlet status to {tier1_url}")
        start_reporting_job()

    app.run(port=port)


@tier2.command()
@click.option(
    "-v/-q",
    "--verbose/--quiet",
    default=True,
    help="Log message verbosity",
)
@click.option(
    "--redeploy",
    default=False,
    help="Redeploy non-expired deployments",
)
@click.pass_obj
def sync(app, verbose, redeploy):
    """Expire and delete stale deployments."""
    cluster = app.app.config["K8S_CLUSTER"]
    cutoff = pendulum.now().subtract(minutes=5)

    with app.app.app_context():
        active_peers = cluster.get_active_peers(cutoff)

        for deployment in cluster.deployments():
            if (
                deployment.created < cutoff
                and deployment.client_public_key not in active_peers
            ):
                if verbose:
                    click.echo(f"Expiring {deployment.name}")
                deployment.expire()
            elif redeploy:
                if verbose:
                    click.echo(f"Redeploying {deployment.name}")
                deployment.helm_install()
