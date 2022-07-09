#
# Sinfonia
#
# Functions to maintain list of known cloudlets
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import logging
import random
import socket
from concurrent.futures import Future
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_interface
from operator import itemgetter
from typing import Any, List, Sequence, Union
from uuid import UUID, uuid4

import pendulum
import requests
import yaml
from attrs import define
from connexion.exceptions import ProblemException
from flask import current_app
from jsonschema import Draft202012Validator
from yarl import URL

from .geo_location import GeoLocation, geolocate
from .wireguard_key import WireguardKey

CLOUDLET_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "description": "Schema definition for cloudlet.yaml config file",
    "type": "object",
    "properties": {
        "name": {
            "description": "Cloudlet name used for logging purposes",
            "type": "string",
        },
        "endpoint": {
            "description": "URL for this Sinfonia Tier 2 instance",
            "type": "string",
            "format": "uri",
        },
        "location": {
            "description": "Geographic coordinate of this Tier 2 cloudlet",
            "$ref": "#/$defs/geolocation",
        },
        "locations": {
            "description": "Coordinates of cloudlets managed by this Tier 2 instance",
            "type": "array",
            "items": {"$ref": "#/$defs/geolocation"},
            "uniqueItems": True,
        },
        "local_networks": {
            "description": "List of networks considered close to this Tier 2 instance",
            "type": "array",
            "items": {"$ref": "#/$defs/ipnetwork"},
            "uniqueItems": True,
        },
        "accepted_clients": {
            "description": "List of client networks this Tier 2 instance will accept",
            "type": "array",
            "items": {"$ref": "#/$defs/ipnetwork"},
            "uniqueItems": True,
        },
        "rejected_clients": {
            "description": "List of client networks the Tier 2 instance will refuse",
            "type": "array",
            "items": {"$ref": "#/$defs/ipnetwork"},
            "uniqueItems": True,
        },
        "resources": {
            "description": "Resource measurements",
            "type": "object",
            "additionalProperties": {"type": "number", "format": "float"},
        },
    },
    "required": ["endpoint"],
    "$defs": {
        "geolocation": {
            "type": "array",
            "prefixItems": [
                {"$ref": "#/$defs/latitude"},
                {"$ref": "#/$defs/longitude"},
            ],
            "minItems": 2,
            "maxItems": 2,
        },
        "ipnetwork": {
            "type": "string",
            # "format": "ipaddress/netmask",
        },
        "latitude": {
            "type": "number",
            "minimum": -90,
            "maximum": 90,
        },
        "longitude": {
            "type": "number",
            "minimum": -180,
            "maximum": 180,
        },
    },
}


logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def getaddrinfo(host, port):
    # return list of global ip addresses for the service at host/port.
    addresses = []
    try:
        for _family, _type, _proto, _flags, addr in socket.getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP
        ):
            address = ip_interface(addr[0])
            if address.is_global:
                addresses.append(address)
    except socket.gaierror:
        pass
    return addresses


def estimated_rtt(distance_in_km):
    speed_of_light = 299792.458
    return 2 * (distance_in_km / speed_of_light)


NetworkList = List[Union[IPv4Network, IPv6Network]]


