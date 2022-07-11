# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from ipaddress import IPv4Address

from sinfonia.client_info import ClientInfo


class TestClientInfo:
    def test_from_request(self, flask_app, example_wgkey):
        with flask_app.test_request_context(headers={"X-ClientIP": "128.2.0.1"}):
            client_info = ClientInfo.from_request(example_wgkey)
            assert client_info.ipaddress == IPv4Address("128.2.0.1")
            assert client_info.location is not None
            assert client_info.location.coordinate == (40.4439, -79.9561)

        with flask_app.test_request_context(
            headers={"X-ClientIP": "128.2.0.1", "X-Location": "37.4178,-122.172"}
        ):
            client_info = ClientInfo.from_request(example_wgkey)
            assert client_info.ipaddress == IPv4Address("128.2.0.1")
            assert client_info.location is not None
            assert client_info.location.coordinate == (37.4178, -122.172)

    def test_from_address(self, flask_app, example_wgkey):
        with flask_app.app_context():
            client_info = ClientInfo.from_address(example_wgkey, "128.2.0.1")
            assert client_info.ipaddress == IPv4Address("128.2.0.1")
            assert client_info.location is not None
            assert client_info.location.coordinate == (40.4439, -79.9561)
