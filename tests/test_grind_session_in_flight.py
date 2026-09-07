"""An operator's own in-flight claim is not a dependency block (finding 30)."""

from __future__ import annotations

import json

import pytest

from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts import grind_session_events as gse
from specy_road.bundled_scripts import grind_session_in_flight as gsif
from specy_road.bundled_scripts.grind_session_events import (
    EXIT_BLOCKED,
    EXIT_IN_FLIGHT,
    EXIT_NO_LEAVES,
    EXIT_OK,
    EventEmitter,
)
from specy_road.bundled_scripts.grind_session_in_flight import (
    InFlightClaim,
    handle_no_ready,
    own_in_flight_claims,
    prepare_resume,
)
from specy_road.bundled_scripts.session_plan import BlockedLeaf, SessionPlan, Wave

TS = "2026-09-07T00:00:00Z"


def _plan(ready=None, blocked=None, active=None):
    ready = ready or []
    return SessionPlan(
        under=None,
        ready=list(ready),
        blocked=list(blocked or []),
        active=list(active or []),
        closed=[],
        gated=[],
        gates_open=[],
        needs_codename=[],
        waves=[Wave(index=0, node_ids=list(ready))] if ready else [],
        parallel_batches=[list(ready)] if ready else [],
        totals={"ready": len(ready)},
    )


def _reg(*entries):
    return {"version": 1, "entries": list(entries)}


def _entry(node_id, codename, branch=None):
    return {
        "node_id": node_id,
        "codename": codename,
        "branch": branch or f"feature/rm-{codename}",
    }


def _events(capsys):
    out = capsys.readouterr().out.strip().splitlines()
    return [json.loads(line) for line in out if line.strip()]


# ---------------------------------------------------------------------------
# Ownership: a registry row alone is not proof
# ---------------------------------------------------------------------------


def test_claim_needs_both_a_registry_row_and_a_local_branch(tmp_path):
    reg = _reg(_entry("M1.1", "mine"), _entry("M1.2", "theirs"))
    claims = own_in_flight_claims(
        tmp_path, reg, ["M1.1", "M1.2"],
        branch_exists=lambda _root, b: b == "feature/rm-mine",
    )
    assert [c.node_id for c in claims] == ["M1.1"]
    assert claims[0].branch == "feature/rm-mine"


def test_in_progress_without_a_registry_row_is_not_a_claim(tmp_path):
    """Another lane's leaf reaches ``active`` via status alone; never resume it."""
    claims = own_in_flight_claims(
        tmp_path, _reg(), ["M1.1"], branch_exists=lambda _root, _b: True
    )
    assert claims == []


def test_ownership_probe_is_resolved_at_call_time(monkeypatch, tmp_path):
    """Binding the probe as a default would freeze it at import."""
    monkeypatch.setattr(gsif, "local_branch_exists", lambda _root, _b: True)
    claims = own_in_flight_claims(tmp_path, _reg(_entry("M1.1", "cn")), ["M1.1"])
    assert [c.node_id for c in claims] == ["M1.1"]


# ---------------------------------------------------------------------------
# Classification: in-flight outranks blocked
# ---------------------------------------------------------------------------


def test_own_claim_wins_over_a_blocked_leaf_waiting_on_it(monkeypatch, capsys, tmp_path):
    """The downstream leaf is blocked *on* the claim, so both buckets are full."""
    monkeypatch.setattr(gse, "_now_iso", lambda: TS)
    plan = _plan(
        ready=[],
        blocked=[BlockedLeaf("M1.2", "cn2", ["M1.1"], "dependency")],
        active=["M1.1"],
    )
    code = handle_no_ready(
        EventEmitter(as_json=True), plan, 0,
        repo_root=tmp_path, reg=_reg(_entry("M1.1", "mine")),
        claims_fn=lambda *_a, **_k: [InFlightClaim("M1.1", "mine", "feature/rm-mine")],
    )
    assert code == EXIT_IN_FLIGHT
    event = _events(capsys)[-1]
    assert event["event"] == "in_flight"
    assert event["node_id"] == "M1.1"
    assert event["branch"] == "feature/rm-mine"


def test_someone_elses_claim_still_reports_as_blocked(capsys, tmp_path):
    plan = _plan(
        ready=[],
        blocked=[BlockedLeaf("M1.2", "cn2", ["M1.1"], "dependency")],
        active=["M1.1"],
    )
    code = handle_no_ready(
        EventEmitter(as_json=True), plan, 0,
        repo_root=tmp_path, reg=_reg(), claims_fn=lambda *_a, **_k: [],
    )
    assert code == EXIT_BLOCKED
    assert _events(capsys)[-1]["event"] == "blocked"


@pytest.mark.parametrize(
    "finished,expected,reason",
    [(0, EXIT_NO_LEAVES, "no_actionable_leaves"), (2, EXIT_OK, "no_work")],
)
def test_nothing_in_flight_and_nothing_blocked(capsys, tmp_path, finished, expected, reason):
    code = handle_no_ready(
        EventEmitter(as_json=True), _plan(), finished,
        repo_root=tmp_path, reg=_reg(), claims_fn=lambda *_a, **_k: [],
    )
    assert code == expected
    assert _events(capsys)[-1]["reason"] == reason


