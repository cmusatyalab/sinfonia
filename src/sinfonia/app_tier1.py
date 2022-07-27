#
# Sinfonia
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import click
import connexion
from connexion.resolver import MethodViewResolver
from flask_executor import Executor
from geolite2 import geolite2
from importlib_metadata import entry_points
from werkzeug.middleware.proxy_fix import ProxyFix
from yarl import URL

from .cloudlets import Cloudlet
from .cloudlets import load as cloudlets_load
from .deployment_repository import DeploymentRepository
from .jobs import scheduler, start_expire_cloudlets_job
from .matchers import Tier1MatchFunction
from .openapi import load_spec


class Tier1DefaultConfig:
    CLOUDLETS: str | Path | None = None
    RECIPES: str | Path | URL = "RECIPES"
    MATCHERS: list[str] = ["network", "location", "random"]

    # these are initialized by the tier1 app factory from the defined config
    cloudlets: dict[UUID, Cloudlet] = {}
    deployment_repository: DeploymentRepository | None = None
    match_functions: list[Tier1MatchFunction] = []


def load_cloudlets_conf(cloudlets_conf: str | Path | None) -> dict[UUID, Cloudlet]:
    """read cloudlets.yaml configuration file to preseed Tier2 cloudlets

    this depends on flask_app.config["geolite2_reader"]
    """
    if cloudlets_conf is None:
        return {}

    with Path(cloudlets_conf).open() as stream:
        cloudlets = cloudlets_load(stream)

    return {cloudlet.uuid: cloudlet for cloudlet in cloudlets}


def list_match_functions(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    matchers = [ep.name for ep in entry_points(group="sinfonia.tier1_matchers")]

    click.echo("Available tier1 match functions:")
    for matcher in sorted(matchers):
        click.echo(f"\t{matcher}")
    ctx.exit()


def load_match_functions(matchers: list[str]) -> list[Tier1MatchFunction]:
    """load pluggable functions to select Tier2 candidates"""
    try:
        tier1_matchers = {
            ep.name: ep for ep in entry_points(group="sinfonia.tier1_matchers")
        }
        match_functions = [tier1_matchers[matcher].load() for matcher in matchers]
        logging.info(f"Loaded match functions {matchers}")
    except KeyError as e:
        sys.exit(f"Unknown matcher {e.args[0]} selected")
    return match_functions


def tier1_app_factory(**args: dict[str, Any]) -> connexion.FlaskApp:
    """Sinfonia Tier 1 API server"""
    app = connexion.FlaskApp(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.config.from_object(Tier1DefaultConfig)
    flask_app.config.from_envvar("SINFONIA_SETTINGS", silent=True)
    flask_app.config.from_prefixed_env(prefix="SINFONIA")

    cmdargs = {k.upper(): v for k, v in args.items() if v}
    flask_app.config.from_mapping(cmdargs)

    flask_app.config["executor"] = Executor(flask_app)
    flask_app.config["geolite2_reader"] = geolite2.reader()

    flask_app.config["deployment_repository"] = DeploymentRepository(
        flask_app.config["RECIPES"]
    )
    with flask_app.app_context():
        flask_app.config["cloudlets"] = load_cloudlets_conf(
            flask_app.config.get("CLOUDLETS")
        )
    flask_app.config["match_functions"] = load_match_functions(
        flask_app.config["MATCHERS"]
    )

    # start background job to expire Tier2 cloudlets that are no longer reporting
    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_cloudlets_job()

    # handle running behind reverse proxy (should this be made configurable?)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)

    # add Tier1 APIs
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier1.yaml"),
        resolver=MethodViewResolver("sinfonia.api_tier1"),
        validate_responses=True,
    )

    @app.route("/")
    def index():
        return ""

    return app


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
    "-c",
    "--cloudlets",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing known Tier2 cloudlets",
)
@click.option(
    "--recipes",
    type=str,
    help="Location of Sinfonia deployment recipes (directory or url)",
)
@click.option(
    "matchers",
    "-m",
    "--matcher",
    type=str,
    multiple=True,
    help="Select Tier1 best match functions (multiple) [network, location, random]",
)
@click.option(
    "--list-matchers",
    is_flag=True,
    callback=list_match_functions,
    expose_value=False,
    is_eager=True,
    help="Show available matchers",
)
def main(port, cloudlets, recipes, matchers):
    """Run with flask builtin server (development)"""
    app = tier1_app_factory(cloudlets=cloudlets, recipes=recipes, matchers=matchers)
    app.run(port=port)
