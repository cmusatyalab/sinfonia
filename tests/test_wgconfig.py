# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import copy

import pytest

from sinfonia.cli_tier3 import create_wireguard_config

IFNAME = "wg-test"
UUID = "00000000-0000-0000-0000-000000000000"
TUNNEL_CONFIG = {
    "publicKey": "DnLEmfJzVoCRJYXzdSXIhTqnjygnhh6O+I3ErMS6OUg=",
    "allowedIPs": ["10.0.0.1/32"],
    "endpoint": "127.0.0.1:51820",
    "address": ["10.0.0.2/32"],
    "dns": ["10.0.0.1", "test.svc.cluster.local"],
    "privateKey": "DnLEmfJzVoCRJYXzdSXIhTqnjygnhh6O+I3ErMS6OUg=",
}
TUNNEL_CONFIG_CONTENT = """\
[Interface]
PrivateKey = DnLEmfJzVoCRJYXzdSXIhTqnjygnhh6O+I3ErMS6OUg=

[Peer]
PublicKey = DnLEmfJzVoCRJYXzdSXIhTqnjygnhh6O+I3ErMS6OUg=
AllowedIPs = 10.0.0.1/32
Endpoint = 127.0.0.1:51820
"""


def test_create_wireguard_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    create_wireguard_config(IFNAME, TUNNEL_CONFIG)

    generated_conffile = tmp_path / f"{IFNAME}.conf"
    assert generated_conffile.exists()
    assert generated_conffile.read_text() == TUNNEL_CONFIG_CONTENT


def test_create_wireguard_missing_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    bad_config = copy.deepcopy(TUNNEL_CONFIG)
    del bad_config["publicKey"]

    with pytest.raises(KeyError):
        create_wireguard_config(IFNAME, bad_config)
