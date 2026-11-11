"""The orchestration state table: one fixture repo per row, and what each reader said about it.

Every row starts from :func:`tests.worker_repo_helpers.make_worker_repo` (leaf ``M1.1`` claimed on
``feature/rm-thing``, the main checkout on that branch, a roster with ``max_workers: 2``) and adds
the workers, worktrees, review files and presence the row names, and pushes ``dev`` and the leaf's
branch to a bare ``origin``. ``golden/<row>.txt`` holds, for
each row, ``worker list --all`` (text and ``--json``), ``orchestrate plan --json`` and ``doctor``,
then the cleanup eligibility: :func:`specy_road.worker_orphans.orphans` (what
``worker terminate --orphaned`` ends), :func:`specy_road.worker_orphans.holding_slots` (what
``policy.max_workers`` counts) and :func:`specy_road.orphaned_claims.orphaned_claims` (the claims
doctor reports, M15.26). Those goldens were recorded before any reader switched to the snapshot;
``golden/<row>.snapshot.txt`` is what :func:`specy_road.orchestration.snapshot` returns for the row.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from specy_road import worker_state as ws
from specy_road.chore_records import chores_dir
from specy_road.orchestration import snapshot
from specy_road.orphaned_claims import orphaned_claims
from specy_road.review_files import reviews_dir
from specy_road.review_target import resolve_target
from specy_road.session_presence import start_session
from specy_road.worker_orphans import holding_slots, orphans
from tests.parity.process.corpus import corpus_env, step_transcript
from tests.parity.support import run_cli
from tests.review_repo_helpers import commit_file, git, review_text
from tests.worker_repo_helpers import make_worker_repo

GOLDEN = Path(__file__).resolve().parent / "golden"
NODE, BRANCH = "M1.1", "feature/rm-thing"
#: The commands each row records, from the main checkout.
COMMANDS = (
    ("worker", "list", "--all"),
    ("worker", "list", "--all", "--json"),
    ("orchestrate", "plan", "--json"),
    ("doctor",),
)
#: ``(feature/rm-thing, 3d)``: a claim's age follows the clock; the row does not.
_AGE = re.compile(r"(, )(under 1m|\d+[dhm])\)")


@dataclass(frozen=True)
class Row:
    """``build(repo, tmp)`` adds the row's state to a fresh repo and returns its labelled paths."""

    name: str
    build: Callable[[Path, Path], dict[str, Path]]


def _worker(
    repo: Path,
    state: str,
    *,
    node: str = NODE,
    worktree: Path | None = None,
    branch: str | None = BRANCH,
) -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, "generic", "x", worktree or repo, branch=branch)
    return ws.set_state(repo, rec, state, pid=None)


def _ready_at_tip(repo: Path) -> None:
    target, tip = resolve_target(repo, NODE), git(repo, "rev-parse", BRANCH)
    d = reviews_dir(repo, NODE)
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-x.md").write_text(
        f"---\nnode_id: {NODE}\nagent: x\nbranch: {BRANCH}\ncommit: '{tip}'\n"
        f"base: '{target.base}'\nchanged_paths: [src/a.py]\n---\n",
        encoding="utf-8",
    )


def _fresh_claim(repo: Path, tmp: Path) -> dict[str, Path]:
    return {}


def _live_worker(repo: Path, tmp: Path) -> dict[str, Path]:
    _worker(repo, "running")
    return {}


def _exited_clean(repo: Path, tmp: Path) -> dict[str, Path]:
    _worker(repo, "completed")
    _ready_at_tip(repo)
    return {}


def _exited_failed(repo: Path, tmp: Path) -> dict[str, Path]:
    _worker(repo, "failed")
    return {}


def _abandoned(repo: Path, tmp: Path) -> dict[str, Path]:
    """A claim whose worker was terminated, with no presence and no READY: M15.26 reports it."""
    _worker(repo, "terminated")
    return {}


def _review_no_worker(repo: Path, tmp: Path) -> dict[str, Path]:
    d = reviews_dir(repo, NODE)
    d.mkdir(parents=True, exist_ok=True)
    (d / "REVIEW-human.md").write_text(
        review_text(git(repo, "rev-parse", BRANCH)), encoding="utf-8"
    )
    return {}


def _chore_worker(repo: Path, tmp: Path) -> dict[str, Path]:
    """An idle worker on chore ``tidy-docs``: it has no leaf, claim or graph node."""
    chores_dir(repo).mkdir(parents=True, exist_ok=True)
    (chores_dir(repo) / "tidy-docs.json").write_text(
        json.dumps(
            {
                "slug": "tidy-docs",
                "branch": "chore/tidy-docs",
                "worktree": str(repo),
                "touch_zones": ["docs"],
            }
        ),
        encoding="utf-8",
    )
    _worker(repo, "idle", node="tidy-docs", branch=None)
    return {}


