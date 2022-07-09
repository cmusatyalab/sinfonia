# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from io import StringIO
from ipaddress import IPv4Network, ip_address
from pathlib import Path

import pytest
from jsonschema import ValidationError

from sinfonia import cloudlets
from sinfonia.geo_location import GeoLocation


class TestValidation:
    def load(self, string):
        return cloudlets.load(StringIO(string))

    def test_config_minimal(self, flask_app):
        with flask_app.app_context():
            cloudlets = self.load("endpoint: http://localhost/api/v1/deploy")
            assert len(cloudlets) == 1
            cloudlet = cloudlets[0]
            assert cloudlet.name == "localhost"
            assert cloudlet.locations == []
            assert cloudlet.local_networks == []
            assert cloudlet.accepted_clients == [IPv4Network("0.0.0.0/0")]
            assert cloudlet.rejected_clients == []

            cloudlet = self.load("endpoint: http://128.2.0.1/api/v1/deploy")[0]
            assert cloudlet.name == "128.2.0.1"
            # this test may fail when geolite2 is updated
            assert cloudlet.locations == [GeoLocation(40.4439, -79.9561)]
            assert cloudlet.local_networks == [IPv4Network("128.2.0.1")]
            assert cloudlet.accepted_clients == [IPv4Network("0.0.0.0/0")]
            assert cloudlet.rejected_clients == []

    def test_config_nourl(self, flask_app):
        with flask_app.app_context():
            with pytest.raises(ValidationError):
                self.load("name: no url specified")

    def test_config_location(self, flask_app):
        with flask_app.app_context():
            # check some things that should work
            cloudlet = self.load(
                """\
endpoint: http://128.2.0.1/api/v1/deploy
location: [40.4439, -79.9444]
"""
            )[0]
            assert cloudlet.locations == [GeoLocation(40.4439, -79.9444)]

            cloudlet = self.load(
                """\
endpoint: "/api/v1/deploy"
locations:
  - [40.4439, -79.9444]
"""
            )[0]
            assert cloudlet.locations == [GeoLocation(40.4439, -79.9444)]

            # and check for things that should fail
            failures = [
                """\
# location should be a lat/long coordinate
endpoint: "/api/v1/deploy"
location: false
""",
                """\
# latitude has to be [-90, 90]
endpoint: "/api/v1/deploy"
location: [-100, 0]
""",
                """\
# longitude has to be [-180, 180]
endpoint: "/api/v1/deploy"
location: [0, 200]
""",
                """\
# don't try to include 'height' in our location
endpoint: "/api/v1/deploy"
location: [0, 0, 0]
""",
                """\
# locations should be a list of lat/long coordinates
endpoint: "/api/v1/deploy"
locations:
  - "Pittsburgh, PA"
""",
            ]
            for config in failures:
                with pytest.raises(ValidationError):
                    self.load(config)


class TestSearch:
    @pytest.fixture(scope="class")
    def aws_cloudlets(self, request, flask_app):
        datadir = Path(request.fspath.dirname) / "data"
        with flask_app.app_context():
            with open(datadir / "aws_regions.yaml") as f:
                return {cloudlet.uuid: cloudlet for cloudlet in cloudlets.load(f)}

    def test_search_from_cmu(self, aws_cloudlets, flask_app):
        with flask_app.app_context():
            address = ip_address("128.2.0.1")
            location = GeoLocation.from_address(address)
            nearest = [
                cloudlet.name
                for cloudlet in cloudlets.find(aws_cloudlets, address, location)
            ]
            assert nearest == [
                "AWS Northern Virginia",
                "AWS Ohio",
                "AWS Canada",
                "AWS Oregon",
                "AWS Northern California",
                "AWS Ireland",
                "AWS London",
                "AWS Paris",
                "AWS Frankfurt",
                "AWS Stockholm",
                "AWS Milan",
                "AWS Sao Paulo",
                "AWS Tokyo",
                "AWS Osaka",
                "AWS Seoul",
                "AWS Bahrain",
                "AWS Mumbai",
                "AWS Hong Kong",
                "AWS Cape Town",
                "AWS Singapore",
                "AWS Sydney",
                "AWS Jakarta",
            ]

    def test_search_from_stanford(self, aws_cloudlets, flask_app):
        with flask_app.app_context():
            address = ip_address("171.64.0.1")
            location = GeoLocation.from_address(address)
            nearest = [
                cloudlet.name
                for cloudlet in cloudlets.find(aws_cloudlets, address, location)
            ]
            assert nearest == [
                "AWS Northern California",
                "AWS Oregon",
                "AWS Ohio",
                "AWS Canada",
                "AWS Northern Virginia",
                "AWS Ireland",
                "AWS Tokyo",
                "AWS London",
                "AWS Stockholm",
                "AWS Osaka",
                "AWS Paris",
                "AWS Seoul",
                "AWS Frankfurt",
                "AWS Milan",
                "AWS Sao Paulo",
                "AWS Hong Kong",
                "AWS Sydney",
                "AWS Bahrain",
                "AWS Mumbai",
                "AWS Singapore",
                "AWS Jakarta",
                "AWS Cape Town",
            ]

    def test_search_from_vu(self, aws_cloudlets, flask_app):
        with flask_app.app_context():
            address = ip_address("130.37.0.1")
            location = GeoLocation.from_address(address)
            nearest = [
                cloudlet.name
                for cloudlet in cloudlets.find(aws_cloudlets, address, location)
            ]
            assert nearest == [
                "AWS London",
                "AWS Frankfurt",
                "AWS Paris",
                "AWS Milan",
                "AWS Ireland",
                "AWS Stockholm",
                "AWS Bahrain",
                "AWS Canada",
                "AWS Northern Virginia",
                "AWS Ohio",
                "AWS Mumbai",
                "AWS Oregon",
                "AWS Seoul",
                "AWS Northern California",
                "AWS Osaka",
                "AWS Hong Kong",
                "AWS Tokyo",
                "AWS Cape Town",
                "AWS Sao Paulo",
                "AWS Singapore",
                "AWS Jakarta",
                "AWS Sydney",
            ]
