"""Options several commands declare, declared once here, and reading a parser's subcommands.

``--json``, ``--ref``, ``--model``, ``--base`` and ``--remote`` mean the same thing on every
command that takes them, so their flag, action and metavar live here. A caller passes what is its
own: a help string that says more than the default, and its required flag or default.
``tests/parity/golden/option_table.json`` pins each command's action, type, choices, required flag
and default for these options.
"""

from __future__ import annotations

import argparse

JSON_HELP = "Machine-readable output."
REF_HELP = "Branch or commit under review (default: the node's registered branch)"
MODEL_HELP = "Roster id"
BASE_HELP = "Integration branch (default: roadmap/git-workflow.yaml, else main)."
REMOTE_HELP = "Git remote (default: roadmap/git-workflow.yaml, else origin)."


def add_json_arg(
    parser: argparse.ArgumentParser, help: str = JSON_HELP, *, dest: str = "json"
) -> None:
    """``--json``: print machine-readable output instead of text."""
    parser.add_argument("--json", dest=dest, action="store_true", help=help)


def add_ref_arg(parser: argparse.ArgumentParser, help: str = REF_HELP) -> None:
    """``--ref``: the branch or commit to read instead of the node's registered branch."""
    parser.add_argument("--ref", help=help)


def add_model_arg(
    parser: argparse.ArgumentParser,
    help: str = MODEL_HELP,
    *,
    required: bool = False,
    default: str | None = None,
    append: bool = False,
) -> None:
    """``--model``: a roster id; ``append`` collects one per use, most preferred first."""
    if append:
        parser.add_argument("--model", action="append", metavar="ROSTER_ID", help=help)
    else:
        parser.add_argument("--model", required=required, default=default, help=help)


def add_base_arg(
    parser: argparse.ArgumentParser, help: str = BASE_HELP, *, metavar: str = "BRANCH"
) -> None:
    """``--base``: the integration branch (or, for a diff, the ref to diff from)."""
    parser.add_argument("--base", default=None, metavar=metavar, help=help)


def add_remote_arg(
    parser: argparse.ArgumentParser, help: str = REMOTE_HELP, *, default: str | None = None
) -> None:
    """``--remote``: the git remote to fetch from or push to."""
    parser.add_argument("--remote", default=default, metavar="NAME", help=help)


def subcommand_parsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """``parser``'s subcommand parsers by name, aliases included; empty when it has none."""
    return {
        name: sub
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
        for name, sub in action.choices.items()
    }