@define
class Cloudlet:
    uuid: UUID
    endpoint: URL
    name: str
    locations: list[GeoLocation]
    local_networks: NetworkList
    accepted_clients: NetworkList
    rejected_clients: NetworkList
    resources: dict[str, float]
    api_version: int
    last_update: pendulum.DateTime | None

    @classmethod
    def new(
        cls,
        uuid: UUID,
        endpoint: URL,
        name: str | None = None,
        locations: list[GeoLocation] | None = None,
        local_networks: NetworkList | None = None,
        accepted_clients: NetworkList | None = None,
        rejected_clients: NetworkList | None = None,
        resources: dict[str, float] | None = None,
        last_update: pendulum.DateTime | None = None,
    ) -> Cloudlet:
        # default name to hostname of cloudlet url
        if name is None:
            name = endpoint.host or "cloudlet"

        api_version = int(endpoint.parent.name[1:])
        if api_version > 1:
            logging.info(f"Downgrading {endpoint} api version to v1")
            endpoint = endpoint.parent.with_name("v1") / "deploy"
            api_version = 1

        # we may need to resolve the ip address(es) of the cloudlet
        if locations is None or local_networks is None:
            local_addresses = getaddrinfo(endpoint.host, endpoint.port)

        if locations is None:
            # geoip lookup for addresses associated with hostname
            locations = [
                coordinate
                for coordinate in (geolocate(addr.ip) for addr in local_addresses)
                if coordinate is not None
            ]

        # set sensible defaults for local_networks and accepted clients
        if local_networks is None:
            local_networks = local_addresses

        if accepted_clients is None:
            accepted_clients = [IPv4Network("0.0.0.0/0")]
            # should we include ipv6?
            # We can't be sure if the cloudlet has IPv6 but maybe we could
            # check if there is an IPv6 address in local_addresses

        if rejected_clients is None:
            rejected_clients = []

        if resources is None:
            resources = {}

        return cls(
            uuid,
            endpoint,
            name,
            locations,
            [ip_interface(network).network for network in local_networks],
            [ip_interface(network).network for network in accepted_clients],
            [ip_interface(network).network for network in rejected_clients],
            resources,
            api_version,
            last_update,
        )

    @classmethod
    def new_from_yaml(
        cls,
        endpoint: str | URL,
        name: str | None = None,
        location: tuple[float, float] | None = None,
        locations: list[tuple[float, float]] | None = None,
        local_networks: NetworkList | None = None,
        accepted_clients: NetworkList | None = None,
        rejected_clients: NetworkList | None = None,
        resources: dict[str, float] | None = None,
    ) -> Cloudlet:

        if locations is not None or location is not None:
            geolocations = [GeoLocation.from_tuple(coord) for coord in locations or []]

            if location is not None:
                geolocations.insert(0, GeoLocation.from_tuple(location))
        else:
            geolocations = None

        return cls.new(
            uuid=uuid4(),
            endpoint=URL(endpoint),
            name=name,
            locations=geolocations,
            local_networks=local_networks,
            accepted_clients=accepted_clients,
            rejected_clients=rejected_clients,
            resources=resources,
        )

    @classmethod
    def new_from_api(cls, request_body: dict) -> Cloudlet:
        uuid = request_body["uuid"]
        endpoint = URL(request_body["endpoint"])
        locations = [
            GeoLocation.from_tuple(coord) for coord in request_body.get("locations", [])
        ]
        accepted_clients = request_body.get("accepted_clients")
        rejected_clients = request_body.get("rejected_clients")
        resources = request_body.get("resources")

        return cls.new(
            uuid,
            endpoint,
            locations=locations,
            accepted_clients=accepted_clients,
            rejected_clients=rejected_clients,
            resources=resources,
            last_update=pendulum.now(),
        )

    def deploy_async(
        self,
        app_uuid: UUID,
        client_key: WireguardKey,
        client_address: str | None = None,
        client_location: Sequence[float] | None = None,
    ) -> Future:
        """Initiate backend deployment on this cloudlet."""

        def deploy(
            url: str, client_address: str | None, client_location: str | None
        ) -> dict[str, Any] | None:
            try:
                headers: dict[str, str] = {}
                if client_address is not None:
                    headers["X-ClientIP"] = client_address
                if client_location is not None:
                    headers["X-Location"] = f"{client_location[0]},{client_location[1]}"
                r = requests.post(url, headers=headers)
                r.raise_for_status()
                return r.json()
            except requests.exceptions.RequestException:
                logger.exception("Exception while forwarding request")
                return None

        request_url = self.endpoint / str(app_uuid) / client_key.urlsafe

        executor = current_app.config["EXECUTOR"]
        return executor.submit(
            deploy, str(request_url), client_address, client_location
        )

    def deploy(self, app_uuid: UUID, client_key: WireguardKey) -> dict[str, Any]:
        """Request backend deployment on this cloudlet."""

        request = self.deploy_async(app_uuid, client_key)
        result = request.result()
        if result is None:
            raise ProblemException(500, "Error", "Error while forwarding request")

        return result

    def distance_from(self, location: GeoLocation) -> float | None:
        """Calculate closest distance to any cloudlet managed by this Tier 2 instance.
        Return distance in kilometers, or None when cloudlet location is unknown.
        """
        closest = None
        for cloudlet_location in self.locations:
            distance = cloudlet_location - location
            if closest is None or distance < closest:
                closest = distance
        return closest

    def summary(self) -> dict[str, Any]:
        """Returns json encodeable 'CloudletSummary'"""
        summary = dict(
            endpoint=str(self.endpoint),
            locations=self.locations,
            accepted_clients=[str(client) for client in self.accepted_clients],
            rejected_clients=[str(client) for client in self.rejected_clients],
            resources=self.resources,
        )
        if self.last_update is not None:
            summary["last_update"] = str(self.last_update)
        return summary


