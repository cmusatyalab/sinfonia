# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest

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
