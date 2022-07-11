#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""A geolocation holds latitude, longitude
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address

import geopy.distance
from attrs import define, field
from flask import current_app, request


@define
class GeoLocation:
    latitude: float = field()
    longitude: float = field()

    @latitude.validator
    def _valid_latitude(self, _attribute, value):
        if not -90.0 <= float(value) <= 90.0:
            raise ValueError("latitude out of bounds")

    @longitude.validator
    def _valid_longitude(self, _attribute, value):
        if not -180.0 <= float(value) <= 180.0:
            raise ValueError("latitude out of bounds")

    @classmethod
    def from_request(cls) -> GeoLocation:
        """Get geolocation from X-Location http header.
        Raises ValueError when no valid location is found.
        """
        try:
            location = request.headers.get("X-Location").split(",")
            return cls(float(location[0]), float(location[1]))
        except (KeyError, AttributeError, IndexError, ValueError):
            raise ValueError("X-Location header missing or invalid")

    @classmethod
    def from_address(cls, ipaddress: str | IPv4Address | IPv6Address) -> GeoLocation:
        """Get geolocation from ip address.
        Raises ValueError when no valid location is found for the IP address.
        """
        geolite2_reader = current_app.config["GEOLITE2_READER"]
        try:
            address = ip_address(ipaddress)
            match = geolite2_reader.get(str(address))
            assert match is not None
            location = match["location"]
            return cls(location["latitude"], location["longitude"])
        except (AssertionError, KeyError, ValueError):
            raise ValueError(f"No valid location found for {ipaddress}")

    @classmethod
    def from_request_or_addr(
        cls, ipaddress: str | IPv4Address | IPv6Address
    ) -> GeoLocation:
        try:
            return cls.from_request()
        except ValueError:
            return cls.from_address(ipaddress)

    @classmethod
    def from_tuple(cls, coordinates: tuple[float, float]) -> GeoLocation:
        """Get geolocation from tuple of floats."""
        return cls(coordinates[0], coordinates[1])

    @property
    def coordinate(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)

    def __sub__(self, other: GeoLocation) -> float:
        """Calculate geographic distance between this and other."""
        return geopy.distance.distance(self.coordinate, other.coordinate).km


def geolocate(ipaddress: IPv4Address | IPv6Address) -> GeoLocation | None:
    try:
        return GeoLocation.from_address(ipaddress)
    except ValueError:
        return None
