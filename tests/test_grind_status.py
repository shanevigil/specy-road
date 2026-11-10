"""``grind-session --status`` (M22.68): scope, buckets, estimate, decisions, sessions, watch, read-only.

Temporary repos with real commits; history is dated through ``GIT_AUTHOR_DATE`` and ``now`` is pinned through
:func:`grind_status.run_status`'s ``clock``, so nothing waits and nothing reads the wall clock.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from specy_road import grind_status as gst
from specy_road.brainstorm_session import BrainstormSession, write_session
from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.history_index import clear_memo
from specy_road.planning_sheet_bootstrap import promote_placeholder
from specy_road.registration_pickup_commit import registration_commit_message
from specy_road.review_files import render_front_matter, reviews_dir
from specy_road.review_policy_pin import pinned_message
from specy_road.session_presence import start_session
from specy_road.worker_state import FLAG_NEEDS_PERSON, add_flag, create_record, set_lease, set_state
from tests.review_repo_helpers import commit_file, diverge, make_review_repo, review_text
from tests.test_review_rca import ROSTER

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
NS = uuid.UUID("05b23f6c-3e4d-4ac9-b0a0-022b4fe7f7f1")


@pytest.fixture(autouse=True)
def no_history_memo() -> None:
    clear_memo()


def key(nid: str) -> str:
    return str(uuid.uuid5(NS, nid))


def node(nid: str, *, parent: str | None = None, typ: str = "task", status: str = "Not Started",
         deps: tuple[str, ...] = (), codename: str | None = "", title: str | None = None) -> dict:
    n = {"id": nid, "node_key": key(nid), "title": title or f"Leaf {nid}", "type": typ, "parent_id": parent,
         "sibling_order": int(nid.rsplit(".", 1)[-1].lstrip("M")), "status": status,
         "dependencies": [key(d) for d in deps], "touch_zones": [f"src/{nid}.py"], "acceptance": ["it works"],
         "planning_dir": f"planning/{nid}.md"}
    if codename is not None:
        n["codename"] = codename or nid.lower().replace(".", "-")
    return n


def git(repo: Path, *args: str, when: datetime | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "pat", "GIT_AUTHOR_EMAIL": "pat@example.com",
           "GIT_COMMITTER_NAME": "pat", "GIT_COMMITTER_EMAIL": "pat@example.com"}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


def write_graph(repo: Path, nodes: list[dict], unauthored: tuple[str, ...] = ()) -> None:
    (repo / "roadmap" / "phases").mkdir(parents=True, exist_ok=True)
    (repo / "roadmap" / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M.json"]}))
    (repo / "roadmap" / "phases" / "M.json").write_text(json.dumps({"nodes": nodes}, indent=1))
    for n in nodes:
        sheet = repo / n["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        approach = promote_placeholder(n["id"]) if n["id"] in unauthored else "Write it."
        sheet.write_text(f"# {n['title']}\n\n## Intent\n\nDo it.\n\n## Approach\n\n{approach}\n")


def commit(repo: Path, msg: str, when: datetime | None = None) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg, when=when)


def make_repo(tmp_path: Path, nodes: list[dict], *, entries: tuple[dict, ...] = (),
              unauthored: tuple[str, ...] = (), when: datetime | None = None) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "dev")
    write_graph(repo, nodes, unauthored)
    (repo / "roadmap" / "registry.yaml").write_text(yaml.safe_dump({"version": 1, "entries": list(entries)}))
    (repo / "roadmap" / "git-workflow.yaml").write_text("version: 1\nintegration_branch: dev\nremote: origin\n")
    (repo / ".gitignore").write_text("work/\n.specyrd/cache/\n")
    commit(repo, "graph", when)
    return repo


def set_status(repo: Path, nid: str, status: str) -> None:
    path = repo / "roadmap" / "phases" / "M.json"
    doc = json.loads(path.read_text())
    next(n for n in doc["nodes"] if n["id"] == nid)["status"] = status
    path.write_text(json.dumps(doc, indent=1))


def run(repo: Path, *argv: str, now: datetime = NOW, sleep=None) -> int:
    args = parse_grind_session_args(["--status", *argv, "--repo-root", str(repo)])
    extra = {"sleep": sleep} if sleep else {}
    return gst.run_status(repo, args, clock=lambda: now, **extra)


def status(repo: Path, capsys, *argv: str, now: datetime = NOW) -> dict:
    capsys.readouterr()
    assert run(repo, *argv, "--json", now=now) == 0
    return json.loads(capsys.readouterr().out)


def ids(items: list[dict]) -> list[str]:
    return [i["id"] for i in items]


# --- scope -------------------------------------------------------------------

SCOPE_GRAPH = [
    node("M1", typ="phase"), node("M1.1", parent="M1", deps=("M2", "M3.1")),
    node("M2", typ="phase"), node("M2.1", parent="M2", status="Complete"), node("M2.2", parent="M2"),
    node("M3", typ="phase"), node("M3.1", parent="M3", status="Complete", deps=("M3.2",)),
    node("M3.2", parent="M3"), node("M3.3", parent="M3"),
    node("M4", typ="phase", deps=("M6.2",)), node("M4.1", parent="M4", typ="milestone"),
    node("M4.1.1", parent="M4.1", deps=("M6.1",)),
    node("M6", typ="phase"), node("M6.1", parent="M6"), node("M6.2", parent="M6"),
]


@pytest.mark.parametrize("argv, leaves, done", [
    (("--until", "M1.1"), ["M1.1", "M2.1", "M2.2", "M3.1"], 2),   # D (M3.2) stays out: C is Complete
    (("--until", "M4.1"), ["M4.1.1", "M6.1", "M6.2"], 0),          # X from the leaf, Y inherited from M4
    (("--under", "M3"), ["M3.1", "M3.2", "M3.3"], 1),
    (("--until", "M1.1", "--under", "M3"), ["M3.1"], 1),           # not the ready M3.3 nor D
])
def test_scope_rules(tmp_path: Path, capsys, argv: tuple[str, ...], leaves: list[str], done: int) -> None:
    r = status(make_repo(tmp_path, SCOPE_GRAPH), capsys, *argv)
    assert r["scope"]["leaves"] == leaves
    assert (r["totals"]["total"], r["totals"]["done"]) == (len(leaves), done)


def test_the_milestone_session_parent_is_the_default_scope(tmp_path: Path, capsys) -> None:
    from specy_road.milestone_session import milestone_session_path, write_milestone_session

    repo = make_repo(tmp_path, SCOPE_GRAPH)
    write_milestone_session(milestone_session_path(repo / "work"), parent_node_id="M3", parent_codename="m3",
                            integration_branch="dev", remote="origin")
    r = status(repo, capsys)
    assert r["scope"]["leaves"] == status(repo, capsys, "--under", "M3")["scope"]["leaves"]
    assert r["goal"] == "M3" and ".milestone-session.yaml" in r["scope"]["rule"]


@pytest.mark.parametrize("argv, words", [
    ((), ("--until", "--under", "start-milestone-session")),
    (("--until", "M99"), ("no node M99",)),
])
def test_no_scope_or_an_unknown_node_exits_2(tmp_path: Path, capsys, argv, words) -> None:
    repo = make_repo(tmp_path, SCOPE_GRAPH)
    capsys.readouterr()
    assert gs.run_session(parse_grind_session_args(["--status", *argv, "--repo-root", str(repo)])) == 2
    err = capsys.readouterr().err
    assert all(w in err for w in words), err


# --- buckets -----------------------------------------------------------------


def branch_with(repo: Path, codename: str, *, complete: str | None = None, path: str | None = None) -> str:
    git(repo, "checkout", "-q", "-b", f"feature/rm-{codename}", "dev")
    if complete:
        set_status(repo, complete, "Complete")
    if path:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n")
    commit(repo, f"work on {codename}")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "dev")
    return sha


def claim(nid: str) -> dict:
    c = nid.lower().replace(".", "-")
    return {"codename": c, "node_id": nid, "branch": f"feature/rm-{c}", "touch_zones": [f"src/{nid}.py"]}


def buckets_repo(tmp_path: Path) -> Path:
    nodes = [
        node("M1", typ="phase"), node("M1.1", parent="M1", status="Complete"),
        node("M1.2", parent="M1", status="Cancelled"), node("M1.3", parent="M1", deps=("M1.20",)),
        node("M1.4", parent="M1"), node("M1.5", parent="M1"), node("M1.6", parent="M1", deps=("M1.5",)),
        node("M1.7", parent="M1"), node("M1.8", parent="M1", deps=("M1.20",)), node("M1.9", parent="M1"),
        node("M1.10", parent="M1"), node("M1.11", parent="M1", deps=("M1.21",)), node("M1.12", parent="M1"),
        node("M1.20", parent="M1", typ="gate"), node("M1.21", parent="M1", typ="gate", status="Complete"),
        node("M9", typ="phase"), node("M9.1", parent="M9"),
    ]
    repo = make_repo(tmp_path, nodes, entries=tuple(claim(i) for i in ("M1.4", "M1.8", "M1.10", "M1.12")),
                     unauthored=("M1.7",))
    sha = branch_with(repo, "m1-4", path="src/M1.4.py")
    branch_with(repo, "m1-8")
    branch_with(repo, "m1-9", complete="M1.9")
    branch_with(repo, "m1-10", complete="M1.10")
    ready = reviews_dir(repo, "M1.4") / "READY-composer.md"
    ready.parent.mkdir(parents=True)
    ready.write_text(render_front_matter({"node_id": "M1.4", "agent": "composer", "branch": "feature/rm-m1-4",
                                          "commit": sha, "base": git(repo, "rev-parse", "dev"),
                                          "changed_paths": ["src/M1.4.py"]}))
    outside = reviews_dir(repo, "M9.1")
    outside.mkdir(parents=True)
    (outside / "READY-x.md").write_text("not front matter\n")
    outside.chmod(0)   # a status that read it would fail here
    return repo


def test_each_leaf_is_in_exactly_one_bucket(tmp_path: Path, capsys) -> None:
    repo = buckets_repo(tmp_path)
    try:
        r = status(repo, capsys, "--under", "M1")
        capsys.readouterr()
        assert run(repo, "--under", "M1") == 0
        text = capsys.readouterr().out
    finally:
        reviews_dir(repo, "M9.1").chmod(0o755)
    got = {k: ids(r[k]) for k in ("held", "active", "ready", "waiting", "awaiting_merge", "not_pickable")}
    assert got == {"held": ["M1.3", "M1.8"], "active": ["M1.4", "M1.10", "M1.12"], "ready": ["M1.5", "M1.11"],
                   "waiting": ["M1.6"], "awaiting_merge": ["M1.9"], "not_pickable": ["M1.7"]}
    t = r["totals"]
    assert (t["total"], t["done"], t["cancelled"], t["remaining"]) == (12, 1, 1, 10)
    assert "M1.20" not in r["scope"]["leaves"] and "M1.21" not in r["scope"]["leaves"]
    held = {h["id"]: h for h in r["held"]}
    assert held["M1.8"]["claimed"] and held["M1.8"]["reasons"][0]["next"] == [
        "specy-road set-gate-status M1.20 --status Complete"]
    active = {a["id"]: a for a in r["active"]}
    assert active["M1.4"]["review"] == "in-review"
    assert gst.UNMERGED in active["M1.10"]["note"]
    assert active["M1.12"]["review"] is None and "not evaluated" in active["M1.12"]["review_error"]
    assert r["awaiting_merge"][0]["reason"] == gst.UNMERGED
    assert r["waiting"][0]["waiting_on"] == ["M1.5"]
    assert {h["node"] for h in r["decisions"]["held"]} == {"M1.3", "M1.8"}
    assert all(h["options"] == gst.NO_OPTIONS for h in r["decisions"]["held"])
    assert "M9.1" not in text and gst.NO_OPTIONS in text and "`specy-road set-gate-status M1.20" in text


# --- held: review and workers ------------------------------------------------


def block_round(repo: Path, n: int) -> None:
    commit_file(repo, f"src/r{n}.py", f"r = {n}\n", f"fix {n}")
    notes = repo.parent / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1="fail"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "block", "--file", str(notes),
                         "--repo-root", str(repo)])
    assert e.value.code == 0


def escalated(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    for n in (1, 2, 3):
        block_round(repo, n)
    return repo


def budget_spent(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + "policy: {max_fix_rounds: 1}\n")
    block_round(repo, 1)
    return repo


def executor_blocked(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path)
    sha = git(repo, "rev-parse", "HEAD")
    path = reviews_dir(repo, "M1.1") / "READY-opus.md"
    path.parent.mkdir(parents=True)
    path.write_text(render_front_matter({
        "node_id": "M1.1", "agent": "opus", "branch": "feature/rm-thing", "commit": sha,
        "base": git(repo, "rev-parse", "dev"), "changed_paths": ["src/a.py"], "verify": [{"cmd": "true", "exit": 0}],
        "blocked_on": [{"acceptance": "A1", "reason": "cannot without weakening a test"}]}))
    return repo


def policy_changed(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    git(repo, "checkout", "-q", "dev")
    git(repo, "commit", "-q", "--allow-empty", "-m",
        pinned_message(repo, registration_commit_message("thing", include_ci_skip=True)))
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "rebase", "-q", "dev")
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/orchestration.yaml", ROSTER + "  - {id: sonnet, family: anthropic, roles: [reviewer]}\n",
                "roster gains a reviewer")
    git(repo, "checkout", "-q", "feature/rm-thing")
    return repo


@pytest.mark.parametrize("build, kind, next_has", [
    (escalated, "escalated", "specy-road prompt M1.1 --role rca"),
    (budget_spent, "fix_round_budget_spent", None),   # the budget's own `next`
    (executor_blocked, "executor_blocked", "A1: cannot without weakening a test"),
    (policy_changed, "policy_pin", "specy-road review accept-policy M1.1"),
])
def test_a_claimed_leaf_held_by_its_review_names_the_records_next_step(
        tmp_path: Path, capsys, build, kind: str, next_has: str | None) -> None:
    repo = build(tmp_path)
    capsys.readouterr()
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "M1.1", "--json", "--repo-root", str(repo)])
    handoff = json.loads(capsys.readouterr().out)["nodes"][0]
    r = status(repo, capsys, "--until", "M1.1")
    assert ids(r["held"]) == ["M1.1"]
    reason = next(x for x in r["held"][0]["reasons"] if x["kind"] == kind)
    expected = next_has or handoff["fix_round_budget"]["next"]
    assert any(expected in n for n in reason["next"]), reason
    assert {"node": "M1.1", **reason, "options": gst.NO_OPTIONS} in r["decisions"]["held"]


def test_status_runs_no_trial_merge_and_handoff_still_reports_the_conflict(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    diverge(repo, "code")
    capsys.readouterr()
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "M1.1", "--repo-root", str(repo)])
    assert "trial merge with refs/heads/dev: conflicts on src/a.py" in capsys.readouterr().out
    assert run(repo, "--until", "M1.1") == 0
    assert "trial merge" not in capsys.readouterr().out
    assert "trial" not in json.dumps(status(repo, capsys, "--until", "M1.1"))


def test_live_workers_leased_to_a_person_or_needing_one_hold_their_leaf(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, [node("M1", typ="phase")] + [node(f"M1.{i}", parent="M1") for i in (1, 2, 3, 4)])
    w1, w2, w3, w4 = (create_record(repo, f"M1.{i}", "claude-code", "opus", repo) for i in (1, 2, 3, 4))
    set_lease(repo, w1, "human")
    add_flag(repo, w2, FLAG_NEEDS_PERSON)
    set_lease(repo, w3, "human")
    set_state(repo, w3, "completed")
    set_lease(repo, w4, "human")
    set_state(repo, w4, "failed")
    r = status(repo, capsys, "--under", "M1")
    assert ids(r["held"]) == ["M1.1", "M1.2", "M1.3"] and ids(r["ready"]) == ["M1.4"]
    for h, w, step in ((r["held"][0], w1, "reclaim"), (r["held"][1], w2, "status"), (r["held"][2], w3, "reclaim")):
        assert w.worker_id in h["reasons"][0]["reason"]
        assert h["reasons"][0]["next"] == [f"specy-road worker {step} {w.worker_id}"]


# --- decisions ---------------------------------------------------------------

D1 = {"id": "D1", "kind": "decision", "node": "M1.1", "summary": "Pick the parser", "asked": "2026-11-01",
      "status": "open", "why_now": "M1.1 cannot start without it",
      "options": [{"label": "yaml", "effect": "one more dependency"}, {"label": "json", "effect": "no comments"}],
      "recommendation": "yaml", "recommendation_reason": "people edit these files by hand",
      "default_if_unanswered": "json after the deadline"}
D2 = {**D1, "id": "D2", "node": "M2.1", "summary": "Somewhere else", "needed_by": "2026-12-01"}


def test_ledger_entries_print_as_recorded_in_scope_and_one_line_outside(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, [node("M1", typ="phase"), node("M1.1", parent="M1"),
                                node("M2", typ="phase"), node("M2.1", parent="M2")])
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump({"version": 1, "entries": [D1, D2]}))
    r = status(repo, capsys, "--under", "M1")
    entry = r["decisions"]["ledger"][0]
    assert {k: entry[k] for k in D1 if k not in ("asked", "status")} == {
        k: v for k, v in D1.items() if k not in ("asked", "status")}
    assert entry["ledger"] == "shared" and entry["pros_cons"] == gst.PROS_CONS
    assert [e["id"] for e in r["decisions"]["ledger_outside_scope"]] == ["D2"]
    assert {"record": "D1", "field": "needed_by"} in r["missing"]
    assert run(repo, "--under", "M1") == 0
    text = capsys.readouterr().out
    for value in ("Pick the parser", "M1.1 cannot start without it", "yaml (one more dependency)",
                  "json (no comments)", "yaml — people edit these files by hand", "json after the deadline",
                  f"pros/cons: {gst.PROS_CONS}", "outside scope: D2 node M2.1: Somewhere else"):
        assert value in text, value


# --- estimate ----------------------------------------------------------------


def estimate_repo(tmp_path: Path, dates: list[datetime], open_count: int) -> Path:
    n = len(dates)
    leaves = [node(f"M1.{i}", parent="M1") for i in range(1, n + open_count + 1)]
    repo = make_repo(tmp_path, [node("M1", typ="phase"), *leaves], when=datetime(2026, 9, 1, tzinfo=timezone.utc))
    for i, when in enumerate(dates, start=1):
        set_status(repo, f"M1.{i}", "Complete")
        commit(repo, f"finish M1.{i}", when)
    return repo


def at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def test_the_range_comes_from_the_overall_and_recent_rates(tmp_path: Path, capsys) -> None:
    dates = [at(1), at(1, 12), at(2), at(3), at(3, 18), at(4)]   # 3 days; the last 2 within 7 days of NOW
    e = status(estimate_repo(tmp_path, dates, 4), capsys, "--under", "M1")["estimate"]
    i = e["inputs"]
    assert (i["n"], i["first"], i["last"], i["recent"], i["window_days"]) == (
        6, at(1).isoformat(), at(4).isoformat(), 2, 7)
    overall, recent = 5 / timedelta(days=3).total_seconds(), 2 / timedelta(days=7).total_seconds()
    assert e["earliest"] == (NOW + timedelta(seconds=round(4 / overall))).isoformat()
    assert e["latest"] == (NOW + timedelta(seconds=round(4 / recent))).isoformat()
    assert e["reason"] is None and gst.ASSUMPTION in e["method"]


@pytest.mark.parametrize("dates, words", [
    ([at(1), at(2), at(3), at(4)], ("4 completion(s)", "minimum 5")),
    ([at(4, h) for h in (0, 0, 1, 1, 2)], ("span 2.0 hours", "minimum 24 hours")),
])
def test_too_few_completions_give_no_dates(tmp_path: Path, capsys, dates, words) -> None:
    e = status(estimate_repo(tmp_path, dates, 3), capsys, "--under", "M1")["estimate"]
    assert e["reason"].startswith("not enough data") and all(w in e["reason"] for w in words)
    assert (e["earliest"], e["latest"]) == (None, None)


def test_no_recent_completions_leave_latest_open(tmp_path: Path, capsys) -> None:
    dates = [datetime(2026, 10, d, tzinfo=timezone.utc) for d in (1, 2, 3, 4, 5)]
    e = status(estimate_repo(tmp_path, dates, 2), capsys, "--under", "M1")["estimate"]
    overall = 4 / timedelta(days=4).total_seconds()
    assert e["latest"] == gst.NO_RECENT
    assert e["earliest"] == (NOW + timedelta(seconds=round(2 / overall))).isoformat()


def test_a_completion_follows_its_node_key_across_a_renumber(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, [node("M1", typ="phase"), node("M1.1", parent="M1")])
    set_status(repo, "M1.1", "Complete")
    commit(repo, "finish M1.1", at(2))
    path = repo / "roadmap" / "phases" / "M.json"
    doc = json.loads(path.read_text())
    doc["nodes"][1].update(id="M1.2", sibling_order=2)   # same node_key, new id
    doc["nodes"].append({**node("M1.1", parent="M1"), "node_key": str(uuid.uuid5(NS, "new"))})
    path.write_text(json.dumps(doc, indent=1))
    commit(repo, "renumber", at(3))
    r = status(repo, capsys, "--under", "M1")
    assert [c["id"] for c in r["estimate"]["inputs"]["completions"]] == ["M1.2"]
    assert ids(r["ready"]) == ["M1.1"] and r["totals"]["done"] == 1


# --- read-only, JSON, sessions -----------------------------------------------


def files(repo: Path) -> set[str]:
    return {p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}


def test_status_fetches_nothing_and_writes_only_the_history_cache(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, SCOPE_GRAPH)
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump({"version": 1, "entries": [D1]}))
    commit(repo, "ledger")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    sentinel, script = tmp_path / "fetched", tmp_path / "upload-pack.sh"
    script.write_text(f"#!/bin/sh\ntouch {sentinel}\nexec git-upload-pack \"$@\"\n")
    script.chmod(0o755)
    git(repo, "config", "remote.origin.uploadpack", str(script))
    before = (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD"), files(repo),
              (repo / "roadmap" / "registry.yaml").read_bytes(), (repo / "roadmap" / "decisions.yaml").read_bytes())
    assert run(repo, "--until", "M1.1") == 0
    assert not sentinel.exists()
    after = files(repo)
    assert (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD")) == before[:2]
    assert ((repo / "roadmap" / "registry.yaml").read_bytes(), (repo / "roadmap" / "decisions.yaml").read_bytes()) \
        == before[3:]
    assert before[2] <= after and all(p.startswith(".specyrd/cache/") for p in after - before[2])


def test_json_is_one_object_naming_its_checkout(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, SCOPE_GRAPH)
    r = status(repo, capsys, "--until", "M1.1")
    assert set(r) == {"generated_at", "source", "goal", "scope", "totals", "held", "active", "ready", "waiting",
                      "awaiting_merge", "not_pickable", "estimate", "decisions", "sessions", "missing"}
    assert set(r["estimate"]) == {"method", "inputs", "earliest", "latest", "reason"}
    assert set(r["decisions"]) == {"ledger", "ledger_outside_scope", "held"}
    assert set(r["sessions"]) == {"brainstorm", "presence"}
    head = git(repo, "rev-parse", "HEAD")
    assert r["generated_at"] == NOW.isoformat() and r["goal"] == "M1.1"
    assert r["source"] == {"branch": "dev", "head": head, "fetched": False}
    assert run(repo, "--until", "M1.1") == 0
    assert f"as of dev @ {head[:12]}, this checkout, not fetched" in capsys.readouterr().out
    git(repo, "checkout", "-q", "--detach")
    assert status(repo, capsys, "--until", "M1.1")["source"]["branch"] is None


def test_sessions_list_open_brainstorms_and_live_presence_word_for_word(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, SCOPE_GRAPH)
    now = datetime.now(timezone.utc)
    without = status(repo, capsys, "--until", "M1.1", now=now)["scope"]
    write_session(repo, BrainstormSession(slug="open-one", mode="roadmap"))
    unreadable = {"brainstorm-broken.yaml": b"version: [\n",                  # YAML that does not parse
                  "brainstorm-Open-two.yaml": b"version: 2\nslug: Open-two\n",  # a name validate_slug rejects
                  "brainstorm-utf16.yaml": "version: 2\n".encode("utf-16")}     # not UTF-8
    for name, data in unreadable.items():
        (repo / "work" / name).write_bytes(data)
    closed = repo / "work" / "brainstorm-closed" / "brainstorm-old.yaml"
    closed.parent.mkdir()
    closed.write_text("version: 2\nslug: old\n")
    start_session(repo, "planner-a", paths=[], note="planner: status")
    start_session(repo, "gone", paths=[], ttl_hours=-1)
    r = status(repo, capsys, "--until", "M1.1", now=now)
    assert r["sessions"]["brainstorm"] == [{"slug": "open-one", "mode": "roadmap", "ideas": 0}]
    assert {m["record"] for m in r["missing"] if "unreadable" in m["field"]} == {f"work/{n}" for n in unreadable}
    [live] = r["sessions"]["presence"]
    assert (live["agent"], live["branch"], live["note"]) == ("planner-a", "dev", "planner: status")
    assert r["scope"] == without


# --- watch and arguments -----------------------------------------------------


class FakeSleep:
    def __init__(self) -> None:
        self.asked: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)
        if len(self.asked) == 2:
            raise KeyboardInterrupt


@pytest.mark.parametrize("watch, yaml_line, seconds", [
    (["--watch", "15"], "", 900), (["--watch"], f"{gst.INTERVAL_KEY}: 5\n", 300), (["--watch"], "", 1800),
])
@pytest.mark.parametrize("as_json", [False, True])
def test_watch_repeats_the_report_on_the_interval_until_ctrl_c(
        tmp_path: Path, capsys, watch, yaml_line: str, seconds: int, as_json: bool) -> None:
    repo = make_repo(tmp_path, SCOPE_GRAPH)
    wf = repo / "roadmap" / "git-workflow.yaml"
    wf.write_text(wf.read_text() + yaml_line)
    sleep = FakeSleep()
    capsys.readouterr()
    assert run(repo, "--until", "M1.1", *watch, *(["--json"] if as_json else []), sleep=sleep) == 0
    out = capsys.readouterr().out
    assert sleep.asked == [seconds, seconds]
    if as_json:
        assert [json.loads(line)["goal"] for line in out.splitlines()] == ["M1.1", "M1.1"]
    else:
        assert out.count("last updated ") == 2 and out.count(gst.SEPARATOR) == 2


def test_a_bad_interval_exits_2_naming_the_flag_or_key(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as e:
        parse_grind_session_args(["--status", "--watch", "0"])
    assert e.value.code == 2 and "--watch" in capsys.readouterr().err
    repo = make_repo(tmp_path, SCOPE_GRAPH)
    wf = repo / "roadmap" / "git-workflow.yaml"
    wf.write_text(wf.read_text() + f"{gst.INTERVAL_KEY}: soon\n")
    assert run(repo, "--until", "M1.1", "--watch", sleep=FakeSleep()) == 2
    assert gst.INTERVAL_KEY in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--status", "--plan"], ["--status", "--step", "pickup"], ["--watch"]])
def test_status_conflicts_are_argparse_errors(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as e:
        parse_grind_session_args(argv)
    assert e.value.code == 2
