"""The process corpus: commands whose output must not change when they stop running in a child.

Each :class:`Case` builds its repos under a fresh directory and runs its steps in order, every
step from the directory it names. :func:`run_in_one_process` runs every case's steps through
``specy_road.cli.main`` in this one interpreter, with every launch of a Python interpreter
refused but the GUI's uvicorn; ``python -m tests.parity.process.corpus`` is that run as a
command, for :mod:`tests.parity.process.test_process_corpus`.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from tests.milestone_repo_helpers import make_milestone_repo
from tests.parity.support import cli_env, normalise
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

GOLDEN = Path(__file__).resolve().parent / "golden"

#: A commit id: seven or more hex digits holding at least one digit, so a hex-only word is left;
#: not a segment of a node key (a UUID), whose segments sit between hyphens.
_SHA = re.compile(r"(?<![\w-])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}(?![\w-])")
#: A commit's timestamp: each build of a case commits at a different time.
_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:[+-]\d\d:\d\d|Z)?")
#: A written file's size: the digest's length follows the dates in it.
_SIZE = re.compile(r"\(\d+ bytes\)")


@dataclass(frozen=True)
class Case:
    """``steps`` are ``(directory label, argv)``; ``build`` makes the labelled directories under a root."""

    name: str
    build: Callable[[Path], dict[str, Path]]
    steps: tuple[tuple[str, tuple[str, ...]], ...]


def _two_repos(tmp: Path) -> dict[str, Path]:
    """``a``: a claimed leaf on its feature branch; ``b``: milestone ``M2`` on ``dev``; ``out``: no project."""
    (tmp / "out").mkdir(parents=True)
    return {"a": make_review_repo(tmp / "a"), "b": make_milestone_repo(tmp / "b"), "out": tmp / "out"}


def _milestone_reviewed(tmp: Path) -> dict[str, Path]:
    """Milestone ``M2`` with both leaves landed and a human approval at the ``dev`` tip."""
    root = make_milestone_repo(tmp / "b")
    d = root / "work" / "reviews" / "M2"
    d.mkdir(parents=True)
    record = {"node_id": "M2", "model": "human", "date": "2026-11-02", "verdict": "approve",
              "commit": git(root, "rev-parse", "dev"), "acceptance": {},
              "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
              "commands_rerun": [], "required_changes": [], "fresh_session": True, "authored_fix": False,
              "is_coordinator": False}
    (d / "REVIEW-human.md").write_text("---\n" + yaml.safe_dump(record, sort_keys=False) + "---\nnotes\n")
    return {"b": root}


def _doctor_repo(tmp: Path, *, dirty: bool = False) -> dict[str, Path]:
    """``dev`` holds a registry row whose leaf ``M1.4`` is Complete; ``origin`` is bare; no open claim.

    With ``dirty`` a tracked file has an uncommitted change, so the nested registry-prune run
    refuses to sync the integration branch and doctor goes on.
    """
    repo = make_review_repo(tmp)
    git(repo, "checkout", "-q", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["status"] = "Complete"
    doc["nodes"].append({**NODE, "id": "M1.4", "codename": "settled", "status": "Complete",
                         "node_key": "44444444-4444-5444-8444-444444444444", "sibling_order": 4})
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "graph")
    reg = {"version": 1, "entries": [{"codename": "settled", "node_id": "M1.4",
                                      "branch": "feature/rm-settled", "touch_zones": ["settled"]}]}
    commit_file(repo, "roadmap/registry.yaml", yaml.safe_dump(reg), "claims")
    git(repo, "merge", "-q", "--no-ff", "--no-edit", "feature/rm-thing")
    bare = tmp / "origin.git"
    git(tmp, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "--all")
    if dirty:
        (repo / "src" / "a.py").write_text("print('edited')\n")
    return {"d": repo, "origin": bare}


def _prompt_repo(tmp: Path) -> dict[str, Path]:
    """The ``opus`` roster entry with the shipped Claude Opus profile, on the claimed leaf's branch."""
    from tests.test_models_and_prompt import make_profile_repo

    repo = make_profile_repo(tmp)
    (repo / "work" / "reviews" / "M1.1").mkdir(parents=True)
    (repo / "work" / "reviews" / "M1.1" / "PACKET.md").write_text("# Review packet: `M1.1`\n")
    return {"p": repo}


