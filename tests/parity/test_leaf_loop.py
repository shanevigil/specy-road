"""One leaf from ``init project`` to ``finish-this-task``, once per landing mode, offline.

After each CLI step the run records its exit code, the registry rows (checkout and integration
branch), the leaf's status (checkout and integration branch) and the git state, and compares the
list with ``golden/leaf_loop/<mode>.json``, recorded from today's behaviour. The merge run must also
end at exit 0 with the leaf Complete, its registry row gone and the feature branch merged.

Nothing reaches a hosting service: ``gh`` and ``glab`` on PATH only log that they were called, and
git may use the file protocol only (the remote is a local bare repo).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.parity.support import GOLDEN, check_golden, cli_env, normalise, run_cli

pytestmark = pytest.mark.parity

LEAF, PARENT = "M1.2", "M1"
FEATURE = "feature/rm-write-the-hello-module"
ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator]}
  - {id: exec-a, family: vendor-a, roles: [executor]}
  - {id: rev-b, family: vendor-b, roles: [reviewer]}
  - {id: rev-c, family: vendor-c, roles: [reviewer]}
policy:
  reviewers_required: 2
  count_human_filed_reviews: true
"""
SHEET = (
    "## Intent\n\nA hello module the app can import.\n\n## Approach\n\nWrite src/hello.py; "
    "the ready check proves it exists.\n\n## Tasks / checklist\n\n- [ ] src/hello.py exists\n\n"
    "## References\n\n- Roadmap chunk for `M1.2`\n"
)


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True
    ).stdout.strip()


