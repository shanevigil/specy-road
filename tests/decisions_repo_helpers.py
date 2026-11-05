"""Shared fixtures for the ``specy-road decisions`` tests: a seeded repo, the CLI runner, a full ``add`` argv."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts import decisions_cli
from specy_road.init_project import project_template_root
from tests.helpers import DOGFOOD
from tests.review_repo_helpers import NODE, git

SHEET = NODE["planning_dir"]


def decisions_repo(tmp_path: Path) -> Path:
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


def run_decisions(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(argv)
    return int(exc.value.code or 0)


def add_args(repo: Path, *extra: str) -> list[str]:
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
