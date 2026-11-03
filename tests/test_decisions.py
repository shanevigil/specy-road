"""``roadmap/decisions.yaml`` ledger: add, list ordering, close, schema (M11.34)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts import decisions_cli
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.decisions import read_decisions
from specy_road.init_project import project_template_root
from specy_road.runtime_paths import specy_road_package_dir
from tests.helpers import DOGFOOD
from tests.review_repo_helpers import NODE, git

SHEET = NODE["planning_dir"]
SKILL = specy_road_package_dir() / "templates" / "specyrd" / "commands" / "specyrd-orchestrate.md"


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


def _run(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(argv)
    return int(exc.value.code or 0)


def _add_args(repo: Path, *extra: str) -> list[str]:
    return [
        "decisions",
        "add",
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
        *extra,
    ]


def test_add_writes_schema_valid_open_entry(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_add_args(repo)) == 0
    doc = read_decisions(repo / "roadmap" / "decisions.yaml")
    assert len(doc["entries"]) == 1
    e = doc["entries"][0]
    assert e["id"] == "D1" and e["status"] == "open" and e["node"] == "M1.1"


def test_list_orders_by_needed_by(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_add_args(
        repo, "--id", "Dlate", "--needed-by", "2026-12-01", "--asked", "2026-11-01",
        "--summary", "Late",
    )) == 0
    soon = [
        "decisions", "add", "--repo-root", str(repo), "M1.1",
        "--kind", "human-action", "--summary", "Soon", "--why", "y",
        "--option", "c|d", "--recommendation", "c", "--recommendation-reason", "s",
        "--default", "c", "--id", "Dsoon", "--needed-by", "2026-11-05", "--asked", "2026-11-02",
    ]
    none = [
        "decisions", "add", "--repo-root", str(repo), "M1.1",
        "--kind", "decision", "--summary", "No deadline", "--why", "z",
        "--option", "e|f", "--recommendation", "e", "--recommendation-reason", "t",
        "--default", "e", "--id", "Dnone", "--asked", "2026-10-01",
    ]
    assert _run(soon) == 0
    assert _run(none) == 0
    capsys.readouterr()

    assert _run(["decisions", "list", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert out.index("Dsoon") < out.index("Dlate") < out.index("Dnone")


def test_close_requires_decision_block_record(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_add_args(repo, "--id", "D1", "--summary", "Pick color")) == 0
    capsys.readouterr()

    (repo / SHEET).write_text(
        "# M1.1 Thing\n\n## Intent\n\nD1: blue\n\n## Decisions and notes\n\n",
        encoding="utf-8",
    )
    assert _run(["decisions", "close", "D1", "--answer", "blue", "--repo-root", str(repo)]) == 1
    assert "planning sheet decision block has no line" in capsys.readouterr().err
    assert read_decisions(repo / "roadmap" / "decisions.yaml")["entries"][0]["status"] == "open"

    (repo / SHEET).write_text(
        "# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## Decisions and notes\n\n"
        "```\nD1: blue\n```\n",
        encoding="utf-8",
    )
    assert _run(["decisions", "close", "D1", "--answer", "blue", "--repo-root", str(repo)]) == 1
    assert "planning sheet decision block has no line" in capsys.readouterr().err
    assert read_decisions(repo / "roadmap" / "decisions.yaml")["entries"][0]["status"] == "open"

    (repo / SHEET).write_text(
        "# M1.1 Thing\n\n## Intent\n\nD1: blue\n\n## Decisions and notes\n\n- D1: blue\n",
        encoding="utf-8",
    )
    assert _run(["decisions", "close", "D1", "--answer", "blue", "--repo-root", str(repo)]) == 0
    closed = read_decisions(repo / "roadmap" / "decisions.yaml")["entries"][0]
    assert closed["status"] == "closed" and closed["answer"] == "blue" and closed.get("closed")


@pytest.mark.parametrize("flag,value", [("--asked", "not-a-date"), ("--needed-by", "tomorrow-ish")])
def test_add_rejects_malformed_dates(tmp_path: Path, capsys, flag: str, value: str) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_add_args(repo, flag, value)) == 1
    err = capsys.readouterr().err
    assert "ISO date YYYY-MM-DD" in err
    assert not (repo / "roadmap" / "decisions.yaml").is_file()


def test_list_rejects_malformed_asked_in_ledger(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    (repo / "roadmap" / "decisions.yaml").write_text(
        "version: 1\n"
        "entries:\n"
        "  - id: D1\n"
        "    node: M1.1\n"
        "    kind: decision\n"
        "    summary: x\n"
        "    why_now: y\n"
        "    options:\n"
        "      - label: a\n"
        "        effect: b\n"
        "    recommendation: a\n"
        "    recommendation_reason: r\n"
        "    default_if_unanswered: a\n"
        "    asked: not-a-date\n"
        "    status: open\n",
        encoding="utf-8",
    )
    assert _run(["decisions", "list", "--repo-root", str(repo)]) == 1
    assert "decisions.schema:" in capsys.readouterr().err


def test_schema_rejects_incomplete_document(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    (repo / "roadmap" / "decisions.yaml").write_text(
        "version: 1\nentries:\n  - id: D1\n    node: M1.1\n    status: open\n",
        encoding="utf-8",
    )
    assert _run(["decisions", "list", "--repo-root", str(repo)]) == 1
    assert "decisions.schema:" in capsys.readouterr().err


def test_coordinator_prompt_and_skill_name_kind_and_shape(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    text, _, err = build_prompt(repo, "M1.1", role="coordinator", model="human")
    assert err is None
    skill = SKILL.read_text(encoding="utf-8")
    for blob in (text, skill):
        assert "specy-road decisions list" in blob
        assert "Decisions waiting on you" in blob
        assert '--kind planning' in blob
        assert "--scope planning" not in blob
        assert "why now" in blob.lower()
        assert "recommendation" in blob.lower()
        assert "default" in blob.lower()
        assert "needed-by" in blob or "deadline" in blob.lower()


def test_documented_search_kind_planning(tmp_path: Path) -> None:
    from specy_road.bundled_scripts.search_cli import main as search_main

    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    with pytest.raises(SystemExit) as exc:
        search_main(["search", "contract", "--kind", "planning", "--repo-root", str(dest)])
    assert int(exc.value.code or 0) == 0
