#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from . import __version__

# define some type aliases to keep pyupgrade from upgrading these to type|None
# because typer uses 'typing.get_type_hints' which fails to parse those with
# python <3.10
OptionalBool = Optional[bool]
OptionalPath = Optional[Path]
OptionalStr = Optional[str]
StrList = List[str]


def version_callback(value):
    if value:
        print(f"Sinfonia {__version__}")
        raise typer.Exit()


version_option: OptionalBool = typer.Option(
    False, "--version", callback=version_callback, is_eager=True
)

port_option: int = typer.Option(5000, help="Port to listen for requests")

recipes_option: OptionalStr = typer.Option(
    "",
    metavar="PATH|URL",
    help="Location of Sinfonia deployment recipes [default: RECIPES]",
    show_default=False,
)