CASES: tuple[Case, ...] = (
    Case("two_roots", _two_repos, (
        ("a", ("list-nodes",)),
        ("b", ("list-nodes",)),
        ("a", ("validate",)),
        ("b", ("validate",)),
        ("a", ("mark-implementation-reviewed", "--yes")),
        ("b", ("mark-implementation-reviewed", "--yes")),
        ("a", ("mark-implementation-reviewed", "--yes", "--allow-missing-summary")),
    )),
    Case("repo_root_positions", _two_repos, (
        ("out", ("--repo-root", "{a}", "list-nodes")),
        ("out", ("list-nodes", "--repo-root", "{a}")),
        ("out", ("list-nodes", "--json", "--repo-root", "{b}", "--status", "Complete")),
        ("out", ("list-nodes", "--repo-root={a}")),
        ("out", ("show-node", "M1.1", "--repo-root", "{a}")),
        ("out", ("validate", "--repo-root={b}")),
        ("out", ("validate", "--repo-root", "{a}")),
    )),
    Case("shared_parser", _two_repos, (
        ("out", ("why-blocked", "M2.2", "--repo-root", "{b}")),
        ("out", ("list-gates", "--repo-root", "{b}")),
        ("a", ("list-gates",)),
    )),
    Case("forwarded", _two_repos, (
        ("out", ("digest", "--repo-root", "{b}", "--check")),
        ("out", ("digest", "--repo-root", "{b}", "-o", "{out}/context.md")),
        ("out", ("search", "Node", "--repo-root", "{b}")),
        ("out", ("brainstorm", "sessions", "--repo-root", "{b}")),
        ("out", ("history", "--repo-root", "{b}", "--json")),
        ("out", ("orchestration", "guard", "--format", "generic", "--role", "executor",
                 "--command", "git push --force origin dev")),
    )),
    Case("doctor_prune", _doctor_repo, (
        ("d", ("doctor", "--fix", "--yes")),
        ("d", ("doctor",)),
    )),
    Case("doctor_prune_fails", lambda tmp: _doctor_repo(tmp, dirty=True), (
        ("d", ("doctor", "--fix", "--yes")),
    )),
    Case("milestone_close", _milestone_reviewed, (
        ("b", ("mark-implementation-reviewed", "M2", "--yes")),
        ("b", ("mark-implementation-reviewed", "M2", "--yes")),
    )),
    Case("usage_errors", _two_repos, (
        ("a", ("validate", "--bogus")),
        ("a", ("frobnicate",)),
        ("a", ("grind",)),
        ("a", ("orchestration",)),
        ("a", ("orchestration", "--format", "generic")),
        ("a", ("list-nodes", "--status")),
        ("a", ("history", "--bogus")),
    )),
    Case("prompt_cli", _prompt_repo, (
        ("p", ("prompt", "M1.1", "--model", "opus", "--role", "executor", "--channel", "cli")),
        ("p", ("prompt", "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli")),
    )),
    Case("version", _two_repos, (
        ("a", ("--version",)),
        ("a", ("version",)),
    )),
)


def corpus_env() -> dict[str, str]:
    """:func:`cli_env` with git's directory alone on ``PATH``, and unbuffered output.

    ``PATH`` holds no ``specy-road``, so doctor's install report reads the same on every machine.
    Unbuffered, the order of lines is the order they were written, as a terminal shows them: with
    a pipe, a child's buffered lines used to land after the git output it started.
    """
    git_dir = str(Path(shutil.which("git") or "/usr/bin/git").parent)
    return cli_env(PATH=git_dir, PYTHONUNBUFFERED="1")


def build(case: Case, tmp: Path) -> tuple[dict[str, Path], list[tuple[Path, list[str]]]]:
    """Build ``case`` under ``tmp``; return its directories and its steps with paths filled in."""
    dirs = {label: path.resolve() for label, path in case.build(tmp).items()}
    fill = {label: str(path) for label, path in dirs.items()}
    return dirs, [(dirs[label], [arg.format(**fill) for arg in argv]) for label, argv in case.steps]


def step_transcript(argv: list[str], code: int, out: str, err: str, dirs: dict[str, Path]) -> str:
    """One step as the golden stores it: paths, commit ids and the version normalised."""
    text = normalise(
        f"$ specy-road {' '.join(argv)}\nexit: {code}\n--- stdout ---\n{out}--- stderr ---\n{err}",
        {path: f"<{label.upper()}>" for label, path in dirs.items()},
    )
    return _SIZE.sub("(<N> bytes)", _TIME.sub("<TIME>", _SHA.sub("<SHA>", text)))


def golden_path(case: Case) -> Path:
    """Where ``case``'s recorded steps live."""
    return GOLDEN / f"{case.name}.txt"
