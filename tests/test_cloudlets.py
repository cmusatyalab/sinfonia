# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from io import StringIO
from ipaddress import IPv4Network

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