def _two_worktrees(repo: Path, tmp: Path) -> dict[str, Path]:
    """The leaf's branch in linked worktree ``leaf``, a running worker there; a terminated worker's
    detached worktree ``scratch`` with an uncommitted change."""
    git(repo, "checkout", "-q", "dev")
    leaf, scratch = tmp / "leaf", tmp / "scratch"
    git(repo, "worktree", "add", "-q", str(leaf), BRANCH)
    git(repo, "worktree", "add", "-q", "--detach", str(scratch), BRANCH)
    (scratch / "src" / "a.py").write_text("print('scratch')\n", encoding="utf-8")
    _worker(repo, "terminated", worktree=scratch)
    _worker(repo, "running", worktree=leaf)
    return {"leaf": leaf, "scratch": scratch}


def _unreadable_worker(repo: Path, tmp: Path) -> dict[str, Path]:
    """The leaf's only worker record is not YAML."""
    ws.workers_dir(repo).mkdir(parents=True, exist_ok=True)
    (ws.workers_dir(repo) / "w-0001.yaml").write_text("state: [running\n", encoding="utf-8")
    return {}


def _manual_presence(repo: Path, tmp: Path) -> dict[str, Path]:
    """A person's live session on the claimed branch, no worker."""
    start_session(repo, "pat", paths=["src"])
    return {}


ROWS: tuple[Row, ...] = (
    Row("fresh_manual_claim", _fresh_claim),
    Row("live_worker", _live_worker),
    Row("exited_clean", _exited_clean),
    Row("exited_failed", _exited_failed),
    Row("abandoned", _abandoned),
    Row("review_no_worker", _review_no_worker),
    Row("chore_worker", _chore_worker),
    Row("two_worktrees", _two_worktrees),
    Row("unreadable_worker_state", _unreadable_worker),
    Row("manual_presence", _manual_presence),
)


def build(row: Row, tmp: Path) -> tuple[Path, dict[str, Path]]:
    """The row's repo, and every path its output may print, labelled for normalisation."""
    repo, script = make_worker_repo(tmp)
    commit_file(
        repo, "src/b.py", "print('b')\n", "more"
    )  # the tip moves past the first impl commit
    extra = row.build(repo, tmp)
    bare = (
        tmp / "origin.git"
    )  # doctor compares against origin/dev: with no remote it skips its cleanup checks
    git(tmp, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "dev", BRANCH)
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")   # as clone does: plan reads the branch there
    dirs = {
        "repo": repo.resolve(),
        "tmp": tmp.resolve(),
        "fake": script.resolve(),
        "origin": bare.resolve(),
        **{k: v.resolve() for k, v in extra.items()},
    }
    return repo, dirs


def eligibility(repo: Path) -> dict[str, object]:
    """Cleanup eligibility: orphaned workers, workers holding a slot, the claims M15.26 reports."""
    records = ws.list_records(repo)
    return {
        "orphaned_workers": orphans(repo),
        "holding_slots": [r.worker_id for r in holding_slots(repo, records)],
        "orphaned_claims": [
            {"node_id": c["node_id"], "branch": c["branch"]} for c in orphaned_claims(repo)
        ],
    }


def normalise(text: str) -> str:
    """:func:`step_transcript`'s normalisation, plus claim ages."""
    return _AGE.sub(r"\1<AGE>)", text)


def record(row: Row, tmp: Path) -> str:
    """The golden text for ``row``: each command's transcript, then the eligibility."""
    repo, dirs = build(row, tmp)
    env = corpus_env()
    parts = []
    for argv in COMMANDS:
        result = run_cli("specy_road.cli", list(argv), cwd=repo, env=env)
        parts.append(
            step_transcript(list(argv), result.returncode, result.stdout, result.stderr, dirs)
        )
    parts.append(
        step_transcript(
            ["(eligibility)"], 0, json.dumps(eligibility(repo), indent=2) + "\n", "", dirs
        )
    )
    return normalise("\n".join(parts))


def golden_path(row: Row) -> Path:
    """Where ``row``'s recorded output lives."""
    return GOLDEN / f"{row.name}.txt"


def snapshot_text(repo: Path, dirs: dict[str, Path]) -> str:
    """``snapshot(repo)`` as JSON, normalised as the command transcripts are."""
    return step_transcript(["(snapshot)"], 0, json.dumps(snapshot(repo), indent=2) + "\n", "", dirs)


def snapshot_golden(row: Row) -> Path:
    """Where ``row``'s snapshot lives, apart from the pickup goldens (it was recorded later)."""
    return GOLDEN / f"{row.name}.snapshot.txt"
