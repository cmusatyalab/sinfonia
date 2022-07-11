# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from io import StringIO
from pathlib import Path

import pytest

from sinfonia import cloudlets
from sinfonia.client_info import ClientInfo
from sinfonia.deployment_score import DeploymentScore
from sinfonia.matchers import (
    match_by_location,
    match_by_network,
    match_random,
    tier1_best_match,
)


class TestMatchers:
    NEARBY = {
        "128.2.0.1": [
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
        ],
        "171.64.0.1": [
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
        ],
        "130.37.0.1": [
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
        ],
    }

    @pytest.fixture(scope="class")
    def aws_cloudlets(self, request, flask_app):
        datadir = Path(request.fspath.dirname) / "data"
        with flask_app.app_context():
            with open(datadir / "aws_regions.yaml") as f:
                return cloudlets.load(f)

    @pytest.fixture(scope="class")
    def deployment_score(self, repository, good_uuid):
        return DeploymentScore.from_repo(repository, good_uuid)

    def load(self, string):
        return cloudlets.load(StringIO(string))

    def test_by_network(self, deployment_score, flask_app, example_wgkey):
        with flask_app.app_context():
            client_info = ClientInfo.from_address(
                example_wgkey,
                "128.2.0.1",
            )
            all_cloudlets = self.load(
                "endpoint: http://localhost/api/v1/deploy\n"
                "local_networks: [128.2.0.0/16]\n"
            )
            cloudlets = all_cloudlets[:]
            cloudlet = next(match_by_network(client_info, deployment_score, cloudlets))
            assert cloudlet == all_cloudlets[0]
            assert len(cloudlets) == 0

    def test_by_location(
        self, aws_cloudlets, deployment_score, flask_app, example_wgkey
    ):
        with flask_app.app_context():
            for address, nearby in self.NEARBY.items():
                client_info = ClientInfo.from_address(
                    example_wgkey,
                    address,
                )
                cloudlets = aws_cloudlets[:]
                nearest = [
                    cloudlet.name
                    for cloudlet in match_by_location(
                        client_info, deployment_score, cloudlets
                    )
                ]
                assert nearest == nearby
                assert len(cloudlets) == 0

    def test_random(self, aws_cloudlets, deployment_score, flask_app, example_wgkey):
        with flask_app.app_context():
            client_info = ClientInfo.from_address(example_wgkey, "128.2.0.1")
            cloudlets = aws_cloudlets[:]
            for cloudlet in match_random(client_info, deployment_score, cloudlets):
                assert cloudlet in aws_cloudlets
                assert cloudlet not in cloudlets
            assert len(cloudlets) == 0

    def test_tier1_best_match(
        self, aws_cloudlets, deployment_score, flask_app, example_wgkey
    ):
        matchers = [match_by_network, match_by_location]
        with flask_app.app_context():
            for address, nearby in self.NEARBY.items():
                client_info = ClientInfo.from_address(
                    example_wgkey,
                    address,
                )
                nearest = [
                    cloudlet.name
                    for cloudlet in tier1_best_match(
                        matchers, client_info, deployment_score, aws_cloudlets[:]
                    )
                ]
                assert nearest == nearby