def load(stream):
    """Load known cloudlets from configuration file."""
    validator = Draft202012Validator(CLOUDLET_SCHEMA)

    def validate_and_create(cloudlet_desc):
        validator.validate(cloudlet_desc)  # will throw ValidationError
        return Cloudlet.new_from_yaml(**cloudlet_desc)

    return [
        validate_and_create(cloudlet_desc)
        for cloudlet_desc in yaml.safe_load_all(stream)
        if cloudlet_desc is not None
    ]


def _filter_by_network(cloudlets, client_ip):
    """Yields any cloudlets that claim to be local.
    Also removes cloudlets that explicitly blacklist the client address
    """
    client_address = ip_address(client_ip)

    # Used to jump the loop whenever a cloudlet can be removed from the list
    class DropCloudlet(Exception):
        pass

    for cloudlet in cloudlets:
        try:
            for network in cloudlet.rejected_clients:
                if client_address in network:
                    logger.debug("Cloudlet (%s) would reject client", cloudlet.name)
                    raise DropCloudlet

            for network in cloudlet.local_networks:
                if client_address in network:
                    logger.info("network (%s)", cloudlet.name)
                    yield cloudlet
                    # don't need/want to return this one again in this query.
                    raise DropCloudlet

            for network in cloudlet.accepted_clients:
                if client_address not in network:
                    logger.debug("Cloudlet (%s) will not accept client", cloudlet.name)
                    raise DropCloudlet

        except DropCloudlet:
            cloudlets.remove(cloudlet)


def _filter_by_location(cloudlets, location):
    """Yields any geographically close cloudlets"""
    by_distance = []

    for cloudlet in cloudlets:
        distance = cloudlet.distance_from(location)
        if distance is not None:
            by_distance.append((distance, cloudlet))

    if not by_distance:
        return

    by_distance.sort(key=itemgetter(0))
    for distance, cloudlet in by_distance:
        logger.info(
            "distance (%s) %d km, %.3f minRTT",
            cloudlet.name,
            distance,
            estimated_rtt(distance),
        )
        yield cloudlet
        cloudlets.remove(cloudlet)


def _random_shuffle(cloudlets):
    """Shuffle anything that is left and return in random order"""
    random.shuffle(cloudlets)
    for cloudlet in cloudlets:
        logger.info("random (%s)", cloudlet.name)
        yield cloudlet


def find(CLOUDLETS, client_ip, location=None):
    """Generator which yields nearby cloudlets."""
    # create list of cloudlets that we can filter/shuffle/etc.
    cloudlets = list(CLOUDLETS.values())

    yield from _filter_by_network(cloudlets, client_ip)

    if location is not None:
        yield from _filter_by_location(cloudlets, location)

    yield from _random_shuffle(cloudlets)
