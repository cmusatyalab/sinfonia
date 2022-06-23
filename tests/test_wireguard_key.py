# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest

from sinfonia.wireguard_key import WireguardKey


def urlsafe_encoding(key):
    return key.translate(str.maketrans("/+", "_-")).rstrip("=")


class TestWireguardKey:
    def test_create(self):
        public_key = "YpdTsMtb/QCdYKzHlzKkLcLzEbdTK0vP4ILmdcIvnhc="
        stored_key = WireguardKey(public_key)
        assert str(stored_key) == public_key
        assert stored_key.urlsafe == urlsafe_encoding(public_key)

        key_copy = WireguardKey(stored_key)
        assert stored_key == key_copy

        with pytest.raises(ValueError):
            WireguardKey("foobar")
