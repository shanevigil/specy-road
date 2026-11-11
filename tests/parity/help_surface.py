"""The CLI's command surface: its parsers, and the ``--help`` transcript of each command.

Top-level names come from :func:`specy_road.cli.registered_agent_command_names`; each name's
parsers from :func:`specy_road.cli.command_parsers` (``specyrd``'s from its ``build_parser()``),
followed down through their subcommands, so the surface cannot drift from the CLI. From each
parser the inventory keeps the subparser path, the option strings ``--help`` lists and whether the
command passes the remaining arguments through (an ``argparse.REMAINDER`` argument).
"""

from __future__ import annotations

import argparse
import functools
import os
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from specy_road.cli_args import subcommand_parsers
from tests.parity.support import run_cli, transcript

MODULES = {"specy-road": "specy_road.cli", "specyrd": "specy_road.specyrd_cli"}

#: Names ``cli.main`` answers itself, without a parser: ``--help`` (a fixed text, ``cli_usage``)
#: and ``version``.
_NO_PARSER = ("specy-road",), ("specy-road", "version")


def parser_inventory(path: tuple[str, ...], parser: argparse.ArgumentParser) -> dict:
    """Subcommands, listed option strings and passthrough of the command ``path`` parses with."""
    actions = parser._actions
    return {
        "path": list(path[1:]),
        "subcommands": sorted(subcommand_parsers(parser)),
        "options": sorted(
            o for a in actions if a.help != argparse.SUPPRESS for o in a.option_strings
        ),
        "passthrough": any(a.nargs == argparse.REMAINDER for a in actions),
    }


def _walk(
    path: tuple[str, ...], parser: argparse.ArgumentParser
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    yield path, parser
    for name, sub in subcommand_parsers(parser).items():
        yield from _walk((*path, name), sub)


def command_tree() -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser | None]]:
    """Every command path with the parser it parses with (``None`` for the ``_NO_PARSER`` names)."""
    from specy_road.cli import command_parsers, registered_agent_command_names
    from specy_road.specyrd_cli import build_parser as specyrd_parser

    names = registered_agent_command_names()
    yield from ((path, None) for path in _NO_PARSER)
    for name in sorted(names["specy-road"] - {"version"}):
        yield from _walk(("specy-road", name), command_parsers(name)[-1])
    specyrd = specyrd_parser()
    yield ("specyrd",), specyrd
    for name in sorted(names["specyrd"]):
        yield from _walk(("specyrd", name), subcommand_parsers(specyrd)[name])


def _help(path: tuple[str, ...], cwd: Path) -> tuple[tuple[str, ...], str]:
    result = run_cli(MODULES[path[0]], [*path[1:], "--help"], cwd=cwd)
    return path, transcript([*path, "--help"], result, {cwd: "<CWD>"})


@functools.lru_cache(maxsize=1)
def crawl() -> dict[str, dict]:
    """The whole surface: ``{"specy-road review record": {"transcript": ..., "inventory": ...}}``.

    The roots (``specy-road``, ``specyrd``) are included: their help is the command list a user
    sees. Help runs from an empty directory, so no repo's state reaches the text.
    """
    tree = list(command_tree())
    found: dict[str, dict] = {}
    for path, parser in tree:
        inventory = (
            {"path": list(path[1:]), "subcommands": [], "options": [], "passthrough": False}
            if parser is None
            else parser_inventory(path, parser)
        )
        if len(path) == 1:
            inventory = {**inventory, "subcommands": []}  # the roots' commands: registered names
        found[" ".join(path)] = {"inventory": inventory}
    with (
        tempfile.TemporaryDirectory() as tmp,
        ThreadPoolExecutor(min(8, os.cpu_count() or 1)) as pool,
    ):
        for path, text_out in pool.map(lambda p: _help(p, Path(tmp)), [p for p, _ in tree]):
            found[" ".join(path)]["transcript"] = text_out
    return found
