#
# Sinfonia
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

from pathlib import Path
from typing import Any

import prance


def load_spec(specfile: Path) -> dict[str, Any]:
    """helper to load OpenAPI specifications that include other specifications"""
    parser = prance.ResolvingParser(
        str(specfile.absolute()),
        lazy=True,
        strict=True,
        backend="openapi-spec-validator",
    )
    parser.parse()
    return parser.specification
