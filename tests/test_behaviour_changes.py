"""M13.8: behaviour-change catalogue (lint moved to M13.14)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.behaviour_changes import CATALOGUE
from specy_road.cli import registered_agent_command_names

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("command", sorted({entry.command for entry in CATALOGUE}))
def test_every_entry_names_a_registered_command_and_flag(command: str) -> None:
    assert command in registered_agent_command_names()["specy-road"]
    proc = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", command, "--help"],
        capture_output=True, text=True, check=True, cwd=REPO,
    )
    known = set(re.findall(r"--[a-z][a-z-]*", proc.stdout))
    for entry in CATALOGUE:
        if entry.command == command:
            assert entry.flags and set(entry.flags) <= known, (entry, known)


def test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work() -> None:
    entry = next(e for e in CATALOGUE if e.flags == ("--base",))
    hits = [
        f"{path.relative_to(REPO)}:{n}"
        for top in ("docs", "specy_road/templates")
        for path in sorted((REPO / top).rglob("*"))
        if path.is_file()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if entry.contradicted_by(line)
    ]
    assert hits == []
