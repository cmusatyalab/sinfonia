# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest
import wgconfig.wgexec
from flask import Flask
from geolite2 import geolite2

from sinfonia.deployment_repository import DeploymentRepository

GOOD_CONTENT = """\
chart: example
version: 0.1.0
"""
BAD_CONTENT = """\
chart: example
"""


@pytest.fixture(scope="session")
def repository(tmp_path_factory):
    repo = tmp_path_factory.mktemp("repository")
    (repo / "good.yaml").write_text(GOOD_CONTENT)
    (repo / "bad.yaml").write_text(BAD_CONTENT)
    return DeploymentRepository(repo)


@pytest.fixture
def mock_generate_keypair(monkeypatch):
    """wgconfig.wgexec.generate_keypairs mocked so we don't `wg` binary"""
    keypairs = [
        (
            "mHJFze/rYugSqH5y5jYgJmJA+Xn+8GYankWDJx69Ymo=",
            "LaMgyk/jPiVRX1XFhBbbW7RlZQO976ZOcnpjlRIeSCc=",
        ),
        (
            "AB9y9TPUpZRYXdA/VEMmY1vjXN78xnG3W5u0kh+7H3c=",
            "P8+7aAk2FsUYkhX4CvJfFWWThus25+A9AeoIRdeEumU=",
        ),
        (
            "wDKetfz9LiQq1hu4E8x0woPmwFp/Oc6Zt69gglQHsV8=",
            "nyJ86rdfI7nxVk7CBoDV42e6gh6E2EzAbI/dVTGbdjs=",
        ),
    ]

    def generate_keypair():
        return keypairs.pop()

    monkeypatch.setattr(wgconfig.wgexec, "generate_keypair", generate_keypair)


@pytest.fixture(scope="session")
def flask_app():
    app = Flask("test")
    app.config["GEOLITE2_READER"] = geolite2.reader()
    return app
