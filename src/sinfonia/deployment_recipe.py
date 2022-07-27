#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""A deployment recipe is a YAML document specifying values for a deployment.

The deployment recipe file is a yaml document which is expected to be named as
a unique UUID with a .yaml extension and is stored in the `--recipes=URL`
(`SINFONIA_RECIPES` environment variable) repository of a Sinfonia Tier2
instance.

There is an optional description field, which is used for documenting the
purpose and customizations of this specific deployment.

The chart and version fields are combined into 'chart-version.tgz' and looked
for relative to where this document was found.  So chart could refer to a
subdirectory (charts/example), but it could also be a fully qualified URL if
the chart is stored somewhere else, i.e. https://thirdparty.org/charts/example
The charts' template values can be overriden with a local values.

Example recipe.yaml file,

    description: |-
        This is a description for the example deployment.
        We typically specify at least a fullnameOverride because the default
        template helm chart defines this as "namespace-chartname" and this name
        is used to name the service. By overriding this generated name we get a
        predictable service name that a client can use without knowing the
        namespace name.
    chart: example
    version: 0.1.0
    values:
        fullnameOverride: example
    restricted: false
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import yaml
from attrs import define
from flask import current_app
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from requests.exceptions import RequestException
from yarl import URL

from .deployment_repository import DeploymentRepository

SINFONIA_RECIPE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "description": "Schema definition for 'deployment recipe' files",
    "type": "object",
    "properties": {
        "description": {
            "description": "Description for this deployment recipe",
            "type": "string",
        },
        "chart": {
            "description": "Name of helm chart to install",
            "type": "string",
        },
        "version": {
            "description": "Version of helm chart to install",
            "type": "string",
        },
        "values": {
            "description": "Overrides for chart values",
            "type": "object",
        },
        "restricted": {
            "description": "Try to keep recipe private (default: true)",
            "type": "boolean",
        },
    },
    "required": ["chart", "version"],
}


@define
class DeploymentRecipe:
    repository: DeploymentRepository
    uuid: UUID
    description: str | None
    chart: str
    version: str
    values: dict
    restricted: bool

    @classmethod
    def from_uuid(cls, uuid: UUID | str) -> DeploymentRecipe:
        repository = current_app.config["deployment_repository"]
        if isinstance(uuid, str):
            uuid = UUID(uuid)
        try:
            return cls.from_repo(repository, uuid)
        except RequestException:
            raise ValueError(f"Request for unknown recipe {uuid}")
        except ValidationError:
            raise ValueError(f"Failed to validate recipe {uuid}")

    @classmethod
    def from_repo(
        cls, repository: DeploymentRepository, uuid: UUID
    ) -> DeploymentRecipe:
        """Load deployment recipe from yaml document.
        May raise jsonschema.exceptions.ValidationError.
        """
        recipe_yaml = repository.get(str(uuid) + ".yaml")

        recipe = yaml.safe_load(recipe_yaml)
        validator = Draft202012Validator(SINFONIA_RECIPE_SCHEMA)
        validator.validate(recipe)

        return cls(
            repository=repository,
            uuid=uuid,
            chart=recipe["chart"],
            version=recipe["version"],
            values=recipe.get("values", {}),
            description=recipe.get("description"),
            restricted=recipe.get("restricted", True),
        )

    @property
    def chart_version(self) -> str:
        return f"{self.chart}-{self.version}"

    @property
    def chart_ref(self) -> URL:
        return self.repository.join(self.chart_version + ".tgz")

    def asdict(self) -> dict[str, Any]:
        assert not self.restricted
        recipe: dict[str, Any] = {
            "chart": self.chart,
            "version": self.version,
        }
        if self.description is not None:
            recipe["description"] = self.description
        if self.values:
            recipe["values"] = self.values
        return recipe