def test_human_message_names_the_node_the_branch_and_the_way_out(capsys, tmp_path):
    handle_no_ready(
        EventEmitter(as_json=False), _plan(active=["M1.3.2"]), 0,
        repo_root=tmp_path, reg=_reg(),
        claims_fn=lambda *_a, **_k: [
            InFlightClaim("M1.3.2", "tradelog", "feature/rm-tradelog"),
        ],
    )
    text = capsys.readouterr().out
    assert "M1.3.2" in text and "feature/rm-tradelog" in text
    assert "finish-this-task" in text
    assert "abort-task-pickup" in text
    assert "--resume-in-flight" in text


def test_extra_claims_are_listed_but_only_one_is_named(capsys, tmp_path):
    handle_no_ready(
        EventEmitter(as_json=False), _plan(active=["M1.1", "M1.2"]), 0,
        repo_root=tmp_path, reg=_reg(),
        claims_fn=lambda *_a, **_k: [
            InFlightClaim("M1.1", "a", "feature/rm-a"),
            InFlightClaim("M1.2", "b", "feature/rm-b"),
        ],
    )
    assert "also claimed here: M1.2" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def _artifacts(repo_root, node_id, *, brief="brief", prompt="prompt"):
    work = repo_root / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / f"brief-{node_id}.md").write_text(brief, encoding="utf-8")
    (work / f"prompt-{node_id}.md").write_text(prompt, encoding="utf-8")


def test_prepare_resume_checks_out_and_keeps_existing_artifacts(tmp_path):
    _artifacts(tmp_path, "M1.1", prompt="hand-edited")
    seen = []
    error = prepare_resume(
        tmp_path,
        InFlightClaim("M1.1", "cn", "feature/rm-cn"),
        [{"id": "M1.1", "codename": "cn"}],
        on_complete="merge",
        checkout=lambda _root, b: (seen.append(b), (0, ""))[1],
    )
    assert error is None
    assert seen == ["feature/rm-cn"]
    assert (tmp_path / "work" / "prompt-M1.1.md").read_text() == "hand-edited"


def test_prepare_resume_reports_a_failed_checkout(tmp_path):
    error = prepare_resume(
        tmp_path,
        InFlightClaim("M1.1", "cn", "feature/rm-cn"),
        [{"id": "M1.1"}],
        on_complete="merge",
        checkout=lambda _root, _b: (1, "would be overwritten"),
    )
    assert error is not None
    assert "would be overwritten" in error


def test_prepare_resume_rejects_a_claim_with_no_node(tmp_path):
    error = prepare_resume(
        tmp_path,
        InFlightClaim("M9.9", "gone", "feature/rm-gone"),
        [{"id": "M1.1"}],
        on_complete="merge",
        checkout=lambda _root, _b: (0, ""),
    )
    assert error is not None
    assert "abort-task-pickup" in error


def test_loop_resumes_instead_of_exiting_six(monkeypatch, capsys, tmp_path):
    from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args

    _artifacts(tmp_path, "M1.1")
    monkeypatch.setattr(gse, "_now_iso", lambda: TS)
    monkeypatch.setattr(gsif, "local_branch_exists", lambda _root, _b: True)
    monkeypatch.setattr(gsif, "checkout_branch", lambda _root, _b: (0, ""))

    plans = [
        (_plan(active=["M1.1"]), _reg(_entry("M1.1", "cn"))),
        (_plan(), _reg()),
    ]
    calls: list[str] = []

    def fake_gather(_repo_root, _under):
        plan, reg = plans[min(len(calls), len(plans) - 1)]
        return [{"id": "M1.1", "codename": "cn"}], reg, plan

    def fake_run_cli(_repo_root, cli_args):
        calls.append(cli_args[0])
        return 0

    monkeypatch.setattr(gs, "gather_plan", fake_gather)
    monkeypatch.setattr(gs, "_run_cli", fake_run_cli)
    monkeypatch.setattr(gs, "_run_shell", lambda *_a, **_k: 0)

    args = parse_grind_session_args([
        "--on-complete", "merge", "--implement-mode", "hook",
        "--implement-cmd", "true", "--resume-in-flight",
        "--json", "--repo-root", str(tmp_path),
    ])
    code = gs.run_session(args)

    assert code == EXIT_OK
    events = [e["event"] for e in _events(capsys)]
    assert "resumed" in events
    assert "finished" in events
    # Pickup is skipped: the claim is already registered and branched.
    assert "do-next-available-task" not in calls
    assert "finish-this-task" in calls


def test_loop_without_the_flag_stops_with_exit_six(monkeypatch, capsys, tmp_path):
    from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args

    monkeypatch.setattr(gse, "_now_iso", lambda: TS)
    monkeypatch.setattr(gsif, "local_branch_exists", lambda _root, _b: True)
    monkeypatch.setattr(
        gs, "gather_plan",
        lambda _r, _u: ([{"id": "M1.1", "codename": "cn"}],
                        _reg(_entry("M1.1", "cn")),
                        _plan(active=["M1.1"])),
    )
    monkeypatch.setattr(gs, "_run_cli", lambda *_a, **_k: 0)

    args = parse_grind_session_args([
        "--on-complete", "merge", "--implement-mode", "hook",
        "--implement-cmd", "true", "--json", "--repo-root", str(tmp_path),
    ])
    assert gs.run_session(args) == EXIT_IN_FLIGHT
    assert _events(capsys)[-1]["event"] == "in_flight"
