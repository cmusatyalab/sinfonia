#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""Helpers to handle a repository of deployment descriptions.

Deployment descriptions are stored in a repository defined by `--recipes=URL`
(`SINFONIA_RECIPES` environment variables). This can be either a local
directory, or a remote reference through a URL. This complicates things because
we do still want to avoid typicaly local path traversal exploits. The inputs
here are the Admin defined RECIPES, the UUID from the 'untrusted client', and
the application developer specified chart and version fields in the deployment
recipe file.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
from attrs import define, field
from werkzeug.security import safe_join
from yarl import URL


def _root_to_url(repository_root: str | os.PathLike | URL) -> URL:
    """Canonicalize the repository root."""
    root_url = URL(str(repository_root))

    # if given a local path, make sure it is absolute
    if root_url.scheme == "":
        assert not isinstance(repository_root, URL)
        fullpath = Path(repository_root).resolve()
        root_url = URL.build(scheme="file", path=str(fullpath))

    # adding an empty path forces the url to end with '/'
    return root_url / ""


@define
class DeploymentRepository:
    base_url: URL = field(converter=_root_to_url)

    def join(self, other: str | os.PathLike | URL) -> URL:
        """Try to safely join the current repository with 'other'.

        raises:
        - AssertionError when the 'other' reference refers to a path outside of
          the local repository root directory.
        """
        other_url = URL(str(other))

        if self.base_url.scheme == "file" and other_url.scheme in ["", "file"]:
            local_path = safe_join(self.base_url.path, other_url.path)
            # when safe join fails, it returns None
            assert local_path is not None
            return URL.build(scheme="file", path=local_path)

        # when repository root is not a local directory, the reference we
        # are trying to join should definitely not be one.
        assert not (self.base_url.scheme != "file" and other_url.scheme == "file")
        return self.base_url.join(other_url)

    def get(self, ref: str | URL) -> str:
        """Retrieves the contents of 'ref'.

        raises:
        - AssertionError when the 'other' reference refers to a path outside of
          the local repository root directory.
        - requests.ConnectionError when there is a network problem.
        - requests.HTTPError when the server returned an unsuccessful status
          code.
        - requests.Timeout when the request timed out during connect or read.
        (requests related exceptions can be caught with 'requests.RequestException')
        """
        ref_url = self.join(ref)

        if ref_url.scheme == "file":
            return Path(ref_url.path).read_text()

        r = requests.get(str(ref_url))
        r.raise_for_status()
        return r.text
