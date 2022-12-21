# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from wireguard_tools import WireguardKey

from sinfonia.deployment import key_from_k8s_label, key_to_k8s_label


class TestWireguardKey:
    def test_to_k8s_label(self, example_wgkey):
        stored_key = WireguardKey(example_wgkey)

        # valid label values:
        k8s_label = key_to_k8s_label(stored_key)

        # must be 63 characters or less
        assert len(k8s_label) <= 63

        # unless empty, must begin and end with an alphanumeric character
        assert len(k8s_label) == 0 or k8s_label[0].isalnum()
        assert len(k8s_label) == 0 or k8s_label[-1].isalnum()

        # contain dashes, underscores, dots and alphanumerics
        for c in k8s_label:
            assert c.isalnum() or c in ["-", "_", "."]

    def test_from_k8s_label(self, example_wgkey):
        stored_key = WireguardKey(example_wgkey)
        k8s_label = key_to_k8s_label(stored_key)

        assert key_from_k8s_label(k8s_label) == stored_key
