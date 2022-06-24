#
# Sinfonia
#
# run periodic tasks
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

import logging

import pendulum
import requests
from flask_apscheduler import APScheduler
from requests.exceptions import RequestException
from yarl import URL

scheduler = APScheduler()


def expire_cloudlets():
    CLOUDLETS = scheduler.app.config["CLOUDLETS"]

    expiration = pendulum.now().subtract(minutes=5)

    for cloudlet in CLOUDLETS.values():
        if cloudlet.last_update is not None and cloudlet.last_update < expiration:
            logging.info(f"Removing stale {cloudlet}")
            del CLOUDLETS[cloudlet.uuid]


def start_expire_cloudlets_job():
    scheduler.add_job(
        func=expire_cloudlets,
        trigger="interval",
        seconds=60,
        max_instances=1,
        coalesce=True,
        id="expire_cloudlets",
        replace_existing=True,
    )


def expire_deployments():
    cluster = scheduler.app.config["K8S_CLUSTER"]
    cluster.expire_inactive_deployments()


def start_expire_deployments_job():
    scheduler.add_job(
        func=expire_deployments,
        trigger="interval",
        seconds=60,
        max_instances=1,
        coalesce=True,
        id="expire_deployments",
        replace_existing=True,
    )


def report_to_tier1():
    config = scheduler.app.config
    tier1_endpoint = URL(config["TIER1_URL"]) / "api/v1/cloudlets/"
    tier2_endpoint = URL(config["TIER2_URL"]) / "api/v1/deploy"

    cluster = scheduler.app.config["K8S_CLUSTER"]
    resources = cluster.get_resources()

    logging.info("Got %s", str(resources))

    try:
        requests.post(
            str(tier1_endpoint),
            json={
                "uuid": str(cluster.uuid),
                "endpoint": str(tier2_endpoint),
                "resources": resources,
            },
        )
    except RequestException:
        logging.warn(f"Failed to report to {tier1_endpoint}")


def start_reporting_job():
    scheduler.add_job(
        func=report_to_tier1,
        trigger="interval",
        seconds=15,
        max_instances=1,
        coalesce=True,
        id="report_to_tier1",
        replace_existing=True,
    )
