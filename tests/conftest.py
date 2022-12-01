# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from uuid import UUID

import pytest
from flask import Flask
from geolite2 import geolite2

from sinfonia.deployment_repository import DeploymentRepository
from sinfonia.matchers import match_by_location, match_by_network, match_random

GOOD_UUID = "00000000-0000-0000-0000-000000000000"
GOOD_CONTENT = """\
chart: example
version: 0.1.0
restricted: false
"""
BAD_UUID = "00000000-0000-0000-0000-000000000001"
BAD_CONTENT = """\
chart: example
"""
RESTRICTED_UUID = "00000000-0000-0000-0000-000000000002"
RESTRICTED_CONTENT = """\
chart: private
version: 0.1.0
"""


@pytest.fixture(scope="session")
def repository(tmp_path_factory):
    repo = tmp_path_factory.mktemp("repository")
    (repo / GOOD_UUID).with_suffix(".yaml").write_text(GOOD_CONTENT)
    (repo / BAD_UUID).with_suffix(".yaml").write_text(BAD_CONTENT)
    (repo / RESTRICTED_UUID).with_suffix(".yaml").write_text(RESTRICTED_CONTENT)
    return DeploymentRepository(repo)


@pytest.fixture(scope="session")
def good_uuid():
    return UUID(GOOD_UUID)


@pytest.fixture(scope="session")
def bad_uuid():
    return UUID(BAD_UUID)


@pytest.fixture(scope="session")
def restricted_uuid():
    return UUID(RESTRICTED_UUID)


@pytest.fixture(scope="session")
def flask_app():
    app = Flask("test")
    app.config["geolite2_reader"] = geolite2.reader()
    app.config["match_functions"] = [match_by_network, match_by_location, match_random]
    return app


@pytest.fixture(scope="session")
def example_wgkey():
    return "YpdTsMtb/QCdYKzHlzKkLcLzEbdTK0vP4ILmdcIvnhc="
