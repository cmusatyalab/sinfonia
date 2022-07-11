# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from pathlib import Path
from uuid import UUID

from sinfonia.cli_tier3 import load_application_keys


def test_cached_keys(monkeypatch, mock_generate_keypair, tmp_path):
    cache_dir = Path(tmp_path, "cache").resolve()
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

    uuid = UUID("00000000-0000-0000-0000-000000000000")

    generated = load_application_keys(uuid)
    assert "private_key" in generated
    assert "public_key" in generated

    cached = load_application_keys(uuid)
    assert generated["private_key"] == cached["private_key"]
    assert generated["public_key"] == cached["public_key"]

    cl_cache_dir = cache_dir / "sinfonia"
    assert (cl_cache_dir / str(uuid)).exists()


def test_unique_keys(monkeypatch, mock_generate_keypair, tmp_path):
    cache_dir = Path(tmp_path, "cache").resolve()
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

    uuid0 = UUID("00000000-0000-0000-0000-000000000000")

    generated = load_application_keys(uuid0)
    assert "private_key" in generated
    assert "public_key" in generated

    uuid1 = UUID("00000000-0000-0000-0000-000000000001")

    cached = load_application_keys(uuid1)
    assert generated["private_key"] != cached["private_key"]
    assert generated["public_key"] != cached["public_key"]

    cl_cache_dir = cache_dir / "sinfonia"
    assert (cl_cache_dir / str(uuid0)).exists()
    assert (cl_cache_dir / str(uuid1)).exists()
