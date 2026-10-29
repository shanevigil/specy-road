"""`validate` warns when a project's own AGENTS.md or CLAUDE.md names a command that does not exist."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env

from specy_road import __version__
from specy_road.agents_md_block import render_agents_lines
from specy_road.bundled_scripts.validate_roadmap import unregistered_commands, warn_unregistered_commands
from specy_road.cli import REPLACED_COMMANDS
from specy_road.managed_block import HTML_COMMENT, render_block

AGENTS_MD = """# Our agents guide

The specy-road toolkit coordinates work; run `specy-road validate` and `specy-road grind`.
Then specy-road frob.
- specy-road frob --flag
Please run specy-road does-not-exist.
the specy-road toolkit is how this repo coordinates.
specy-road validate

```bash
$ specy-road nope --flag && specy-road brief M1
# specy-road files omit the marker
specyrd refresh
specyrd init --ai claude-code
specy-road version
```
"""


def test_validate_warns_for_each_unregistered_command_and_still_passes(tmp_path: Path) -> None:
    root = tmp_path / "sr"
    shutil.copytree(DOGFOOD, root)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    block = render_block(["`specy-road gone-from-the-block`", *render_agents_lines()], style=HTML_COMMENT)
    (root / "AGENTS.md").write_text(f"{AGENTS_MD}\n{block}\nAfter the block: `specy-road pm-sync`.\n",
                                    encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Run `specy-road backfill-activity` weekly.\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_roadmap.py"), "--repo-root", str(root)],
        cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stderr.splitlines() if "tells agents to run" in ln]
    tail = f"which is not a command in specy-road {__version__};"
    assert lines == [
        f"agents: warning — sr/AGENTS.md tells agents to run `specy-road grind`, {tail} use `specy-road grind-session`.",
        f"agents: warning — sr/AGENTS.md tells agents to run `specy-road frob`, {tail} see `specy-road --help`.",
        f"agents: warning — sr/AGENTS.md tells agents to run `specy-road does-not-exist`, {tail} "
        "see `specy-road --help`.",
        f"agents: warning — sr/AGENTS.md tells agents to run `specy-road nope`, {tail} see `specy-road --help`.",
        f"agents: warning — sr/AGENTS.md tells agents to run `specy-road files`, {tail} see `specy-road --help`.",
        f"agents: warning — sr/AGENTS.md tells agents to run `specyrd refresh`, {tail} see `specyrd --help`.",
        f"agents: warning — sr/AGENTS.md tells agents to run `specy-road pm-sync`, {tail} use `specy-road sync`.",
        f"agents: warning — CLAUDE.md tells agents to run `specy-road backfill-activity`, {tail} "
        "it was removed and nothing replaces it.",
    ]


def test_a_noun_phrase_is_quiet_and_a_command_is_not() -> None:
    assert unregistered_commands("Run specy-road project now.") == ["specy-road project"]
    assert unregistered_commands("other specy-road formats (templates...)") == []
    assert unregistered_commands("the specy-road toolkit is") == []
    assert unregistered_commands("Then specy-road frob.") == ["specy-road frob"]
    assert unregistered_commands("specy-road frob M1.2") == ["specy-road frob"]
    assert unregistered_commands("- the specy-road frob") == ["specy-road frob"]
    assert unregistered_commands("specy-road validate --strict") == []


@pytest.mark.parametrize(("old", "new"), REPLACED_COMMANDS.items())
def test_each_replaced_name_is_unregistered_and_its_replacement_is_not(old: str, new: str) -> None:
    assert unregistered_commands(f"`{old}`") == [old]
    if new:
        assert unregistered_commands(f"`{new}`") == []


def test_the_toolkits_agent_files_report_nothing() -> None:
    for name in ("AGENTS.md", "CLAUDE.md"):
        assert unregistered_commands((REPO / name).read_text(encoding="utf-8")) == []


def test_an_agent_file_that_is_not_utf8_is_skipped(tmp_path: Path, capsys) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"\xff\xfe `specy-road nope`")
    warn_unregistered_commands(tmp_path)
    assert capsys.readouterr().err == ""
