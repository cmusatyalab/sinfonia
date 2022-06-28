# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest
from requests_mock import ANY as requests_mock_ANY
from typer.testing import CliRunner

from sinfonia.cli_tier3 import app

runner = CliRunner()

pytestmark = pytest.mark.filterwarnings(
    "ignore:.*Validator.iter_errors.*:DeprecationWarning"
)

SUCCESSFUL_DEPLOYMENT = [
    {
        "DeploymentName": "testing-test",
        "UUID": "00000000-0000-0000-0000-000000000000",
        "ApplicationKey": "DnLEmfJzVoCRJYXzdSXIhTqnjygnhh6O+I3ErMS6OUg=",
        "Status": "Deployed",
        "Created": "2050-12-31T00:00:00Z",
        "TunnelConfig": {
            "publicKey": "DnLEmfJzVoCRJYXzdSXIhTqnjygnhh6O+I3ErMS6OUg=",
            "allowedIPs": ["10.0.0.1/24"],
            "endpoint": "127.0.0.1:51820",
            "address": ["10.0.0.2/32"],
            "dns": ["10.0.0.1"],
        },
    }
]


def test_app(requests_mock):
    # mock the tier2 server
    requests_mock.post(
        requests_mock_ANY,
        json=SUCCESSFUL_DEPLOYMENT,
        headers={"Content-Type": "application/json"},
    )

    with runner.isolated_filesystem():
        cache_dir = Path("cache").resolve()
        args = [
            "--config-only",
            "http://localhost:8080",
            "00000000-0000-0000-0000-000000000000",
            "true",
        ]

        result = runner.invoke(app, args, env={"XDG_CACHE_HOME": str(cache_dir)})
        assert result.exit_code == 0

        assert Path(
            "cache", "sinfonia", "00000000-0000-0000-0000-000000000000"
        ).exists()
        assert Path("wg-testingtest.conf").exists()
