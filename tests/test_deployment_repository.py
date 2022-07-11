# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

import pytest
from yarl import URL

from sinfonia.deployment_repository import DeploymentRepository

from .conftest import BAD_CONTENT, BAD_UUID, GOOD_CONTENT, GOOD_UUID


class TestDeploymentRepository:
    def test_create_remote(self):
        repo = DeploymentRepository("http://test/example")
        assert repo.base_url == URL("http://test/example/")

    def test_create_local(self):
        repo = DeploymentRepository("/root")
        assert repo.base_url == URL("file:///root/")

        repo = DeploymentRepository("root")
        assert repo.base_url.path.endswith("/root/")

    @pytest.mark.parametrize("root_url", ["http://test/", "file:///test/"])
    def test_join(self, root_url):
        repo = DeploymentRepository(root_url)
        assert repo.join("") == URL(root_url)
        assert repo.join("path") == URL(root_url) / "path"
        assert repo.join("http://other") == URL("http://other")

        with pytest.raises(AssertionError):
            repo.join("file:///escaped")

    def test_join_special_cases(self):
        repo = DeploymentRepository("http://test/")
        assert repo.join("../escaped") == URL("http://test/escaped")
        assert repo.join("http://test/path") == URL("http://test/path")

        repo = DeploymentRepository("file:///test/")
        with pytest.raises(AssertionError):
            repo.join("../escaped")
        with pytest.raises(AssertionError):
            repo.join("file:///escaped")

    def test_get_local(self, repository):
        assert repository.get(f"{GOOD_UUID}.yaml") == GOOD_CONTENT
        assert repository.get(f"{BAD_UUID}.yaml") == BAD_CONTENT
        with pytest.raises(FileNotFoundError):
            repository.get("none.yaml")

    def test_get_remote(self, requests_mock):
        requests_mock.get("http://test/good.yaml", text=GOOD_CONTENT)
        repo = DeploymentRepository("http://test/")
        assert repo.get("good.yaml") == GOOD_CONTENT
