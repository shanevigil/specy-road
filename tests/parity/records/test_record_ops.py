"""Each public read, add and update of a chore, decision or lesson record gives the bytes and the
data it gave at pickup.

One row per operation, on a repo seeded from ``fixtures/``: a ledger with every entry kind (an
expired preference, a standing rule, an operator decision and a coordinator decision) and this
clone's overlay, a lessons file with prose around its lessons, and a chore mid-execution. A row's
golden holds what the call returned (or raised, or printed) and then every record file it left,
byte for byte. The wall clock is frozen through :mod:`specy_road.clock` and every ``asked`` is
passed, so a golden depends on the fixtures alone.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import shutil
import subprocess
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from specy_road.orchestration.records.chore_garden_due import garden_due
from specy_road.orchestration.records.chore_records import (
    chore_node,
    chore_prompt,
    chore_target,
    chores_dir,
    load_chore,
    open_chore,
)
from specy_road.orchestration.records.decisions import (
    active_preferences,
    add_entry,
    add_preference,
    close_entry,
    coordinator_decision_lines,
    decisions_path,
    format_open_entry,
    format_preference,
    load_checked_decisions,
    next_decision_id,
    notice_decisions_naming_no_node,
    open_entries,
    open_questions,
    plan_preferences,
    preference_active,
    read_decisions,
    recorded_on_sheet,
    sort_for_list,
    standing_rule_active,
    write_decisions,
)
from specy_road.orchestration.records.decisions import load_merged, next_free_id
from specy_road.orchestration import WorkerError
from specy_road.orchestration.records.review_lessons import (
    add_lesson,
    format_lesson,
    lessons_path,
    parse_lessons,
    read_lessons,
    reviewer_lesson_lines,
)
from tests.parity.support import check_golden

pytestmark = pytest.mark.parity

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"
NOW = "2026-11-14T12:00:00+00:00"
TODAY = date(2026, 11, 14)
#: The record files a row's golden lists after the call, in this order.
RECORD_FILES = (
    "roadmap/decisions.yaml",
    "roadmap/decisions.local.yaml",
    "constraints/review-lessons.md",
)
SHEET = (
    "# M1.1\n\n```\n## Decisions\nD1: yaml\n```\n\n"
    "## Decisions and notes\n\n- D1: yaml\n- D2 : signed\n"
)
OPERATOR_ENTRY = {
    "id": "D5",
    "node": "M1.1",
    "kind": "decision",
    "summary": "accept M1.1 at 0123456789ab (operator decision)",
    "why_now": "the operator decided the review outcome in plain words",
    "options": [
        {"label": "accept", "effect": "settles the named blocks"},
        {"label": "keep reviewing", "effect": "the blocks still count"},
    ],
    "recommendation": "accept",
    "recommendation_reason": "decided by the operator",
    "default_if_unanswered": "keep reviewing",
    "asked": "2026-11-14",
    "status": "closed",
    "answer": "accept for commit 0123456789ab",
    "closed": NOW,
    "decided_by": "operator",
    "channel": "terminal",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@dataclasses.dataclass
class Seeded:
    root: Path
    worktree: Path
    head: str


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Seeded:
    """The fixtures laid out as a project: ledgers, lessons file, chore and a garden cadence."""
    monkeypatch.setattr("specy_road.clock.utc_now_iso", lambda: NOW)
    wt = tmp_path / "wt"
    wt.mkdir()
    _git(wt, "init", "-q", "-b", "main")
    _git(
        wt,
        "-c",
        "user.email=p@example.com",
        "-c",
        "user.name=P",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "base",
    )
    head = _git(wt, "rev-parse", "HEAD")
    root = tmp_path / "repo"
    (root / "roadmap").mkdir(parents=True)
    (root / "constraints").mkdir()
    shutil.copy(FIXTURES / "decisions.yaml", root / "roadmap" / "decisions.yaml")
    shutil.copy(FIXTURES / "decisions.local.yaml", root / "roadmap" / "decisions.local.yaml")
    shutil.copy(FIXTURES / "review-lessons.md", root / "constraints" / "review-lessons.md")
    (root / "roadmap" / "orchestration.yaml").write_text(
        "version: 1\npolicy:\n  garden_cadence_days: 7\n", encoding="utf-8"
    )
    chores = chores_dir(root)
    chores.mkdir(parents=True)
    chore = (FIXTURES / "chore-mid.json").read_text(encoding="utf-8")
    (chores / "tidy-docs.json").write_text(
        chore.replace("{worktree}", str(wt)).replace("{base}", head), encoding="utf-8"
    )
    closed = json.loads((chores / "tidy-docs.json").read_text(encoding="utf-8"))
    closed.update(slug="old-chore", closed_at="2026-11-11T09:00:00+00:00")
    (chores / "old-chore.json").write_text(json.dumps(closed, indent=2) + "\n", encoding="utf-8")
    return Seeded(root, wt, head)


def _ids(entries: list[dict[str, Any]]) -> list[str]:
    return [e["id"] for e in entries]


def _doc(s: Seeded, local: bool = False) -> dict[str, Any]:
    return read_decisions(decisions_path(s.root, local))


def _merged(s: Seeded) -> Any:
    doc, local_ids, errs = load_merged(s.root)
    return {"doc": doc, "local_ids": sorted(local_ids), "errs": errs}


def _flags(s: Seeded) -> Any:
    entries = _doc(s)["entries"]
    return {e["id"]: [preference_active(e, TODAY), standing_rule_active(e, TODAY)] for e in entries}


def _notice(s: Seeded) -> Any:
    notice_decisions_naming_no_node(s.root, {"M1.1"}, TODAY)


def _unreadable_lessons(s: Seeded) -> Any:
    lessons_path(s.root).write_bytes(b"- \xff not utf-8\n")
    return reviewer_lesson_lines(s.root)


def _missing_lessons(s: Seeded) -> Any:
    lessons_path(s.root).unlink()
    return {"read": read_lessons(lessons_path(s.root)), "prompt": reviewer_lesson_lines(s.root)}


def _add_lesson_new_file(s: Seeded) -> Any:
    lessons_path(s.root).unlink()
    return add_lesson(s.root, rule="  One   line  ", example="seen in M2", from_node="M2.1")


def _garden(s: Seeded, record: str | None) -> Any:
    if record is not None:
        (chores_dir(s.root) / ".garden.json").write_text(record, encoding="utf-8")
    return garden_due(s.root, TODAY)


def _operator_append(s: Seeded) -> Any:
    """The ledger update ``review operator-decision`` makes: read, append, write."""
    path = decisions_path(s.root)
    doc = read_decisions(path)
    doc["entries"].append(dict(OPERATOR_ENTRY))
    write_decisions(path, doc)


ROWS: dict[str, Callable[[Seeded], Any]] = {
    # decisions: reads
    "decisions-read": _doc,
    "decisions-read-local": lambda s: _doc(s, local=True),
    "decisions-read-missing": lambda s: read_decisions(s.root / "roadmap" / "absent.yaml"),
    "decisions-load-checked": lambda s: load_checked_decisions(s.root),
    "decisions-views": lambda s: {
        "open": _ids(open_entries(_doc(s))),
        "questions": _ids(open_questions(_doc(s))),
        "active_preferences": _ids(active_preferences(_doc(s), TODAY)),
        "sorted": _ids(sort_for_list(_doc(s)["entries"])),
    },
    "decisions-active-flags": _flags,
    "decisions-ids": lambda s: {
        "D": next_decision_id(_doc(s)),
        "P": next_decision_id(_doc(s), "P"),
        "free_P": next_free_id(s.root, "P"),
        "free_D": next_free_id(s.root, "D"),
        "free_R": next_free_id(s.root, "R"),
    },
    "decisions-format": lambda s: (
        [format_open_entry(e) for e in open_questions(_doc(s))]
        + [format_preference(e) for e in _doc(s)["entries"] if e["kind"] == "preference"]
    ),
    "decisions-merged": _merged,
    "decisions-plan-preferences": lambda s: plan_preferences(s.root, TODAY),
    "decisions-notice": _notice,
    "decisions-recorded-on-sheet": lambda s: [
        recorded_on_sheet(SHEET, i, a)
        for i, a in (("D1", "yaml"), ("D2", "signed"), ("D1", "sqlite"))
    ],
    "decisions-coordinator-lines": lambda s: coordinator_decision_lines(),
    # decisions: adds and updates
    "decisions-add-entry": lambda s: add_entry(
        s.root,
        node_id="M1.1",
        kind="decision",
        summary=" Pick a name ",
        why_now=" naming blocks A2 ",
        options=[{"label": "a", "effect": "x"}, {"label": "b", "effect": "y"}],
        recommendation="a",
        recommendation_reason="short",
        default_if_unanswered="a",
        needed_by="2026-12-01",
        asked="2026-11-14",
    ),
    "decisions-add-entry-local-criterion": lambda s: add_entry(
        s.root,
        node_id="M1.1",
        kind="human-action",
        summary="Sign it",
        why_now="A1",
        local=True,
        options=[{"label": "signed", "effect": "finish"}],
        recommendation="signed",
        recommendation_reason="sent",
        default_if_unanswered="wait",
        decision_id="D9",
        asked="2026-11-14",
        criterion="A1",
    ),
    "decisions-add-entry-duplicate": lambda s: add_entry(
        s.root,
        node_id="M1.1",
        kind="decision",
        summary="x",
        why_now="x",
        options=[{"label": "a", "effect": "b"}],
        recommendation="a",
        recommendation_reason="b",
        default_if_unanswered="a",
        decision_id="D1",
        asked="2026-11-14",
    ),
    "decisions-add-preference": lambda s: add_preference(
        s.root,
        summary=" Data leaves to mid-2 ",
        role="executor",
        models=["mid-2", "cheap-1"],
        applies_to=["data"],
        expires="2026-12-31",
        why=" cheaper ",
        node_id="M1.1",
        asked="2026-11-14",
    ),
    "decisions-add-preference-supersedes": lambda s: add_preference(
        s.root,
        summary="Docs to mid-2",
        role="executor",
        models=["mid-2"],
        supersedes="P1",
        asked="2026-11-14",
    ),
    "decisions-add-preference-local": lambda s: add_preference(
        s.root, summary="Here only", preference_id="P7", local=True, asked="2026-11-14"
    ),
    "decisions-add-standing-rule": lambda s: add_preference(
        s.root,
        summary="Accept style-only blocks",
        why='"accept style blocks" (operator)',
        preference_id="R2",
        expires="2026-11-30T18:00:00+00:00",
        kind="standing-rule",
        asked="2026-11-14",
    ),
    "decisions-add-preference-bad-supersedes": lambda s: add_preference(
        s.root, summary="x", supersedes="R1", asked="2026-11-14"
    ),
    "decisions-add-preference-bad-expires": lambda s: add_preference(
        s.root, summary="x", expires="soon-ish!", asked="2026-11-14"
    ),
    "decisions-close": lambda s: close_entry(
        s.root, "D1", " yaml ", decided_by="operator", channel="terminal"
    ),
    "decisions-close-local": lambda s: close_entry(s.root, "P4", "dropped", local=True),
    "decisions-close-closed": lambda s: close_entry(s.root, "D3", "again"),
    "decisions-close-missing": lambda s: close_entry(s.root, "D99", "none"),
    "decisions-write-invalid": lambda s: write_decisions(
        decisions_path(s.root), {"version": 1, "entries": [{}]}
    ),
    "decisions-operator-append": _operator_append,
    # lessons
    "lessons-read": lambda s: read_lessons(lessons_path(s.root)),
    "lessons-parse-no-section": lambda s: parse_lessons("# Title\n\n- prose only\n"),
    "lessons-format": lambda s: [format_lesson(e) for e in read_lessons(lessons_path(s.root))],
    "lessons-reviewer-lines": lambda s: reviewer_lesson_lines(s.root),
    "lessons-reviewer-lines-unreadable": _unreadable_lessons,
    "lessons-missing": _missing_lessons,
    "lessons-add": lambda s: add_lesson(
        s.root, rule="Name the file in every error", example="x", from_node="M4.4"
    ),
    "lessons-add-rule-only": lambda s: add_lesson(s.root, rule="Keep ids stable"),
    "lessons-add-new-file": _add_lesson_new_file,
    "lessons-add-bad-from": lambda s: add_lesson(s.root, rule="x", from_node="not a node"),
    "lessons-add-empty-rule": lambda s: add_lesson(s.root, rule="   "),
    # chores
    "chore-load": lambda s: load_chore(s.root, "tidy-docs"),
    "chore-load-not-a-slug": lambda s: [
        load_chore(s.root, "M1.1"),
        load_chore(s.root, "w-1"),
        load_chore(s.root, "absent"),
    ],
    "chore-open": lambda s: open_chore(s.root, "tidy-docs"),
    "chore-open-closed": lambda s: open_chore(s.root, "old-chore"),
    "chore-node": lambda s: chore_node(load_chore(s.root, "tidy-docs")),
    "chore-target": lambda s: dataclasses.asdict(
        chore_target(s.root, load_chore(s.root, "tidy-docs"))
    ),
    "chore-prompt-executor": lambda s: chore_prompt(
        load_chore(s.root, "tidy-docs"), "executor", "cheap-1", s.root
    ),
    "chore-prompt-reviewer": lambda s: chore_prompt(
        load_chore(s.root, "tidy-docs"), "reviewer", "slow-3", s.root, commit="feedface"
    ),
    "chore-garden-never": lambda s: _garden(s, None),
    "chore-garden-due": lambda s: _garden(s, '{"last_run": "2026-11-01"}\n'),
    "chore-garden-not-due": lambda s: _garden(s, '{"last_run": "2026-11-10"}\n'),
    "chore-garden-unreadable": lambda s: _garden(s, "not json\n"),
}


def _call(fn: Callable[[Seeded], Any], s: Seeded) -> str:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = "returned:\n" + json.dumps(fn(s), indent=2, sort_keys=True, default=str)
        except (ValueError, WorkerError) as e:
            result = f"raised {type(e).__name__}: {e}"
        except SystemExit as e:
            result = f"exit {e.code}"
    return f"{result}\nstdout:\n{out.getvalue()}stderr:\n{err.getvalue()}"


def _files(s: Seeded) -> str:
    chores = sorted(p.relative_to(s.root).as_posix() for p in chores_dir(s.root).iterdir())
    parts = []
    for rel in (*RECORD_FILES, *chores):
        path = s.root / rel
        parts.append(
            f"--- {rel}\n"
            + (
                path.read_bytes().decode("utf-8", "backslashreplace")
                if path.is_file()
                else "(absent)\n"
            )
        )
    return "".join(parts)


@pytest.mark.parametrize("name", ROWS)
def test_record_operation_matches_its_golden(name: str, seeded: Seeded) -> None:
    """The call's result, output and every record file it left.

    Temporary paths and the chore's head are masked.
    """
    text = _call(ROWS[name], seeded) + _files(seeded)
    text = text.replace(str(seeded.worktree.parent), "<tmp>").replace(seeded.head, "<head>")
    check_golden(GOLDEN / f"{name}.txt", text)
