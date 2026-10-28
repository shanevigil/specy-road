"""Pre-release §2 findings: reviewer precondition, merge-landing retry, work/ file cleanup."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road.bundled_scripts import finish_task
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: rev, family: openai, roles: [reviewer]}
policy: {reviewers_required: 1}
"""


def test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    (repo / "work").mkdir()
    (repo / "work" / "brief-M1.1.md").write_text("# brief\n")                 # do-next-available-task
    (repo / "work" / "implementation-summary-M1.1.md").write_text("Did it.\n")  # the executor
    reviews_dir(repo, "M1.1").mkdir(parents=True)
    (reviews_dir(repo, "M1.1") / PACKET_NAME).write_text("# packet\n")
    text, _prof, err = build_prompt(repo, "M1.1", role="reviewer", model="rev")
    assert err is None
    check = re.search(r"or `(git status [^`]+)` lists changes you did not make", text).group(1)

    def dirty() -> str:
        return subprocess.run(check, shell=True, cwd=repo, capture_output=True, text=True, check=True).stdout

    assert dirty() == ""
    (repo / "src" / "b.py").write_text("x = 1\n")
    assert dirty() == "?? src/b.py\n"


def _finish(repo: Path, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        finish_task.main([*args, "--repo-root", str(repo)])
        raise SystemExit(0)
    return e.value.code or 0


def test_rerunning_finish_retries_a_failed_merge_landing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n", "merge mode")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")   # the landing's push is refused
    hook.chmod(0o755)
    assert _finish(repo) == 1
    assert "run `specy-road finish-this-task --on-complete merge` again" in capsys.readouterr().err
    hook.unlink()
    assert _finish(repo) == 0
    assert "[ok] merged feature/rm-thing into dev and pushed to origin" in capsys.readouterr().out
    git(bare, "merge-base", "--is-ancestor", git(repo, "rev-parse", "feature/rm-thing"), "dev")
