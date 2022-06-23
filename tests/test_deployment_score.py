# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest
from jsonschema import ValidationError

from sinfonia.deployment_score import DeploymentScore


class TestDeploymentDescription:
    def test_create(self, repository):
        score = DeploymentScore.from_repo(repository, "good")
        assert isinstance(score, DeploymentScore)
        assert score.chart_version == "example-0.1.0"

        with pytest.raises(ValidationError):
            DeploymentScore.from_repo(repository, "bad")
