#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""Announce cloudlet availability on the local network with Zeroconf MDNS.

This will not adapt when interfaces are dynamically added or removed. We are
announcing all addresses on all interfaces, so some may be unreachable for the
receiver. We'll also be announcing the wrong address/port whenever we are
running behind a reverse proxy, and generally whenever we are in a production
deployment and are not using the built-in flask debug server.

So this is probably only useful as a proof of concept and during development.
"""

from __future__ import annotations

import socket

from attrs import define
from werkzeug.serving import get_interface_ip
from zeroconf import ServiceInfo, Zeroconf


@define
class ZeroconfMDNS:
    """Wrapper helping with zeroconf service registration"""

    zeroconf: Zeroconf | None = None

    def announce(self, port: int) -> None:
        """Try to announce our service on IPv4 and IPv6 on all interfaces"""
        if self.zeroconf is not None:
            self.withdraw()

        # werkzeug uses this function to figure out the ip address of the interface
        # that handles the default route. This should work as long as we don't
        # happen to have a secondary interface on the 10.0.0.0/8 network, I think.
        # either way, this seems to be about the best we can do for now because
        # when we just give a list of all known local addresses, it seems like
        # only the last IPv4 and IPv6 addresses end up being resolvable, and
        # these tend to be local-only docker or kvm network addresses on my system.
        address = get_interface_ip(socket.AF_INET)

        info = ServiceInfo(
            "_sinfonia._tcp.local.",
            "cloudlet._sinfonia._tcp.local.",
            parsed_addresses=[address],
            port=port,
            properties=dict(path="/"),
        )
        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(info, allow_name_change=True)

    def withdraw(self) -> None:
        """Withdraw service registration"""
        if self.zeroconf is not None:
            self.zeroconf.unregister_all_services()
            self.zeroconf.close()
            self.zeroconf = None