def _offline_env(tmp: Path) -> dict[str, str]:
    """``gh``/``glab`` stand-ins that log each call, first on PATH; git limited to local remotes."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    for tool in ("gh", "glab"):
        stub = bin_dir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{tmp / "hosting-calls.log"}"\nexit 1\n')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return cli_env(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", GIT_ALLOW_PROTOCOL="file")


class Loop:
    """A temp project plus its bare ``origin``, driven through the CLI step by step."""

    def __init__(self, tmp: Path, mode: str) -> None:
        self.tmp, self.mode = tmp, mode
        self.root, self.origin = tmp / "app", tmp / "origin.git"
        self.env = _offline_env(tmp)
        self.steps: list[dict] = []

    def cli(self, step: str, *argv: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        if argv[0] != "init":  # init project takes the target path instead
            argv = (*argv, "--repo-root", str(self.root))
        result = run_cli("specy_road.cli", list(argv), cwd=self.root, env=self.env)
        assert result.returncode == expect, (
            f"{step}: exit {result.returncode}\n{result.stdout}\n{result.stderr}"
        )
        self.steps.append({"step": step, "exit": result.returncode, **self.state()})
        return result

    def _show(self, ref: str | None, rel: str) -> str | None:
        if ref is None:
            path = self.root / rel
            return path.read_text(encoding="utf-8") if path.is_file() else None
        r = subprocess.run(
            ["git", "show", f"{ref}:{rel}"], cwd=self.root, capture_output=True, text=True
        )
        return r.stdout if r.returncode == 0 else None

    def _registry(self, ref: str | None) -> list[dict]:
        doc = yaml.safe_load(self._show(ref, "roadmap/registry.yaml") or "") or {}
        return [
            {k: e.get(k) for k in ("node_id", "branch", "implementation_review")}
            for e in doc.get("entries") or []
        ]

    def leaf(self, ref: str | None) -> dict:
        nodes = json.loads(self._show(ref, "roadmap/phases/M1.json") or '{"nodes": []}')["nodes"]
        return next((n for n in nodes if n["id"] == LEAF), {})

    def _merged(self, repo: Path, into: str) -> bool | None:
        """Whether the local feature tip is in ``into`` of ``repo``; None when either is absent."""
        tip = _git(self.root, "rev-parse", "--verify", "-q", FEATURE, check=False)
        if not tip or not repo.is_dir():
            return None
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", tip, into], cwd=repo, capture_output=True
        )
        return {0: True, 1: False}.get(r.returncode)

    def state(self) -> dict:
        branches = _git(
            self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads"
        ).splitlines()
        state = {
            "registry": {"checkout": self._registry(None), "main": self._registry("main")},
            "status": {
                "checkout": self.leaf(None).get("status"),
                "main": self.leaf("main").get("status"),
            },
            "git": {
                "branch": _git(self.root, "branch", "--show-current"),
                "branches": sorted(branches),
                "origin_branches": sorted(
                    _git(
                        self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads"
                    ).splitlines()
                )
                if self.origin.is_dir()
                else [],
                "merged_into_main": self._merged(self.root, "main"),
                "merged_into_origin_main": self._merged(self.origin, "main"),
                "head_subject": _git(self.root, "log", "-1", "--format=%s", check=False),
                "worktree": sorted(_git(self.root, "status", "--porcelain").splitlines()),
            },
        }
        key = self.leaf(None).get("node_key")  # add-node draws a random one
        return json.loads(normalise(json.dumps(state), {key: "<NODE_KEY>"} if key else {}))

    def commit(self, message: str, *paths: str) -> None:
        _git(self.root, "add", *paths)
        _git(self.root, "commit", "-qm", message)


def _set_up(loop: Loop) -> None:
    """``init project`` in a fresh repo, roster and landing mode set, pushed to a bare origin."""
    root = loop.root
    _git(loop.tmp, "init", "-q", "-b", "main", str(root))
    _git(root, "config", "user.email", "parity@example.com")
    _git(root, "config", "user.name", "Parity")
    loop.cli("init project", "init", "project", str(root))
    (root / "roadmap" / "orchestration.yaml").write_text(ROSTER, encoding="utf-8")
    workflow = root / "roadmap" / "git-workflow.yaml"
    text = workflow.read_text(encoding="utf-8")
    assert "\non_complete: pr\n" in text
    workflow.write_text(
        text.replace("\non_complete: pr\n", f"\non_complete: {loop.mode}\n"), encoding="utf-8"
    )
    loop.commit("specy-road init", "-A")
    _git(loop.tmp, "init", "-q", "--bare", str(loop.origin))
    _git(root, "remote", "add", "origin", str(loop.origin))
    _git(root, "push", "-q", "-u", "origin", "main")
    _git(root, "remote", "set-head", "origin", "main")


def _author(loop: Loop) -> None:
    """add-node and scaffold-planning, then the sheet written and landed on main."""
    loop.cli(
        "add-node",
        "add-node",
        "--id",
        LEAF,
        "--type",
        "task",
        "--title",
        "Write the hello module",
        "--parent-id",
        PARENT,
        "--touch-zone",
        "src",
        "--acceptance",
        "src/hello.py exists",
    )
    loop.cli("scaffold-planning", "scaffold-planning", LEAF)
    (loop.root / loop.leaf(None)["planning_dir"]).write_text(SHEET, encoding="utf-8")
    loop.commit(f"roadmap: add {LEAF}", "-A")
    _git(loop.root, "push", "-q", "origin", "main")


def _implement_and_review(loop: Loop, reviewers: tuple[str, ...]) -> None:
    """The work committed, ready filed, and one hand-filed approval per reviewer."""
    root = loop.root
    (root / "src").mkdir()
    (root / "src" / "hello.py").write_text('GREETING = "hello"\n', encoding="utf-8")
    (root / "work" / f"implementation-summary-{LEAF}.md").write_text(
        f"# {LEAF}\n\nAdded src/hello.py.\n\n## Added\n\n- src/hello.py: the module\n",
        encoding="utf-8",
    )
    loop.commit(
        "feat: hello module",
        "src/hello.py",
        f"work/brief-{LEAF}.md",
        f"work/implementation-summary-{LEAF}.md",
    )
    loop.cli("ready", "ready", LEAF, "--model", "exec-a", "--run", "test -f src/hello.py")
    head = _git(root, "rev-parse", "HEAD")
    for model in reviewers:
        notes = loop.tmp / f"notes-{model}.md"
        record = {
            "node_id": LEAF,
            "model": model,
            "date": "2026-11-07",
            "verdict": "approve",
            "commit": head,
            "acceptance": {"A1": "pass"},
            "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
            "commands_rerun": ["test -f src/hello.py"],
            "required_changes": [],
            "fresh_session": True,
            "authored_fix": False,
            "is_coordinator": False,
        }
        notes.write_text(
            "---\n" + yaml.safe_dump(record, sort_keys=False) + "---\nnotes\n", encoding="utf-8"
        )
        loop.cli(
            f"review record {model}",
            "review",
            "record",
            LEAF,
            "--model",
            model,
            "--verdict",
            "approve",
            "--file",
            str(notes),
            "--human-filed",
            "parity harness: a scripted reviewer",
        )


def _drive(tmp: Path, mode: str, reviewers: tuple[str, ...] = ("rev-b", "rev-c")) -> Loop:
    loop = Loop(tmp, mode)
    _set_up(loop)
    _author(loop)
    loop.cli("pickup", "do-next-available-task", "--under", LEAF)
    _implement_and_review(loop, reviewers)
    return loop


@pytest.mark.parametrize("mode", ["merge", "pr"])
def test_leaf_loop_matches_golden(tmp_path: Path, mode: str) -> None:
    loop = _drive(tmp_path, mode)
    loop.cli("gate check", "mark-implementation-reviewed", "--yes")
    loop.cli("finish", "finish-this-task")
    assert not (tmp_path / "hosting-calls.log").exists(), (
        tmp_path / "hosting-calls.log"
    ).read_text()
    if mode == "merge":
        end = loop.steps[-1]
        assert end["exit"] == 0
        assert end["status"] == {"checkout": "Complete", "main": "Complete"}
        assert end["registry"] == {"checkout": [], "main": []}
        assert end["git"]["merged_into_main"] is True
        assert end["git"]["merged_into_origin_main"] is True
    check_golden(GOLDEN / "leaf_loop" / f"{mode}.json", json.dumps(loop.steps, indent=1) + "\n")


def test_leaf_loop_gate_refuses_one_review_short(tmp_path: Path) -> None:
    """The loop exercises the gate: with one of the two reviews missing, the gate check fails."""
    loop = _drive(tmp_path, "merge", reviewers=("rev-b",))
    loop.cli("gate check", "mark-implementation-reviewed", "--yes", expect=1)
    assert loop.steps[-1]["registry"]["main"][0]["implementation_review"] == "pending"
