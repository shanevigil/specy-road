"""``roadmap/decisions.yaml`` ledger: add, list ordering, close, schema (M11.34)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts import decisions_cli
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.decisions import (
    add_entry,
    read_decisions,
    recorded_on_sheet,
    schema_errors,
    schema_path_for_write,
    sort_for_list,
)
from specy_road.init_project import project_template_root
from tests.helpers import DOGFOOD
from tests.review_repo_helpers import NODE, git

SHEET = NODE["planning_dir"]


def _decisions_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(DOGFOOD / "schemas", repo / "schemas")
    shutil.copy(
        project_template_root() / "schemas" / "decisions.schema.json",
        repo / "schemas" / "decisions.schema.json",
    )
    rm = repo / "roadmap"
    (rm / "phases").mkdir(parents=True)
    (rm / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8"
    )
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": [NODE]}), encoding="utf-8")
    sheet = repo / SHEET
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(
        "# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## Decisions and notes\n\n",
        encoding="utf-8",
    )
    git(repo, "init", "-q", "-b", "dev")
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    (rm / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n"
        "require_implementation_review_before_finish: false\n",
        encoding="utf-8",
    )
    shutil.copy(DOGFOOD / "roadmap" / "orchestration.yaml", rm / "orchestration.yaml")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    return repo


def _add_args(repo: Path) -> list[str]:
    return [
        "--repo-root",
        str(repo),
        "M1.1",
        "--kind",
        "decision",
        "--summary",
        "Which API shape",
        "--why",
        "Blocks the contract test",
        "--option",
        "REST|Stable for adopters",
        "--option",
        "RPC|Matches internal service",
        "--recommendation",
        "REST",
        "--recommendation-reason",
        "Adopters already document REST",
        "--default",
        "REST",
    ]


def test_add_writes_schema_valid_open_entry(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(["decisions", "add", *_add_args(repo)])
    assert exc.value.code == 0
    doc = read_decisions(repo / "roadmap" / "decisions.yaml")
    assert len(doc["entries"]) == 1
    e = doc["entries"][0]
    assert e["id"] == "D1" and e["status"] == "open" and e["node"] == "M1.1"
    assert not schema_errors(doc, schema_path_for_write(repo))


def test_list_orders_by_needed_by(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    add_entry(
        repo,
        node_id="M1.1",
        kind="decision",
        summary="Late",
        why_now="x",
        options=[{"label": "a", "effect": "b"}],
        recommendation="a",
        recommendation_reason="r",
        default_if_unanswered="a",
        decision_id="Dlate",
        needed_by="2026-12-01",
        asked="2026-11-01",
    )
    add_entry(
        repo,
        node_id="M1.1",
        kind="human-action",
        summary="Soon",
        why_now="y",
        options=[{"label": "c", "effect": "d"}],
        recommendation="c",
        recommendation_reason="s",
        default_if_unanswered="c",
        decision_id="Dsoon",
        needed_by="2026-11-05",
        asked="2026-11-02",
    )
    add_entry(
        repo,
        node_id="M1.1",
        kind="decision",
        summary="No deadline",
        why_now="z",
        options=[{"label": "e", "effect": "f"}],
        recommendation="e",
        recommendation_reason="t",
        default_if_unanswered="e",
        decision_id="Dnone",
        asked="2026-10-01",
    )
    ordered = [e["id"] for e in sort_for_list(read_decisions(repo / "roadmap" / "decisions.yaml")["entries"])]
    assert ordered == ["Dsoon", "Dlate", "Dnone"]

    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(["decisions", "list", "--repo-root", str(repo)])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.index("Dsoon") < out.index("Dlate") < out.index("Dnone")


def test_close_requires_sheet_record(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    add_entry(
        repo,
        node_id="M1.1",
        kind="decision",
        summary="Pick color",
        why_now="blocks theme",
        options=[{"label": "blue", "effect": "dark UI"}],
        recommendation="blue",
        recommendation_reason="contrast",
        default_if_unanswered="blue",
        decision_id="D1",
    )
    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(["decisions", "close", "D1", "--answer", "blue", "--repo-root", str(repo)])
    assert exc.value.code == 1
    assert "planning sheet has no line" in capsys.readouterr().err

    sheet_text = (repo / SHEET).read_text(encoding="utf-8") + "- D1: blue\n"
    (repo / SHEET).write_text(sheet_text, encoding="utf-8")
    assert recorded_on_sheet(sheet_text, "D1", "blue")

    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(["decisions", "close", "D1", "--answer", "blue", "--repo-root", str(repo)])
    assert exc.value.code == 0
    closed = read_decisions(repo / "roadmap" / "decisions.yaml")["entries"][0]
    assert closed["status"] == "closed" and closed["answer"] == "blue" and closed.get("closed")


def test_schema_rejects_invalid_document(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    bad = {"version": 1, "entries": [{"id": "D1", "node": "M1.1", "status": "open"}]}
    errs = schema_errors(bad, schema_path_for_write(repo))
    assert errs


def test_coordinator_prompt_mentions_decisions_list(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    text, _, err = build_prompt(repo, "M1.1", role="coordinator", model="human")
    assert err is None
    assert "specy-road decisions list" in text
    assert "Decisions waiting on you" in text
