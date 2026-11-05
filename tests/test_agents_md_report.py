"""M13.3: a pointer-only AGENTS.md section, the notice when .specyrd/AGENTS.md first arrives, per-harness totals.

Adopter feedback (sanitized): an 18-line section pushed a project file over its line cap, the first
upgrade did not say the project's own pickup rules now duplicated the new rules file, and the
Claude Code context line hid that a file was read twice.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.agents_md_block import (
    AGENTS_MD,
    RULES_MD,
    TEAM_MD,
    agents_md_block_state,
    print_injected_context,
    render_agents_lines,
)
from specy_road.bundled_scripts.refresh_stubs import main as refresh_stubs_main
from specy_road.bundled_scripts.refresh_stubs import refresh_stubs
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.init_project import run_init_project
from specy_road.managed_block import HTML_COMMENT

MANIFEST = ".specyrd/manifest.json"


def _set_agents_block(root: Path, value: str) -> None:
    path = root / MANIFEST
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data | {"agents_block": value}), encoding="utf-8")


def _section(root: Path) -> list[str]:
    """The managed section of ``AGENTS.md``, markers included."""
    lines = (root / AGENTS_MD).read_text(encoding="utf-8").splitlines()
    return lines[lines.index(HTML_COMMENT.start):lines.index(HTML_COMMENT.end) + 1]


def test_full_and_minimal_sections_render_and_refresh_stubs_honours_the_setting(tmp_path: Path, capsys) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    full = render_agents_lines(tmp_path)
    assert full == render_agents_lines()
    assert sum(ln.startswith("- **") for ln in full) == 7   # the floor bullets stay in the default
    assert len(_section(tmp_path)) == len(full) + 2

    _set_agents_block(tmp_path, "minimal")
    minimal = render_agents_lines(tmp_path)
    assert len(minimal) == 1 and minimal[0].startswith("Written by specy-road ")
    for needle in ("`.specyrd/AGENTS.md`", "`.specyrd/AGENTS.team.md`", "`.specyrd/AGENTS.local.md`"):
        assert needle in minimal[0]
    assert agents_md_block_state(tmp_path) == "stale"
    written, _orphans = refresh_stubs(tmp_path)
    assert f"{AGENTS_MD} (updated)" in written
    assert len(_section(tmp_path)) == 3 and agents_md_block_state(tmp_path) == "current"
    assert json.loads((tmp_path / MANIFEST).read_text(encoding="utf-8"))["agents_block"] == "minimal"

    capsys.readouterr()
    print_injected_context(tmp_path)
    assert "AGENTS.md" in (codex := capsys.readouterr().out.splitlines()[0])
    assert "(specy-road section 3 lines," in codex


def test_upgrade_names_project_headings_the_new_rules_file_repeats(tmp_path: Path, capsys) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    _set_agents_block(tmp_path, "minimal")
    (tmp_path / RULES_MD).unlink()
    (tmp_path / AGENTS_MD).write_text(
        "# Ours\n\n##  TASK   loop\n\nOur pickup rules.\n\n## Deploy\n", encoding="utf-8")
    refresh_stubs(tmp_path)
    (tmp_path / RULES_MD).unlink()
    capsys.readouterr()

    assert run_upgrade(tmp_path) == 0
    out = capsys.readouterr().out.splitlines()
    assert ("rules: .specyrd/AGENTS.md is new; its headings: Load order; Roadmap model; Finding things; "
            "Lean changes and tests; Task loop; Common commands") in out
    assert [ln for ln in out if ln.startswith(f"rules: {AGENTS_MD}")] == [
        f"rules: {AGENTS_MD}:3 \"TASK   loop\" (outside the specy-road section) matches a heading in {RULES_MD}"]
    assert f"rules: compare these with {RULES_MD} and drop the copy that is stale" in out
    assert len(_section(tmp_path)) == 3   # upgrade honours agents_block too

    capsys.readouterr()
    run_upgrade(tmp_path)   # the rules file exists now: no notice
    assert "rules: " not in capsys.readouterr().out


@pytest.mark.parametrize(("own", "matched"), [
    ("# Ours\n\n   ## Task loop\n", ["3 \"Task loop\""]),                       # R1: up to three spaces of indent
    ("# Ours\n\n##\tTask loop ##\n", ["3 \"Task loop\""]),                     # a tab after the run; closing #'s
    ("# Ours\n\nTask loop\n---------\n", ["3 \"Task loop\""]),                 # setext level 2
    ("# Ours\n\n```markdown\n## Task loop\n```\n", []),                       # R2: a fenced example
    ("~~~~\n## Task loop\n~~~\n```\n## Load order\n~~~~\n## Finding things\n", ["7 \"Finding things\""]),
    ("# Ours\n\n    ## Task loop\n\t## Load order\n", []),                    # indented code, not headings
    ("# Ours\n\n```\n## Task loop\n", []),                                    # an unclosed fence runs to the end
    ("- item\n---\n\nTask loop\n\n---\n", []),                                   # thematic breaks, not underlines
], ids=["indent-3", "tab-closing-run", "setext", "fenced", "fence-kinds", "indented-code", "unclosed-fence",
        "thematic-break"])
def test_refresh_stubs_names_only_real_matching_headings(tmp_path: Path, capsys, own: str, matched: list[str]) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    (tmp_path / RULES_MD).unlink()
    (tmp_path / AGENTS_MD).write_text(own, encoding="utf-8")
    capsys.readouterr()

    refresh_stubs_main(["--repo-root", str(tmp_path)])
    out = capsys.readouterr().out.splitlines()
    assert [ln.split(":", 2)[2].split(" (outside")[0] for ln in out if ln.startswith(f"rules: {AGENTS_MD}:")] == matched
    assert (f"rules: compare these with {RULES_MD} and drop the copy that is stale" in out) == bool(matched)


@pytest.mark.parametrize(("files", "note"), [
    ({AGENT_GUIDE: "# Claude\n@.specyrd/AGENTS.md\n@.specyrd/AGENTS.team.md\n",
      RULES_MD: "# rules\n@AGENTS.team.md\n", TEAM_MD: "# team\n"}, f"{TEAM_MD} imported twice"),
    ({AGENT_GUIDE: "# Claude\n@shared.md\n@shared.md\n", "shared.md": "# Shared\n"}, "shared.md imported twice"),  # R3
], ids=["two-importers", "one-importer-twice"])
def test_claude_code_total_counts_a_doubly_imported_file_once(tmp_path: Path, capsys, monkeypatch,
                                                               files: dict[str, str], note: str) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    lines, size = sum(t.count("\n") for t in files.values()), sum(len(t) for t in files.values())

    print_injected_context(tmp_path)
    claude = next(ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("context: Claude Code"))
    assert claude.endswith(f"; total {lines} lines, {size} bytes ({note}, counted once)")
