#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""A client info object encapsulates what we know about the Tier3 client.
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address

from attrs import define
from flask import request
from wireguard_tools import WireguardKey

from .geo_location import GeoLocation


@define
class ClientInfo:
    """ClientInfo encapsulates what we know of the Tier3 client."""

    publickey: WireguardKey
    ipaddress: IPv4Address | IPv6Address
    location: GeoLocation | None

    @classmethod
    def from_request(cls, application_key: str) -> ClientInfo:
        """Create ClientInfo object from http request parameters.
        May raise ValueError when parameters are badly formatted.
        """
        try:
            client_address = request.headers.get("X-ClientIP")
            if client_address is None:
                raise KeyError
            client_ipaddress = ip_address(client_address)
        except (KeyError, ValueError):
            if request.remote_addr is None:
                raise ValueError
            client_ipaddress = ip_address(request.remote_addr)

        try:
            client_location = GeoLocation.from_request_or_addr(client_ipaddress)
        except ValueError:
            client_location = None

        return cls(
            publickey=WireguardKey(application_key),
            ipaddress=client_ipaddress,
            location=client_location,
        )

    @classmethod
    def from_address(
        cls,
        application_key: str,
        address: str | IPv4Address | IPv6Address,
    ) -> ClientInfo:
        ipaddress = ip_address(address)
        location = GeoLocation.from_address(ipaddress)
        return cls(
            publickey=WireguardKey(application_key),
            ipaddress=ipaddress,
            location=location,
        )
