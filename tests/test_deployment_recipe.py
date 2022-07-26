# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest
from jsonschema import ValidationError

from sinfonia.deployment_recipe import DeploymentRecipe


class TestDeploymentDescription:
    def test_create(self, repository, good_uuid, bad_uuid):
        recipe = DeploymentRecipe.from_repo(repository, good_uuid)
        assert isinstance(recipe, DeploymentRecipe)
        assert recipe.chart_version == "example-0.1.0"

        with pytest.raises(ValidationError):
            DeploymentRecipe.from_repo(repository, bad_uuid)

    def test_asdict(self, repository, good_uuid, restricted_uuid):
        recipe = DeploymentRecipe.from_repo(repository, good_uuid)
        assert recipe.asdict() == dict(chart="example", version="0.1.0")

        recipe = DeploymentRecipe.from_repo(repository, restricted_uuid)
        with pytest.raises(AssertionError):
            recipe.asdict()
