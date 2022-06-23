# Copyright (c) 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest
from prance import ResolvingParser
from prance.util.resolver import RESOLVE_FILES


class TestOpenApiSpecs:
    @pytest.fixture(scope="class")
    def specification_dir(self):
        return Path(__file__).parents[1] / "src" / "sinfonia" / "openapi"

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_tier1_spec(self, specification_dir):
        parser = ResolvingParser(
            str(specification_dir / "sinfonia_tier1.yaml"),
            lazy=True,
            strict=True,
            resolve_type=RESOLVE_FILES,
        )
        parser.parse()

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_tier2_spec(self, specification_dir):
        parser = ResolvingParser(
            str(specification_dir / "sinfonia_tier2.yaml"),
            lazy=True,
            strict=True,
            resolve_type=RESOLVE_FILES,
        )
        parser.parse()
