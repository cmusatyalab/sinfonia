#
# Sinfonia
#
# proxy requests to a nearby cloudlet
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

import logging
from ipaddress import ip_address
from itertools import chain, filterfalse, islice, zip_longest
from typing import Optional
from uuid import UUID

from connexion import NoContent
from connexion.exceptions import ProblemException
from flask import current_app, request
from flask.views import MethodView

from . import cloudlets
from .wireguard_key import WireguardKey

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# don't try to deploy to more than MAX_RESULTS cloudlets at a time
MAX_RESULTS = 3


class DeployView(MethodView):
    def post(self, uuid, application_key, results=1):
        uuid = UUID(uuid)
        application_key = WireguardKey(application_key)

        # set number of returned results between 1 and MAX_RESULTS
        max_results = max(1, min(results, MAX_RESULTS))

        # extract header parameters and add some extra validation
        try:
            client_address: Optional[str] = request.headers["X-ClientIP"]
            assert client_address is not None
            ip_address(client_address)
        except (KeyError, AssertionError, ValueError):
            client_address = request.remote_addr

        client_location = request.headers.get("X-Location", None)
        if client_location is not None and (
            float(client_location[0]) < -90.0
            or float(client_location[0]) > 90.0
            or float(client_location[1]) < -180.0
            or float(client_location[1]) > 180.0
        ):
            client_location = None

        CLOUDLETS = current_app.config["CLOUDLETS"]
        by_nearest = cloudlets.find(CLOUDLETS, client_address, client_location)

        # fire off deployment requests
        requests = [
            cloudlet.deploy_async(uuid, application_key)
            for cloudlet in islice(by_nearest, max_results)
        ]

        # gather the results,
        # - interleave results from cloudlets in case any returned more than requested.
        # - recombine into a single list, drop failed results and limit to max_results.
        results = list(
            islice(
                filterfalse(
                    None, chain(zip_longest(request.result() for request in requests))
                ),
                max_results,
            )
        )

        # all requests failed?
        if not results:
            raise ProblemException(500, "Error", "Something went wrong")

        return results

    def get(self, uuid, application_key):
        raise ProblemException(500, "Error", "Not implemented")


class CloudletsView(MethodView):
    def post(self):
        body = request.json
        if not isinstance(body, dict) or "uuid" not in body:
            return "Bad Request, missing UUID", 400

        cloudlet = cloudlets.Cloudlet.new_from_api(body)
        CLOUDLETS = current_app.config["CLOUDLETS"]
        CLOUDLETS[cloudlet.uuid] = cloudlet
        return NoContent, 204

    def search(self):
        CLOUDLETS = current_app.config["CLOUDLETS"]
        return [cloudlet.summary() for cloudlet in CLOUDLETS.values()]
