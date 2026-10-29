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
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    def at(text: str, needle: str, nth: int = 1) -> int:
        seen = 0
        for number, line in enumerate(text.splitlines(), 1):
            if needle in line:
                seen += 1
                if seen == nth:
                    return number
        raise AssertionError(needle)

    def warning(rel: str, number: int, mention: str, advice: str) -> str:
        return f"agents: warning — {rel}:{number} tells agents to run `{mention}`, {tail} {advice}"

    assert lines == [
        warning("sr/AGENTS.md", at(agents, "grind"), "specy-road grind", "use `specy-road grind-session`."),
        warning("sr/AGENTS.md", at(agents, "Then specy-road frob."), "specy-road frob", "see `specy-road --help`."),
        warning("sr/AGENTS.md", at(agents, "- specy-road frob --flag"), "specy-road frob", "see `specy-road --help`."),
        warning("sr/AGENTS.md", at(agents, "does-not-exist"), "specy-road does-not-exist", "see `specy-road --help`."),
        warning("sr/AGENTS.md", at(agents, "nope"), "specy-road nope", "see `specy-road --help`."),
        warning("sr/AGENTS.md", at(agents, "files omit"), "specy-road files", "see `specy-road --help`."),
        warning("sr/AGENTS.md", at(agents, "specyrd refresh"), "specyrd refresh", "see `specyrd --help`."),
        warning("sr/AGENTS.md", at(agents, "pm-sync"), "specy-road pm-sync", "use `specy-road sync`."),
        warning("CLAUDE.md", at(claude, "backfill-activity"), "specy-road backfill-activity",
                "it was removed and nothing replaces it."),
    ]


def test_a_noun_phrase_is_quiet_and_a_command_is_not() -> None:
    assert unregistered_commands("Run specy-road project now.") == ["specy-road project"]
    assert unregistered_commands("other specy-road formats (templates...)") == []
    assert unregistered_commands("the specy-road toolkit is") == []
    assert unregistered_commands("Then specy-road frob.") == ["specy-road frob"]
    assert unregistered_commands("specy-road frob M1.2") == ["specy-road frob"]
    assert unregistered_commands("- the specy-road frob") == []
    assert unregistered_commands("- Use the specy-road frob") == []
    assert unregistered_commands("- specy-road frob --x") == ["specy-road frob"]
    assert unregistered_commands("- Run specy-road frob") == ["specy-road frob"]
    assert unregistered_commands(
        "- **Adoption prompts** are kept aligned with other specy-road formats that ..."
    ) == []
    assert unregistered_commands("# Please specy-road frob") == ["specy-road frob"]
    assert unregistered_commands("## the specy-road frob --x") == ["specy-road frob"]
    assert unregistered_commands("# Please specy-road frob --flag") == ["specy-road frob"]
    assert unregistered_commands("Use the specy-road frob --flag.") == ["specy-road frob"]
    assert unregistered_commands("Use the specy-road frob path/to/file.") == ["specy-road frob"]
    assert unregistered_commands('Use the specy-road frob "quoted".') == ["specy-road frob"]
    assert unregistered_commands("Use the specy-road frob M1.2.") == ["specy-road frob"]
    assert unregistered_commands("Use the specy-road frob command.") == ["specy-road frob"]
    assert unregistered_commands("Use the specy-road frob subcommand.") == ["specy-road frob"]
    assert unregistered_commands("``the specy-road frob``") == ["specy-road frob"]
    assert unregistered_commands("see ```the specy-road frob``` now") == ["specy-road frob"]
    assert unregistered_commands("``see ` the specy-road frob``") == ["specy-road frob"]
    assert unregistered_commands("````\n```\nthe specy-road frob\n````") == ["specy-road frob"]
    assert unregistered_commands("```\n~~~\nthe specy-road frob\n```") == ["specy-road frob"]
    assert unregistered_commands("```\n```bash\nspecy-road frob\n```") == ["specy-road frob"]
    assert unregistered_commands("the 2 specy-road frob") == ["specy-road frob"]
    assert unregistered_commands("the **specy-road toolkit** is") == []
    assert unregistered_commands("Run __specy-road frob__ now.") == ["specy-road frob"]
    assert unregistered_commands("- __specy-road frob__") == ["specy-road frob"]
    assert unregistered_commands("the specy-road frob @agent") == ["specy-road frob"]
    assert unregistered_commands("```the specy-road frob```") == ["specy-road frob"]
    assert unregistered_commands("Use the specy-road frob (command).") == ["specy-road frob"]
    for quiet in (
        "the specy-road toolkit.",
        "the **specy-road toolkit**.",
        "other specy-road formats, including templates",
        "the specy-road toolkit, which coordinates work",
        "the **specy-road toolkit**, which is",
        "the specy-road toolkit's design",
        "the specy-road toolkit — a library",
        "the specy-road toolkit; see docs",
        "the **specy-road** toolkit is",
        "other specy-road formats that accept --strict",
        "the specy-road toolkit is the command we use",
        "the specy-road toolkit in v2",
        "**the specy-road toolkit** is",
        "*the specy-road toolkit* is",
        "the specy-road toolkit `is`",
        "other specy-road formats that accept `--strict`",
        "specy-road frob_extra",
        "Run specy-road do_next",
    ):
        assert unregistered_commands(quiet) == [], quiet
    for warn in (
        "Run **specy-road** frob",
        "Run *specy-road* frob",
        "Run __specy-road__ frob",
        "- **specy-road** frob",
        "- *specy-road* frob",
        "Use the specy-road frob, --flag",
        "Use the specy-road frob, M1.2",
        "Use the specy-road frob, command",
        "Use the specy-road frob `M1.2`.",
        "Use the specy-road frob `path/to/file`.",
        "Use the specy-road frob `--flag`.",
        "Use the specy-road frob `command`.",
        "specy-road frob_",
    ):
        assert unregistered_commands(warn) == ["specy-road frob"], warn
    assert unregistered_commands("foo_specy-road frob") == []
    assert unregistered_commands("specy-road validate --strict") == []
    assert unregistered_commands("specy-road frob; specy-road frob") == ["specy-road frob", "specy-road frob"]


@pytest.mark.parametrize(("old", "new"), REPLACED_COMMANDS.items())
def test_each_replaced_name_is_unregistered_and_its_replacement_is_not(old: str, new: str) -> None:
    assert unregistered_commands(f"`{old}`") == [old]
    if new:
        assert unregistered_commands(f"`{new}`") == []


def test_each_occurrence_warns_with_its_line(tmp_path: Path, capsys) -> None:
    (tmp_path / "AGENTS.md").write_text("specy-road frob\nspecy-road frob\n", encoding="utf-8")
    warn_unregistered_commands(tmp_path)
    lines = [ln for ln in capsys.readouterr().err.splitlines() if "tells agents to run" in ln]
    assert len(lines) == 2
    assert "AGENTS.md:1" in lines[0] and "`specy-road frob`" in lines[0]
    assert "AGENTS.md:2" in lines[1] and "`specy-road frob`" in lines[1]


def test_the_toolkits_agent_files_report_nothing() -> None:
    for name in ("AGENTS.md", "CLAUDE.md"):
        assert unregistered_commands((REPO / name).read_text(encoding="utf-8")) == []


def test_an_agent_file_that_is_not_utf8_is_skipped(tmp_path: Path, capsys) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"\xff\xfe `specy-road nope`")
    warn_unregistered_commands(tmp_path)
    assert capsys.readouterr().err == ""
