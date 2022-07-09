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

import ipaddress
import json
import logging
import math
import random
from ipaddress import IPv4Address
from typing import Iterator, Sequence
from uuid import UUID, uuid4

import pendulum
import requests
from attrs import define, field
from plumbum.cmd import helm, kubectl
from plumbum.commands.base import BaseCommand
from requests.exceptions import RequestException
from yarl import URL

from .deployment import CLIENT_NETWORK, Deployment
from .deployment_score import DeploymentScore
from .wireguard_key import WireguardKey

RESOURCE_QUERIES = {
    "cpu_ratio": 'sum(rate(node_cpu_seconds_total{mode!="idle"}[1m])) / sum(node:node_num_cpu:sum)',  # noqa
    "mem_ratio": "sum(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) / count(node_memory_MemTotal_bytes)",  # noqa
    "net_rx_rate": "instance:node_network_receive_bytes_excluding_lo:rate5m",
    "net_tx_rate": "instance:node_network_transmit_bytes_excluding_lo:rate5m",
    "gpu_ratio": "sum(DCGM_FI_DEV_GPU_UTIL) / count(DCGM_FI_DEV_GPU_UTIL)",
}

LEASE_DURATION = 300  # seconds


@define
class Cluster:
    uuid: UUID = field(kw_only=True, converter=UUID)

    # bound commands using the current cluster config and context
    kubectl: BaseCommand = field()
    helm: BaseCommand = field()

    # tunnel public key and endpoint information
    tunnel_public_key: WireguardKey = field(init=False)
    tunnel_endpoint: str = field(init=False)
    kubedns_address: ipaddress.IPv4Address = field(
        init=False, converter=ipaddress.ip_address
    )

    # currently we can only extract resource metrics from a local
    # prometheus when we're running in a kubernetes cluster. in the long
    # run we may have to use kubectl port-forward to punch a hole into the
    # right cluster.
    prometheus_url: URL = field()

    @uuid.default
    def _default_uuid(self) -> str:
        return str(uuid4())

    @classmethod
    def connect(cls, kubeconfig: str = "", kubecontext: str = "") -> Cluster:
        return cls(
            kubectl=kubectl[f"--kubeconfig={kubeconfig}", f"--context={kubecontext}"],
            helm=helm[f"--kubeconfig={kubeconfig}", f"--kube-context={kubecontext}"],
        )

    @tunnel_public_key.default
    def _tunnel_public_key(self) -> str:
        key = self.kubectl(
            "get",
            "node",
            "-o",
            r"jsonpath={.items[0].metadata.annotations.kilo\.squat\.ai/key}",
        ).strip()
        return key

    @tunnel_endpoint.default
    def _tunnel_endpoint(self) -> str:
        return self.kubectl(
            "get",
            "node",
            "-o",
            r"jsonpath={.items[0].metadata.annotations.kilo\.squat\.ai/endpoint}",
        ).strip()

    @kubedns_address.default
    def _kubedns_address(self) -> str:
        return self.kubectl(
            "-n",
            "kube-system",
            "get",
            "service",
            "kube-dns",
            "-o",
            "jsonpath={.spec.clusterIP}",
        ).strip()

    @prometheus_url.default
    def _prometheus_url(self) -> URL:
        # return URL("http://localhost:9090/api/v1/query")
        return URL(
            "http://kube-prometheus-stack-prometheus.monitoring:9090/api/v1/query"
        )

    def get_peer(self, *args: str):
        selector = ",".join(args)
        result = self.kubectl("get", "peer", "-o", "json", "-l", selector)
        return json.loads(result)["items"]

    def deployments(self) -> Iterator[Deployment]:
        for ns in self.get_peer("findcloudlet.org=deployment"):
            yield Deployment.from_manifest(self, ns)

    def get(
        self,
        uuid: str | UUID,
        key: str | WireguardKey,
        create: bool = False,
        default: Deployment | None = None,
    ) -> Deployment | None:
        try:
            # make sure uuid and key are correctly formatted
            uuid = UUID(str(uuid))
            key = WireguardKey(key)
        except ValueError:
            return None

        try:
            ns = self.get_peer(
                f"findcloudlet.org/uuid={uuid}",
                f"findcloudlet.org/key={key.urlsafe}",
            )
            return Deployment.from_manifest(self, ns[0])
        except IndexError:
            pass

        try:
            score = DeploymentScore.from_uuid(uuid)
        except ValueError:
            logging.exception(f"Failed to retrieve score {uuid}")
            return None

        if not create:
            return default

        return Deployment.from_score(
            cluster=self,
            score=score,
            client_public_key=key,
        )

    def get_unique_client_address(self) -> IPv4Address:
        """Find an unused address to assign to a client"""
        while True:
            hosts = list(CLIENT_NETWORK.hosts())
            for client_ip in random.sample(hosts, 32):
                ns = self.get_peer(f"findcloudlet.org/client={client_ip}")
                if not ns:
                    assert isinstance(client_ip, IPv4Address)
                    return client_ip
            print("Unable to find unique client ip in 32 tries, resampling candidates")

    def get_resources(self) -> dict[str, float]:
        resources: dict[str, float] = {}

        for resource in RESOURCE_QUERIES:
            try:
                r = requests.post(
                    str(self.prometheus_url),
                    data={
                        "query": f"scalar({RESOURCE_QUERIES[resource]})",
                    },
                )
                r.raise_for_status()

                result = r.json()
                assert result["status"] == "success"
                assert result["data"]["resultType"] == "scalar"

                metric = float(result["data"]["result"][1])
                if math.isfinite(metric):
                    resources[resource] = metric

            except (RequestException, AssertionError, ValueError):
                logging.exception(f"Failed to retrieve {resource}")
                pass
        return resources

    def get_active_peers(
        self, cutoff: pendulum.DateTime
    ) -> Sequence[WireguardKey] | None:
        try:
            r = requests.post(
                str(self.prometheus_url),
                data={
                    "query": f"wireguard_last_handshake_seconds>{cutoff.int_timestamp}",
                },
            )
            r.raise_for_status()

            result = r.json()
            assert result["status"] == "success"
            assert result["data"]["resultType"] == "vector"

            return [
                WireguardKey(peer["metric"]["public_key"])
                for peer in result["data"]["result"]
            ]
        except (RequestException, AssertionError, ValueError):
            logging.exception("Failed to retrieve inactive peers")
            return None

    def expire_inactive_deployments(self) -> None:
        cutoff = pendulum.now().subtract(seconds=LEASE_DURATION)

        active_peers = self.get_active_peers(cutoff)
        if active_peers is None:
            return

        for deployment in self.deployments():
            if (
                deployment.created < cutoff
                and deployment.client_public_key not in active_peers
            ):
                logging.info(f"Expiring {deployment.name}")
                deployment.expire()
