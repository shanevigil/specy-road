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
    tracked = repo / "work" / "README.md"
    tracked.write_text("# tracked work file\n")
    git(repo, "add", "work/README.md")
    git(repo, "commit", "-qm", "tracked work file")
    (repo / "work" / "brief-M1.1.md").write_text("# brief\n")                 # do-next-available-task
    (repo / "work" / "implementation-summary-M1.1.md").write_text("Did it.\n")  # the executor
    (repo / "work" / "prompt-M1.1.md").write_text("# coordinator prompt\n")
    (repo / "work" / "prompt-M1.1-reviewer-rev.md").write_text("# prompt\n")   # the coordinator's
    reviews_dir(repo, "M1.1").mkdir(parents=True)
    (reviews_dir(repo, "M1.1") / PACKET_NAME).write_text("# packet\n")
    text, _prof, err = build_prompt(repo, "M1.1", role="reviewer", model="rev")
    assert err is None
    check = re.search(r"or `(git status [^`]+)` lists changes you did not make", text).group(1)

    def dirty(where: Path) -> str:
        return subprocess.run(check, shell=True, cwd=where, capture_output=True, text=True, check=True).stdout

    assert dirty(repo) == ""
    tracked.write_text("# changed tracked work file\n")
    assert dirty(repo) == " M work/README.md\n"   # work/ is not wholly hidden
    tracked.write_text("# tracked work file\n")
    other_prompt = repo / "work" / "prompt-M1.2.md"
    other_prompt.write_text("# another leaf\n")
    assert dirty(repo) == "?? work/prompt-M1.2.md\n"   # only this leaf's prompts are bookkeeping
    other_prompt.unlink()
    (repo / "src" / "b.py").write_text("x = 1\n")
    assert dirty(repo) == "?? src/b.py\n"
    assert dirty(repo / "work") == "?? src/b.py\n"   # the same from a subdirectory (pathspecs are top-anchored)


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
    finished = git(repo, "rev-parse", "HEAD")
    commit_file(repo, "src/late.py", "x = 2\n", "after review")   # never reviewed
    landed_before = git(bare, "rev-parse", "dev")
    assert _finish(repo) == 1
    assert "new commits need review" in capsys.readouterr().err
    assert git(bare, "rev-parse", "dev") == landed_before   # nothing pushed
    git(repo, "reset", "-q", "--hard", finished)
    (repo / "src" / "amended.py").write_text("x = 3\n")   # amended into the finish commit itself
    git(repo, "add", "src/amended.py")
    git(repo, "commit", "-q", "--amend", "--no-edit")
    assert _finish(repo) == 1
    assert "new commits need review" in capsys.readouterr().err
    git(repo, "reset", "-q", "--hard", finished)
    assert _finish(repo) == 0
    assert "[ok] merged feature/rm-thing into dev and pushed to origin" in capsys.readouterr().out
    git(bare, "merge-base", "--is-ancestor", git(repo, "rev-parse", "feature/rm-thing"), "dev")
    assert _finish(repo) == 0   # a further re-run lands nothing and says so
    assert "already merged into dev on origin; nothing to do" in capsys.readouterr().out
