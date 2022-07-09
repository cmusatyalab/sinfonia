# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest

from sinfonia.geo_location import GeoLocation


class TestGeoLocation:
    def test_create(self):
        location = GeoLocation(40.4439, -79.9561)
        assert location.latitude == 40.4439
        assert location.longitude == -79.9561
        assert location.coordinate == (40.4439, -79.9561)

        with pytest.raises(ValueError):
            GeoLocation(-100.0, 0.0)
        with pytest.raises(ValueError):
            GeoLocation(100.0, 0.0)
        with pytest.raises(ValueError):
            GeoLocation(0.0, -200.0)
        with pytest.raises(ValueError):
            GeoLocation(0.0, 200.0)
        with pytest.raises(ValueError):
            GeoLocation("here", "there")

    def test_from_tuple(self):
        location = GeoLocation.from_tuple((40.4439, -79.9561))
        assert location.coordinate == (40.4439, -79.9561)

    def test_from_address(self, flask_app):
        with flask_app.app_context():
            location = GeoLocation.from_address("128.2.0.1")
            assert location.coordinate == (40.4439, -79.9561)

            location = GeoLocation.from_address("130.37.0.1")
            assert location.coordinate == (52.3556, 4.9135)

    def test_from_request(self, flask_app):
        with flask_app.test_request_context(headers={"X-Location": "40.4439,-79.9561"}):
            location = GeoLocation.from_request()
            assert location.coordinate == (40.4439, -79.9561)

        with pytest.raises(ValueError), flask_app.test_request_context():
            GeoLocation.from_request()

        with pytest.raises(ValueError), flask_app.test_request_context(
            headers={"X-Location": "40.4439"}
        ):
            GeoLocation.from_request()

        with pytest.raises(ValueError), flask_app.test_request_context(
            headers={"X-Location": "here"}
        ):
            GeoLocation.from_request()

        with flask_app.test_request_context(headers={"X-Location": "here"}):
            location = GeoLocation.from_request_or_addr("128.2.0.1")
            assert location.coordinate == (40.4439, -79.9561)

    def test_distance(self):
        location1 = GeoLocation(40.4439, -79.9561)
        location2 = GeoLocation(52.3556, 4.9135)
        assert int(location1 - location2) == 6274
        assert int(location2 - location1) == 6274
