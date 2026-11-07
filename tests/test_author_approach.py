"""M15.8: a promoted leaf is never stuck on an empty ``## Approach``.

Promote's placeholder sits under ``## Approach`` and says pickup skips the leaf
until it is written, naming ``specy-road author-approach <ID>``; pickup's skip
reason names the same command; ``author-approach`` prints (or with ``-o``
writes) the prompt and is otherwise read-only; both plans add one
"needs Approach" line. Sheets promoted before M15.8 are still detected.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.unauthored_repo_helpers import FILLED, git, pick_leaf, unauthored_repo

from specy_road.bundled_scripts import author_approach, orchestrate_cli
from specy_road.bundled_scripts.brainstorm_promote import seed_planning_sheet
from specy_road.bundled_scripts.brainstorm_session import Idea
from specy_road.bundled_scripts.grind_session import run_session
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.planning_sheet_bootstrap import (
    LEGACY_PROMOTE_PLACEHOLDER,
    PROMOTE_PLACEHOLDER,
    placeholder_sheet,
    promote_placeholder,
    render_feature_sheet_template,
)
from specy_road.planning_scaffold_check import scaffold_sheet

COMMAND = "`specy-road author-approach M1`"
PHASE = "## Intent\n\nShip the export to every adopter.\n\n## Approach\n\nOne leaf per format.\n"


def _scaffold_with_authored_approach(nid: str = "M1") -> str:
    raw = render_feature_sheet_template(nid)
    head, rest = raw.split("## Approach\n\n", 1)
    _scaffold_approach, tail = rest.split("\n\n## Tasks", 1)
    return f"{head}## Approach\n\nShip nightly via cron.\n\n## Tasks{tail}"


def _promoted(tmp_path: Path, **over: dict) -> tuple[Path, list[dict]]:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED}, **over)
    seed_planning_sheet(root, nodes[0], Idea(id="i-1", title="Faster export", rationale="Users wait."))
    git(root, "commit", "-qam", "promote")
    return root, nodes


def _status(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                          check=True, capture_output=True, text=True).stdout


def test_placeholder_text_says_pickup_skips_and_names_the_command() -> None:
    assert PROMOTE_PLACEHOLDER == (
        "Not written yet: pickup skips this leaf until this section is written. "
        "`specy-road author-approach <ID>` prints the prompt to write it."
    )
    assert "at pickup" not in PROMOTE_PLACEHOLDER
    assert promote_placeholder("M1") == PROMOTE_PLACEHOLDER
    assert "M1" not in promote_placeholder("M1")


def test_promote_writes_the_placeholder_under_approach_not_intent(tmp_path: Path) -> None:
    root, nodes = _promoted(tmp_path)
    text = (root / nodes[0]["planning_dir"]).read_text(encoding="utf-8")
    intent, approach = text.split("## Approach", 1)
    assert promote_placeholder("M1") in approach.split("## Tasks", 1)[0]
    assert "M1" not in text
    assert "author-approach" not in intent and LEGACY_PROMOTE_PLACEHOLDER not in intent


def test_pickup_skip_reason_names_the_same_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    root, nodes = _promoted(tmp_path, M1={"acceptance": ["works"]})
    assert pick_leaf(monkeypatch, root) == "M2"
    err = capsys.readouterr().err
    assert (f"skipping M1: {nodes[0]['planning_dir']} still has brainstorm promote's placeholder "
            f"under ## Approach; {COMMAND} prints the prompt to write it") in err
    assert "--allow-scaffold-planning" in err


def test_guard_unchanged_allow_scaffold_planning_still_picks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, _nodes = _promoted(tmp_path, M1={"acceptance": ["works"]})
    assert pick_leaf(monkeypatch, root, "--allow-scaffold-planning") == "M1"


def test_a_sheet_promoted_before_m15_8_is_still_detected(tmp_path: Path) -> None:
    old = FILLED.replace("The export writes one row per node.", f"Users wait. {LEGACY_PROMOTE_PLACEHOLDER}")
    root, nodes = unauthored_repo(tmp_path, {"M1": old})
    assert "brainstorm promote's placeholder under ## Intent" in (placeholder_sheet(root, nodes[0]) or "")
    assert scaffold_sheet(root, {**nodes[0], "acceptance": ["works"]}) == (
        f"{nodes[0]['planning_dir']} still has brainstorm promote's placeholder under ## Intent"
    )


def test_author_approach_prints_the_prompt_and_changes_nothing(tmp_path: Path, capsys) -> None:
    root, nodes = unauthored_repo(
        tmp_path, {"M1": PHASE, "M1.1": "scaffold"},
        M1={"type": "phase", "title": "Export"},
        **{"M1.1": {"parent_id": "M1", "title": "CSV export", "acceptance": ["one row per node"],
                    "touch_zones": ["src/export.py"]}},
    )
    seed_planning_sheet(root, nodes[1], Idea(id="i-1", title="CSV", rationale="Users wait."))
    git(root, "commit", "-qam", "promote")
    with pytest.raises(SystemExit) as e:
        author_approach.main(["M1.1", "--repo-root", str(root)])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for part in ("CSV export", "- **A1:** one row per node", "- `src/export.py`",
                 "### M1 — Export", "Ship the export to every adopter.",
                 "constraints, the major steps", f"git commit --only {nodes[1]['planning_dir']}"):
        assert part in out
    assert _status(root) == ""


def test_author_approach_skips_an_authored_leaf(tmp_path: Path, capsys) -> None:
    root, _nodes = _promoted(tmp_path)
    with pytest.raises(SystemExit) as e:
        author_approach.main(["M2", "M1", "--repo-root", str(root)])
    assert e.value.code == 0
    cap = capsys.readouterr()
    assert "M2: ## Approach in" in cap.err and "already written; skipped" in cap.err
    assert "# Write the ## Approach for `M1`" in cap.out and "`M2`" not in cap.out


def test_author_approach_o_writes_only_the_prompt_file(tmp_path: Path, capsys) -> None:
    root, _nodes = _promoted(tmp_path)
    with pytest.raises(SystemExit):
        author_approach.main(["M1", "M2", "-o", "--repo-root", str(root)])
    assert capsys.readouterr().out.strip() == "wrote work/prompt-approach-M1.md"
    assert "# Write the ## Approach for `M1`" in (root / "work" / "prompt-approach-M1.md").read_text()
    assert _status(root) == "?? work/prompt-approach-M1.md\n"


def test_both_plans_print_one_needs_approach_line(tmp_path: Path, capsys) -> None:
    root, _nodes = _promoted(tmp_path, M1={"acceptance": ["works"]})
    line = (f"needs Approach (pickup skips them until ## Approach is written): M1; "
            f"{COMMAND} prints the prompt to write each")
    capsys.readouterr()
    run_session(parse_grind_session_args(["--plan", "--repo-root", str(root)]))
    assert capsys.readouterr().out.count(line) == 1
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(root)])
    assert capsys.readouterr().out.count(line) == 1


def test_needs_approach_line_for_fully_scaffolded_sheets(tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    line = (f"needs Approach (pickup skips them until ## Approach is written): M1; "
            f"{COMMAND} prints the prompt to write each")
    capsys.readouterr()
    run_session(parse_grind_session_args(["--plan", "--repo-root", str(root)]))
    assert line in capsys.readouterr().out
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(root)])
    assert line in capsys.readouterr().out


def test_needs_approach_line_omits_leaves_with_authored_approach(tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": _scaffold_with_authored_approach(), "M2": FILLED})
    capsys.readouterr()
    run_session(parse_grind_session_args(["--plan", "--repo-root", str(root)]))
    assert "needs Approach" not in capsys.readouterr().out
