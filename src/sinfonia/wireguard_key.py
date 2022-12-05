#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""Wireguard key handling.

Validate and convert between standard and urlsafe encodings.
"""

from __future__ import annotations

from base64 import standard_b64encode, urlsafe_b64decode, urlsafe_b64encode

from attrs import define, field


def convert_wireguard_key(value: str | WireguardKey) -> bytes:
    """Accepts urlsafe encoded base64 keys with possibly missing padding.
    Checks if the (decoded) key is a 32-byte byte string
    """
    if isinstance(value, WireguardKey):
        return value.keydata

    # in case this was a key stored in a k8s label
    value = value.lstrip("wg-").rstrip("-pubkey")

    raw_key = urlsafe_b64decode(value + "==")

    if len(raw_key) != 32:
        raise ValueError

    return raw_key


@define
class WireguardKey:
    keydata: bytes = field(converter=convert_wireguard_key)

    def __str__(self) -> str:
        return standard_b64encode(self.keydata).decode("utf-8")

    @property
    def urlsafe(self) -> str:
        return urlsafe_b64encode(self.keydata).decode("utf-8").rstrip("=")

    @property
    def k8s_label(self) -> str:
        """Kubernetes label values have to begin and end with alphanumeric
        characters and be less than 63 byte."""
        return f"wg-{self.urlsafe}-pubkey"
