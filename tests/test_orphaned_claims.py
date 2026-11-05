"""A registry claim with no live worker, live session or READY at the tip is reported (M15.26)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import specy_road
import yaml

from specy_road.bundled_scripts import review_cli, worker_cli
from specy_road.bundled_scripts.grind_session_events import EventEmitter
from specy_road.orphaned_claims import orphaned_claims, report_lines, stays_claimed
from specy_road.review_files import reviews_dir
from specy_road.review_target import resolve_target
from specy_road.session_presence import start_session
from specy_road import worker_state as ws
from tests.review_repo_helpers import git, make_review_repo
from tests.worker_repo_helpers import make_worker_repo


def _claim(repo: Path, node_id: str, branch: str, *, started: str | None = None, make_branch: bool = True) -> None:
    path = repo / "roadmap" / "registry.yaml"
    reg = yaml.safe_load(path.read_text(encoding="utf-8"))
    row = {"codename": branch.removeprefix("feature/rm-"), "node_id": node_id, "branch": branch,
           "touch_zones": ["src"], "implementation_review": "pending"}
    if started:
        row["started"] = started
    reg["entries"].append(row)
    path.write_text(yaml.safe_dump(reg), encoding="utf-8")
    if make_branch:
        git(repo, "branch", branch)


def _ready(repo: Path, node_id: str, branch: str) -> None:
    t = resolve_target(repo, "M1.1")
    tip = git(repo, "rev-parse", branch)
    d = reviews_dir(repo, node_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-x.md").write_text(
        f"---\nnode_id: {node_id}\nagent: x\nbranch: {branch}\ncommit: '{tip}'\n"
        f"base: '{t.base}'\nchanged_paths: [src/a.py]\n---\n",
        encoding="utf-8",
    )


def _exit(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        worker_cli.main(list(argv))
    return e.value.code or 0


def test_a_failed_worker_is_listed_and_a_running_worker_session_or_ready_is_not(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    failed = ws.create_record(repo, "M1.1", "generic", "x", repo, branch="feature/rm-thing")
    ws.set_state(repo, failed, "failed", pid=None)
    _claim(repo, "M1.2", "feature/rm-running")
    live = ws.create_record(repo, "M1.2", "generic", "x", repo, branch="feature/rm-running")
    ws.set_state(repo, live, "running", pid=None)
    _claim(repo, "M1.3", "feature/rm-session")
    git(repo, "checkout", "-q", "feature/rm-session")
    start_session(repo, "pat", paths=["src"])
    git(repo, "checkout", "-q", "feature/rm-thing")
    _claim(repo, "M1.4", "feature/rm-ready")
    _ready(repo, "M1.4", "feature/rm-ready")
    _claim(repo, "M1.5", "feature/rm-gone", started="2020-01-01", make_branch=False)

    found = {c["node_id"]: c for c in orphaned_claims(repo)}
    assert set(found) == {"M1.1", "M1.5"}
    assert found["M1.1"]["age"] == "under 1m"
    assert found["M1.5"]["since"].startswith("2020-01-01T00:00:00") and found["M1.5"]["age"].endswith("d")
    line = f"M1.1 (feature/rm-thing, under 1m): `specy-road worker delegate M1.1` to resume work, " \
           "or `specy-road abort-task-pickup` to release it"
    assert line in report_lines(orphaned_claims(repo))

    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert line in out
    assert "`specy-road worker delegate M1.2`" not in out
    assert "`specy-road worker delegate M1.3`" not in out
    assert "`specy-road worker delegate M1.4`" not in out

    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "--json", "--repo-root", str(repo)])
    data = json.loads(capsys.readouterr().out)
    assert [c["node_id"] for c in data["orphaned_claims"]] == ["M1.1", "M1.5"]


def test_implement_hook_failed_says_the_leaf_stays_claimed(capsys) -> None:
    note = stays_claimed("M1.1")
    EventEmitter(as_json=False).emit("hook_failed", phase="implement", node_id="M1.1", rc=3)
    assert capsys.readouterr().out.strip() == f"[grind-session] hook_failed: phase=implement node=M1.1 rc=3; {note}"
    EventEmitter(as_json=False).emit("hook_failed", phase="finish", node_id="M1.1", rc=3)
    assert capsys.readouterr().out.strip() == "[grind-session] hook_failed: phase=finish node=M1.1 rc=3"
    EventEmitter(as_json=True).emit("hook_failed", phase="implement", node_id="M1.1", rc=3)
    assert "stays claimed" not in capsys.readouterr().out


def test_orchestrate_delegate_step_says_to_resolve_the_claim() -> None:
    text = (Path(specy_road.__file__).parent / "templates" / "specyrd" / "commands" / "specyrd-orchestrate.md").read_text()
    assert ("If delegate fails, the leaf stays claimed with no worker: resolve it with "
            "`specy-road worker delegate <ID>` or `specy-road abort-task-pickup` before the next pickup.") in text


def test_an_unclaimed_or_non_delegate_failure_has_no_claim_hint(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert _exit(["worker", "delegate", "M9.9", "--model", "opus", "--repo-root", str(repo)]) == 1
    err = capsys.readouterr().err
    assert "after pickup" in err and "stays claimed" not in err
    assert _exit(["worker", "resume", "w-0099", "--repo-root", str(repo)]) == 1
    assert "stays claimed" not in capsys.readouterr().err
