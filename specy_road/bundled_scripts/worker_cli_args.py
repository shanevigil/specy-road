"""``worker message --fix-round`` (M14.11), split from :mod:`worker_cli` for the file limit."""

from __future__ import annotations

import argparse
from typing import Any


class FixRound(argparse.Action):
    """``--fix-round``: lets ``worker message`` omit ``--file``/``--text``.

    The pair stays a required mutually exclusive group, so a plain message without either keeps argparse's own
    refusal (exit 2, with the ``(--file PATH | --text TEXT)`` usage). argparse checks required groups only after
    every argument's action has run, so this action lifting the requirement covers ``--fix-round`` in any position.
    """

    def __init__(self, *args: Any, group: argparse._MutuallyExclusiveGroup, **kwargs: Any) -> None:
        super().__init__(*args, nargs=0, default=False, **kwargs)
        self.group = group

    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace, values: Any,
                 option_string: str | None = None) -> None:
        setattr(namespace, self.dest, True)
        self.group.required = False   # build_parser makes a new parser per main(), so this lasts one parse
