#
# Sinfonia
#
# deploy helm charts to a cloudlet kubernetes cluster for edge-native applications
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, Callable, cast
from uuid import UUID

import pendulum
import randomname
import yaml
from attrs import define, field
from plumbum import TF
from wireguard_tools import WireguardKey

from .deployment_recipe import DeploymentRecipe

if TYPE_CHECKING:
    from .cluster import Cluster
else:
    Cluster = object

CLIENT_NETWORK = ip_network("10.5.0.0/16")


def check_in_network(
    network: IPv4Network | IPv6Network,
) -> Callable[[Any, Any, IPv4Address | IPv6Address], None]:
    """Check if the address is in the client network"""

    def _check(_self: Any, _attribute: Any, value: IPv4Address | IPv6Address) -> None:
        if value not in network:
            raise ValueError

    return _check


def parse_date(value: str | pendulum.DateTime) -> pendulum.DateTime:
    if isinstance(value, pendulum.DateTime):
        return value
    # pendulum.parse can return Date, Time or Duration when exact=True
    # but should only return DateTime when exact=False.
    return cast(pendulum.DateTime, pendulum.parse(value, exact=False))


def key_from_k8s_label(value: str) -> WireguardKey:
    """Convert key data that may have been stored in a k8s label.
    Strip the pre-/postfix we added when creating the label.
    """
    if value.startswith("wg-") and value.endswith("-pubkey"):
        value = value[3:-7]
    return WireguardKey(value)


def key_to_k8s_label(key: WireguardKey) -> str:
    """Kubernetes label values have to begin and end with alphanumeric
    characters and be less than 63 byte."""
    return f"wg-{key.urlsafe}-pubkey"


@define
class Deployment:
    cluster: Cluster
    recipe: DeploymentRecipe
    client_public_key: WireguardKey
    client_ip: IPv4Address | IPv6Address = field(
        converter=ip_address, validator=check_in_network(CLIENT_NETWORK)
    )
    name: str = field()
    created: pendulum.DateTime = field(converter=parse_date)

    @name.default
    def _default_name(self) -> str:
        return randomname.get_name()

    @created.default
    def _default_created(self) -> pendulum.DateTime:
        return pendulum.now().start_of("second")

    @classmethod
    def from_recipe(
        cls,
        cluster: Cluster,
        recipe: DeploymentRecipe,
        client_public_key: WireguardKey,
    ) -> Deployment:
        client_ip = cluster.get_unique_client_address()
        return cls(
            cluster=cluster,
            recipe=recipe,
            client_public_key=client_public_key,
            client_ip=client_ip,
        )

    @classmethod
    def from_deployment(
        cls, cluster: Cluster, uuid: UUID, key: WireguardKey
    ) -> Deployment:
        """Recreate Deployment from already deployed backend for this user.

        Raises IndexError when there is none.
        """
        client_key_label = key_to_k8s_label(key)
        ns = cluster.get_peers(
            f"findcloudlet.org/uuid={uuid}",
            f"findcloudlet.org/key={client_key_label}",
        )
        return cls.from_manifest(cluster, ns[0])

    @classmethod
    def from_manifest(cls, cluster: Cluster, k8s_json: dict[str, Any]) -> Deployment:
        metadata = k8s_json["metadata"]

        uuid = UUID(metadata["labels"]["findcloudlet.org/uuid"])
        recipe = DeploymentRecipe.from_uuid(uuid)
        client_key = key_from_k8s_label(metadata["labels"]["findcloudlet.org/key"])

        return cls(
            cluster=cluster,
            name=metadata["name"],
            recipe=recipe,
            client_public_key=client_key,
            client_ip=metadata["labels"]["findcloudlet.org/client"],
            created=metadata["annotations"]["findcloudlet.org/created"],
        )

    def deploy(self) -> None:
        while True:
            if self.is_deployed():
                return

            client_key_label = key_to_k8s_label(self.client_public_key)
            self.created = self._default_created()
            (
                self.cluster.kubectl["apply", "-f", "-"]
                << f"""\
apiVersion: kilo.squat.ai/v1alpha1
kind: Peer
metadata:
  name: "{self.name}"
  labels:
    findcloudlet.org: deployment
    findcloudlet.org/uuid: "{self.recipe.uuid}"
    findcloudlet.org/key: "{client_key_label}"
    findcloudlet.org/client: "{self.client_ip}"
  annotations:
    findcloudlet.org/created: "{self.created}"
spec:
  allowedIPs:
    - "{self.client_ip}/32"
  publicKey: "{self.client_public_key}"
  persistentKeepalive: 10
"""
            )()
            # check if we are the only deployment?
            # this is probably not how to do it...
            deployment = self.cluster.get(self.recipe.uuid, self.client_public_key)
            if deployment is None or deployment == self:
                break

            print("Duplicate deployments found, deleting and retrying")
            self.expire()
            self = deployment

        self.helm_install()

    def is_deployed(self) -> bool:
        """Kilo peer is removed when a lease expires"""
        return self.cluster.kubectl["get", "peer", self.name, "-o", "name"] & TF

    def expire(self) -> None:
        """Remove kilo peer and shut down backend"""
        self.cluster.kubectl("delete", "peer", self.name, retcode=None)
        self.cluster.helm(
            "uninstall", "--namespace", self.name, self.name, retcode=None
        )
        self.cluster.kubectl("delete", "namespace", self.name, retcode=None)

    def helm_install(self) -> None:
        with NamedTemporaryFile(delete=False) as f:
            f.write(yaml.dump(self.recipe.values).encode("utf-8"))
            f.flush()

            self.cluster.helm(
                "install",
                "--namespace",
                self.name,
                "--create-namespace",
                "--values",
                f.name,
                "--replace",
                self.name,
                self.recipe.chart_ref,
            )

    def asdict(self) -> dict[str, Any]:
        status = "Deployed" if self.is_deployed() else "Expired"
        return {
            "DeploymentName": self.name,
            "UUID": str(self.recipe.uuid),
            "ApplicationKey": str(self.client_public_key),
            "Status": status,
            "Created": str(self.created),
            "TunnelConfig": {
                "publicKey": str(self.cluster.tunnel_public_key),
                "allowedIPs": ["0.0.0.0/0"],
                "endpoint": str(self.cluster.tunnel_endpoint),
                "address": [str(self.client_ip)],
                "dns": [
                    str(self.cluster.kubedns_address),
                    f"{self.name}.svc.cluster.local",
                    "svc.cluster.local",
                    "cluster.local",
                ],
            },
        }
