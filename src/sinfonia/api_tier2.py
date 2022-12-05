#
# Sinfonia
#
# deploy helm charts to a cloudlet kubernetes cluster for edge-native applications
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from concurrent.futures import CancelledError
from uuid import UUID

from connexion import NoContent
from connexion.exceptions import ProblemException
from flask import current_app
from flask.views import MethodView

from .wireguard_key import WireguardKey


class DeployView(MethodView):
    def post(self, uuid, application_key):
        cluster = current_app.config["K8S_CLUSTER"]
        deployment = cluster.get(UUID(uuid), WireguardKey(application_key), create=True)

        try:
            deployment.deploy()
        except (CancelledError, TimeoutError) as e:
            raise ProblemException(400, "Error", f"Failed to deploy {e!r}")

        return [deployment.asdict()]

    def get(self, uuid, application_key):
        cluster = current_app.config["K8S_CLUSTER"]
        deployment = cluster.get(UUID(uuid), WireguardKey(application_key))
        if deployment is None:
            raise ProblemException(
                404, "Not Found", "Invalid Application UUID/Key combination"
            )

        return deployment.asdict()

    def delete(self, uuid, application_key):
        cluster = current_app.config["K8S_CLUSTER"]
        deployment = cluster.get(UUID(uuid), WireguardKey(application_key))
        if deployment is None:
            raise ProblemException(
                404, "Not Found", "Invalid Application UUID/Key combination"
            )

        deployment.expire()
        deployment.delete()
        return NoContent, 204
