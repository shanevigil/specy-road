"""M11.3: specy-road's own runtime directories never fail the clean-tree checks.

In rc2 field use, the ``work/.workers/`` files delegation itself writes made the executor's
clean-tree precondition fail in a fresh clone whose ``.gitignore`` predated the rule, and every
lane had to add the directory to ``.git/info/exclude`` by hand. The checks now leave those
directories out themselves, in the main checkout, a linked worktree and a separate clone, while
any other change still stops the agent.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import FAKE, wait_for_worker, worker_roster

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.agent_ignores import RUNTIME_WORK_DIRS, apply_agent_ignores
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.bundled_scripts.role_prompt_rca import dirty_check
from specy_road.init_project import run_init_project

RUNTIME_FILES = ("work/.workers/w-0001.events.jsonl", "work/.sessions/agent.yaml",
                 "work/.worktrees/thing/README.md", "work/reviews/M1.1/PACKET.md")


def _porcelain(tree: Path, command: str) -> str:
    """Run a prompt's clean-tree command (a shell line) in ``tree``."""
    argv = shlex.split(command)
    assert argv[:2] == ["git", "status"]
    return subprocess.run(argv, cwd=tree, capture_output=True, text=True, check=True).stdout


def _touch(tree: Path, rel: str) -> Path:
    path = tree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    return path


# --- A1: the prompts' commands ---------------------------------------------


@pytest.mark.parametrize("prefix", ["", "sr/"])
def test_executor_and_reviewer_checks_exclude_every_runtime_dir(prefix: str) -> None:
    command = dirty_check(prefix, "M1.1")
    for d in RUNTIME_WORK_DIRS:
        assert f"':(top,exclude){prefix}{d}'" in command
    assert f"':(top,exclude){prefix}work/brief-*.md'" in command   # the bookkeeping still left out


def _old_scaffold(tmp_path: Path) -> tuple[Path, Path]:
    """A repo whose committed ``.gitignore`` predates the runtime rules (only ``work/reviews/``)."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    return repo, script


@pytest.mark.parametrize("lane", ["main", "worktree", "clone"])
def test_the_rendered_precondition_passes_over_runtime_state_in_every_lane(tmp_path: Path, lane: str) -> None:
    repo, _script = _old_scaffold(tmp_path)
    if lane == "main":
        tree = repo
    elif lane == "worktree":
        git(repo, "checkout", "-q", "dev")
        tree = tmp_path / "wt"
        git(repo, "worktree", "add", "-q", str(tree), "feature/rm-thing")
    else:
        git(repo, "checkout", "-q", "dev")
        tree = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", "-b", "feature/rm-thing", str(repo), str(tree)], check=True)
    for rel in RUNTIME_FILES:
        _touch(tree, rel)
    assert any(line.startswith("??") for line in
               subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=tree,
                              capture_output=True, text=True, check=True).stdout.splitlines()), \
        "the old scaffold must really list the runtime state, or the test proves nothing"

    _touch(repo, "work/reviews/M1.1/PACKET.md")   # the reviewer prompt needs the main checkout's packet
    for role in ("executor", "reviewer"):
        text, _p, err = build_prompt(repo, "M1.1", role=role, model="opus" if role == "executor" else "sol")
        assert err is None, err
        line = next(ln for ln in text.splitlines() if ln.startswith("If ") and "git status" in ln)
        command = "git status" + line.split("`git status", 1)[1].split("`", 1)[0]
        assert _porcelain(tree, command) == "", f"{role} precondition in the {lane} lane"

        stray = _touch(tree, "notes.md")
        assert "?? notes.md" in _porcelain(tree, command)
        stray.unlink()


# --- A3: delegation in a fresh clone -----------------------------------------


def test_delegate_in_a_fresh_clone_passes_over_runtime_state_but_not_an_unrelated_file(tmp_path: Path) -> None:
    repo, _script = _old_scaffold(tmp_path)
    git(repo, "checkout", "-q", "dev")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "-b", "feature/rm-thing", str(repo), str(clone)], check=True)
    for rel in RUNTIME_FILES:
        _touch(clone, rel)
    stray = _touch(clone, "notes.md")

    with pytest.raises(ws.WorkerError, match=r"uncommitted changes .*notes\.md"):
        ops.delegate(repo, "M1.1", "opus", worktree=clone)
    stray.unlink()

    rec, created = ops.delegate(repo, "M1.1", "opus", worktree=clone)
    assert created and Path(rec.worktree) == clone.resolve()
    wait_for_worker(repo, rec.worker_id)
    # What delegation itself wrote (the brief) plus the runtime state leaves the executor's check empty.
    assert (clone / "work" / "brief-M1.1.md").is_file()
    assert _porcelain(clone, dirty_check("", "M1.1")) == ""
    _touch(clone, "notes.md")
    assert "?? notes.md" in _porcelain(clone, dirty_check("", "M1.1"))


# --- A2: a new project ignores them from the start ---------------------------


def test_init_project_makes_git_ignore_the_runtime_dirs(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    for rel in RUNTIME_FILES:
        _touch(tmp_path, rel)
        assert subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", rel], check=False).returncode == 0, rel


def test_refreshing_an_old_scaffold_makes_git_ignore_the_runtime_dirs(tmp_path: Path) -> None:
    """The field case: a repo scaffolded before the rules existed, brought up to date by the managed block."""
    repo, _script = _old_scaffold(tmp_path)
    apply_agent_ignores(repo, "")   # what refresh-stubs and init run
    for rel in RUNTIME_FILES:
        _touch(repo, rel)
        assert subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", rel], check=False).returncode == 0, rel
