"""The CLI's command surface, read only through public names and ``--help`` output.

Top-level names come from :func:`specy_road.cli.registered_agent_command_names`. Every name's
``--help`` is run, and its subcommands (the ``{a,b}`` choices argparse prints, or extra words in a
usage line) are followed down, so the surface cannot drift from the CLI. From each help text the
inventory keeps the subparser path, the option strings and whether the command passes the remaining
arguments through (``argparse.REMAINDER`` prints a bare ``...``; a bare ``--`` in usage counts too).
"""

from __future__ import annotations

import functools
import itertools
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.parity.support import run_cli, transcript

MODULES = {"specy-road": "specy_road.cli", "specyrd": "specy_road.specyrd_cli"}

_SECTION = re.compile(r"^[A-Za-z][^:]*:$")
_CHOICES = re.compile(r"^  \{([^}]+)\}")
_OPTION = re.compile(r"^-{1,2}[A-Za-z0-9][\w-]*")
_WORD = re.compile(r"[a-z][a-z0-9-]*")


def _section_lines(text: str):
    """Indented lines under argparse's section headers (``options:``, ``positional arguments:``)."""
    inside = False
    for line in text.splitlines():
        if _SECTION.match(line):
            inside = True
        elif line and not line.startswith(" "):
            inside = False
        elif inside:
            yield line


def _usage(text: str) -> list[str]:
    """Tokens of the ``usage:`` block (up to its first blank line)."""
    block = text[text.find("usage:") :].split("\n\n", 1)[0] if "usage:" in text else ""
    return block.split()[1:]


def parse_help(path: tuple[str, ...], text: str) -> dict:
    """Subcommands, option strings and passthrough of one command, from its help text."""
    subs: list[str] = []
    options: set[str] = set()
    for line in _section_lines(text):
        if m := _CHOICES.match(line):
            subs += m.group(1).split(",")
        elif line.startswith("  -") and not line.startswith("   "):
            for piece in re.split(r"\s{2,}", line.strip())[0].split(", "):
                if m := _OPTION.match(piece):
                    options.add(m.group(0))
    usage = _usage(text)
    extra = usage[len(path) :]
    if not subs and usage[: len(path)] == list(path):
        # A command whose bare --help prints only a usage line naming its subcommand (plain words
        # after the path; an argparse usage has ``[-h]`` there).
        subs = list(itertools.takewhile(_WORD.fullmatch, extra))
    passthrough = "--" in usage or any(
        tok == "..." and (i == 0 or not usage[i - 1].endswith("}")) for i, tok in enumerate(usage)
    )
    return {
        "path": list(path[1:]),
        "subcommands": sorted(set(subs)),
        "options": sorted(options),
        "passthrough": passthrough,
    }


def _help(path: tuple[str, ...], cwd: Path) -> tuple[tuple[str, ...], str, str]:
    argv = [*path[1:], "--help"]
    result = run_cli(MODULES[path[0]], argv, cwd=cwd)
    text = result.stdout if result.returncode == 0 else result.stderr
    return path, transcript([*path, "--help"], result, {cwd: "<CWD>"}), text


@functools.lru_cache(maxsize=1)
def crawl() -> dict[str, dict]:
    """The whole surface: ``{"specy-road review record": {"transcript": ..., "inventory": ...}}``.

    The roots (``specy-road``, ``specyrd``) are included: their help is the command list a user
    sees. Runs from an empty directory, so no repo's state reaches the help text.
    """
    from specy_road.cli import registered_agent_command_names

    names = registered_agent_command_names()
    todo = [(prog,) for prog in sorted(names)] + [
        (prog, n) for prog in sorted(names) for n in sorted(names[prog])
    ]
    found: dict[str, dict] = {}
    with (
        tempfile.TemporaryDirectory() as tmp,
        ThreadPoolExecutor(min(8, os.cpu_count() or 1)) as pool,
    ):
        while todo:
            batch, todo = todo, []
            for path, text_out, text in pool.map(lambda p: _help(p, Path(tmp)), batch):
                inventory = parse_help(path, text)
                if len(path) == 1:
                    inventory["subcommands"] = []  # the roots' commands are the registered names
                found[" ".join(path)] = {"transcript": text_out, "inventory": inventory}
                todo += [
                    (*path, sub)
                    for sub in inventory["subcommands"]
                    if " ".join((*path, sub)) not in found
                ]
    return found
