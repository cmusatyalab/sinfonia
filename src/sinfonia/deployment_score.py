#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""A deployment score is a YAML document specifying values for a deployment.

The deployment score file is a yaml document which is expected to be named as a
unique UUID with a .yaml extension and is stored in the `--scores=URL`
(`SINFONIA_SCORES` envvar) repository of a Sinfonia Tier2 instance.

There is an optional description field, which is used for documenting the
purpose and customizations of this specific deployment.

The chart and version fields are combined into 'chart-version.tgz' and looked
for relative to where this document was found.  So chart could refer to a
subdirectory (charts/example), but it could also be a fully qualified URL if
the chart is stored somewhere else, i.e. https://thirdparty.org/charts/example
The charts' template values can be overriden with a local values.

Example score.yaml file,

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
"""

from __future__ import annotations

from uuid import UUID

import yaml
from attrs import define
from flask import current_app
from jsonschema import Draft202012Validator
from yarl import URL

from .deployment_repository import DeploymentRepository

SINFONIA_SCORE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "description": "Schema definition for 'deployment score' files",
    "type": "object",
    "properties": {
        "description": {
            "description": "Description for this deployment",
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
    },
    "required": ["chart", "version"],
}


@define
class DeploymentScore:
    repository: DeploymentRepository
    uuid: UUID
    chart: str
    version: str
    values: dict

    @classmethod
    def from_repo(cls, repository: DeploymentRepository, uuid: UUID) -> DeploymentScore:
        """Load deployment score from yaml document.
        May raise jsonschema.exceptions.ValidationError.
        """
        score_yaml = repository.get(str(uuid) + ".yaml")

        score = yaml.safe_load(score_yaml)
        validator = Draft202012Validator(SINFONIA_SCORE_SCHEMA)
        validator.validate(score)

        return cls(
            repository=repository,
            uuid=uuid,
            chart=score["chart"],
            version=score["version"],
            values=score.get("values", {}),
        )

    @property
    def chart_version(self) -> str:
        return f"{self.chart}-{self.version}"

    @property
    def chart_ref(self) -> URL:
        return self.repository.join(self.chart_version + ".tgz")


def get_deployment_score(uuid: UUID) -> DeploymentScore:
    repository = current_app.config["SCORES"]
    return DeploymentScore.from_repo(repository, uuid)
