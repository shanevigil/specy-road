"""M17.15: ``POST /api/pm-decisions`` records a PM decision from the status modal behind the startup code.

M22.67's layouts with the review gate on: the GUI's checkout is the coordinator's, on the integration branch,
and the leaf is in its own worktree; with a remote the decision is pushed to the bare origin, with none the local
branch moves. ``create_app(decision_code=CODE)`` fixes the code. "Nothing recorded" (:meth:`Layout.snapshot`):
the integration tips (local and origin), the marker directory, the leaf registry and the server's ledger.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient

from specy_road.gui_app import DECISION_CODE_HEADER, NOT_STAMPED, create_app
from specy_road.init_project import project_template_root
from specy_road.orchestration_role_env import ROLE_ENV
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_override import block_item, shortfall_text
from tests.review_repo_helpers import NODE, commit_file, git, make_layout_finish_repo, make_review_repo, review_text
from tests.test_review_override import ROSTER, STRONG

CODE = "c0de"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
LEDGER = "roadmap/decisions.yaml"
FINDINGS = {"correctness": ["A1 regressed"]}


def question(eid: str, **extra) -> dict:
    return {"id": eid, "node": "M1.1", "kind": "decision", "summary": f"question {eid}", "asked": "2026-11-01",
            "status": "open", "why_now": "the leaf needs it",
            "options": [{"label": "A", "effect": "a"}, {"label": "B", "effect": "b"}], "recommendation": "A",
            "recommendation_reason": "simpler", "default_if_unanswered": "A", **extra}


PREFERENCE = {"id": "P1", "kind": "preference", "summary": "docs leaves go to sonnet", "asked": "2026-11-01",
              "status": "open"}


@pytest.fixture(autouse=True)
def manual_coordinator(monkeypatch):
    monkeypatch.delenv(ROLE_ENV, raising=False)


class Layout:
    """``top``: the GUI's (coordinator's) checkout; ``run``: its project root; ``leaf``: the leaf's project root in
    its own worktree; ``prefix``: the project's place under the git root; ``bare``: the origin, or ``None``."""

    def __init__(self, top: Path, prefix: str, leaf: Path, bare: Path | None) -> None:
        self.top, self.prefix, self.leaf, self.bare = top, prefix, leaf, bare
        self.run = top / prefix

    def snapshot(self) -> tuple:
        d = reviews_dir(self.run, "M1.1")
        ledger = self.run / LEDGER
        return (git(self.top, "rev-parse", "dev"), self.bare and git(self.bare, "rev-parse", "dev"),
                sorted(p.name for p in d.glob("OPERATOR-*")), (self.leaf / "roadmap" / "registry.yaml").read_bytes(),
                ledger.read_bytes() if ledger.exists() else None)

    def tip(self) -> str:
        return git(self.bare, "rev-parse", "dev") if self.bare else git(self.top, "rev-parse", "dev")

    def on_dev(self, rel: str, text: str, msg: str) -> None:
        """Commit on the integration branch (and push it, with a remote), from the GUI's checkout."""
        commit_file(self.top, f"{self.prefix}{rel}", text, msg)
        if self.bare:
            git(self.top, "push", "-q", "origin", "dev")


def layout(tmp_path: Path, monkeypatch, shape: str = "root", remote: bool = True, roster: str = ROSTER) -> Layout:
    if shape == "root":
        top, prefix = make_review_repo(tmp_path, orchestration=roster), ""
    else:
        top, prefix = make_layout_finish_repo(tmp_path, "nested")[0], "sr/"
        git(top, "checkout", "-q", "dev")
        commit_file(top, f"{prefix}roadmap/orchestration.yaml", roster, "roster")
        git(top, "checkout", "-q", "feature/rm-thing")
        git(top, "merge", "-q", "--no-edit", "dev")
    git(top, "checkout", "-q", "dev")
    commit_file(top, f"{prefix}.gitignore", "work/\n.specyrd/cache/\nroadmap/decisions.local.yaml\n", "ignores")
    git(top, "checkout", "-q", "feature/rm-thing")
    git(top, "merge", "-q", "--no-edit", "dev")
    git(top, "checkout", "-q", "dev")
    bare = None
    if remote:
        bare = tmp_path / "remote.git"
        git(tmp_path, "clone", "-q", "--bare", str(top), str(bare))
        git(top, "remote", "add", "origin", str(bare))
        git(top, "fetch", "-q", "origin")
        git(top, "remote", "set-head", "origin", "dev")
    leaf = tmp_path / "leaf"
    git(top, "worktree", "add", "-q", str(leaf), "feature/rm-thing")
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(top / prefix))
    return Layout(top, prefix, leaf / prefix, bare)


def block(lay: Layout, model: str = "opus") -> None:
    """``model`` blocks the leaf's commit under review on A1."""
    commit = git(lay.leaf, "rev-parse", "HEAD")
    data = yaml.safe_load(review_text(commit, model=model, verdict="block", a1="fail").split("---\n")[1])
    data["findings"].update(FINDINGS)
    d = reviews_dir(lay.leaf, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")


def client(**kw) -> TestClient:
    return TestClient(create_app(clock=lambda: NOW, **({"decision_code": CODE} | kw)), raise_server_exceptions=False)


def leaf_offer(c: TestClient) -> dict:
    """The claimed leaf's item in the status the modal shows."""
    r = c.get("/api/grind-status", params={"until": "M1.1"}).json()
    return next(i for i in r["held"] + r["active"] if i["id"] == "M1.1")


def approve(c: TestClient, offer: dict, words: str = "false alarm", code: str | None = CODE):
    body = {"kind": "approve-over-block", "node_id": "M1.1", "commit": offer["commit"], "settles": offer["settles"],
            "words": words}
    return c.post("/api/pm-decisions", json=body, headers={DECISION_CODE_HEADER: code} if code else {})


def answer(c: TestClient, eid: str, option: str | None, words: str, code: str | None = CODE):
    return c.post("/api/pm-decisions", json={"kind": "answer", "id": eid, "option": option, "words": words},
                  headers={DECISION_CODE_HEADER: code} if code else {})


def ledger_at(lay: Layout, rev: str) -> dict:
    return {e["id"]: e for e in yaml.safe_load(git(lay.top, "show", f"{rev}:{lay.prefix}{LEDGER}"))["entries"]}


def with_questions(lay: Layout, *entries: dict) -> None:
    lay.on_dev(LEDGER, yaml.safe_dump({"version": 1, "entries": list(entries)}), "ledger")


def clean(lay: Layout) -> str:
    return git(lay.top, "status", "--porcelain")


# --- answers -----------------------------------------------------------------


def test_an_answer_closes_the_entry_on_the_integration_branch(tmp_path: Path, monkeypatch) -> None:
    lay = layout(tmp_path, monkeypatch)
    with_questions(lay, question("D1"), question("D3"))
    sheet, server_ledger = (lay.run / NODE["planning_dir"]).read_bytes(), (lay.run / LEDGER).read_bytes()
    c = client()
    for eid, option, words, want in (("D1", "A", "ship A", "A: ship A"), ("D3", None, "neither", "neither")):
        before = lay.tip()
        r = answer(c, eid, option, words)
        assert r.status_code == 200, r.text
        tip = lay.tip()
        assert r.json() == {"id": eid, "integration_commit": tip, "destination": "origin/dev"}
        assert git(lay.bare, "rev-list", "--count", f"{before}..{tip}") == "1"
        assert git(lay.bare, "show", "--name-only", "--format=", tip).splitlines() == [LEDGER]
        e = ledger_at(lay, "origin/dev")[eid]
        assert (e["status"], e["answer"], e["decided_by"], e["channel"]) == ("closed", want, "operator", "pm-gui")
    assert (lay.run / NODE["planning_dir"]).read_bytes() == sheet
    assert clean(lay) == "" and (lay.run / LEDGER).read_bytes() == server_ledger


def test_a_local_answer_closes_in_place(tmp_path: Path, monkeypatch) -> None:
    lay = layout(tmp_path, monkeypatch)
    local = lay.run / "roadmap" / "decisions.local.yaml"
    local.write_text(yaml.safe_dump({"version": 1, "entries": [question("D2")]}))
    before = lay.snapshot()
    r = answer(client(), "D2", "B", "only here")
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "D2", "integration_commit": None, "destination": "local ledger"}
    (e,) = yaml.safe_load(local.read_text())["entries"]
    assert (e["status"], e["answer"], e["channel"], e["decided_by"]) == ("closed", "B: only here", "pm-gui", "operator")
    assert lay.snapshot() == before and clean(lay) == ""


# --- approval over a block -----------------------------------------------------


@pytest.mark.parametrize(("shape", "remote"), [("root", True), ("sr", True), ("root", False)])
def test_an_approval_over_a_block_is_m22_67s_record_with_the_channel(tmp_path: Path, monkeypatch, shape: str,
                                                                    remote: bool) -> None:
    lay = layout(tmp_path, monkeypatch, shape, remote)
    block(lay)
    c = client()
    offer = leaf_offer(c)
    head = git(lay.leaf, "rev-parse", "HEAD")
    assert (offer["commit"], offer["can_approve_over_block"]) == (head, True)
    assert offer["settles"] == [block_item("opus", head, FINDINGS), shortfall_text(1, 0)]
    before, registry = lay.tip(), (lay.leaf / "roadmap" / "registry.yaml").read_bytes()
    r = approve(c, offer)
    assert r.status_code == 200, r.text
    tip = lay.tip()
    where = "origin/dev" if remote else "local dev"
    assert r.json() == {"id": "D1", "integration_commit": tip, "destination": where, "gate_met": True}
    repo = lay.bare or lay.top
    assert git(repo, "rev-list", "--count", f"{before}..{tip}") == "1"
    assert git(repo, "show", "--name-only", "--format=", tip).splitlines() == [f"{lay.prefix}{LEDGER}"]
    e = ledger_at(lay, tip)["D1"]
    for part in (f"for commit {head},", block_item("opus", head, FINDINGS), '"false alarm"', "T <t@e.com>"):
        assert part in e["answer"]
    assert (e["status"], e["kind"], e["decided_by"], e["channel"]) == ("closed", "decision", "operator", "pm-gui")
    marker = yaml.safe_load((reviews_dir(lay.run, "M1.1") / f"OPERATOR-{head}.yaml").read_text())
    assert marker["decision"] == "D1" and marker["session"].startswith("pm-gui ")
    assert (lay.leaf / "roadmap" / "registry.yaml").read_bytes() == registry   # the coordinator stamps it
    assert evaluate_gate(lay.leaf, NODE, head, branch="feature/rm-thing").passed
    assert clean(lay) == ""
    if remote:
        assert not (lay.run / LEDGER).exists()   # the server's ledger is unchanged


def test_the_gate_still_unmet_after_the_commit_is_reported_recorded(tmp_path: Path, monkeypatch) -> None:
    lay = layout(tmp_path, monkeypatch)
    block(lay)
    c = client()
    offer = leaf_offer(c)
    late = tmp_path / "REVIEW-sol.md"
    data = yaml.safe_load(review_text(offer["commit"], model="sol", verdict="block", a1="fail").split("---\n")[1])
    late.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")
    hook = lay.top / ".git" / "hooks" / "post-commit"   # the temporary worktree shares it
    hook.write_text(f"#!/bin/sh\ncp '{late}' '{reviews_dir(lay.run, 'M1.1')}/REVIEW-sol.md'\n")
    hook.chmod(0o755)
    before = lay.tip()
    r = approve(c, offer)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["id"], body["integration_commit"], body["destination"], body["gate_met"]) == (
        "D1", lay.tip(), "origin/dev", False)
    assert NOT_STAMPED in body["detail"] and lay.tip() != before
    assert list(reviews_dir(lay.run, "M1.1").glob("OPERATOR-*.yaml"))
    assert c.get("/api/health").status_code == 200


def test_an_old_copied_schema_refuses_both_kinds_naming_refresh_schemas(tmp_path: Path, monkeypatch) -> None:
    lay = layout(tmp_path, monkeypatch)
    schema = json.loads((project_template_root() / "schemas" / "decisions.schema.json").read_text())
    del schema["$defs"]["entry"]["properties"]["channel"]
    lay.on_dev("schemas/decisions.schema.json", json.dumps(schema), "a schema copied before channel")
    with_questions(lay, question("D1"))
    git(lay.leaf, "merge", "-q", "--no-edit", "dev")
    block(lay)
    c = client()
    offer = leaf_offer(c)
    before = lay.snapshot()
    for r in (answer(c, "D1", "A", "ship A"), approve(c, offer)):
        assert r.status_code == 400 and "specy-road refresh-schemas" in r.json()["detail"], r.text
    assert lay.snapshot() == before and c.get("/api/health").status_code == 200


# --- the code ------------------------------------------------------------------


@pytest.mark.parametrize("code", [None, "wrong", CODE.upper()])
def test_a_missing_or_wrong_code_is_refused(tmp_path: Path, monkeypatch, code: str | None) -> None:
    lay = layout(tmp_path, monkeypatch)
    with_questions(lay, question("D1"))
    block(lay)
    c = client()
    offer = leaf_offer(c)
    before = lay.snapshot()
    assert answer(c, "D1", "A", "ship A", code=code).status_code == 403
    assert approve(c, offer, code=code).status_code == 403
    assert lay.snapshot() == before


def test_read_only_refuses_and_draws_no_code(tmp_path: Path, monkeypatch, capsys) -> None:
    lay = layout(tmp_path, monkeypatch)
    with_questions(lay, question("D1"))
    before = lay.snapshot()
    capsys.readouterr()
    with TestClient(create_app(read_only=True)) as c:
        assert answer(c, "D1", "A", "ship A").status_code == 403
    assert "PM decisions" not in capsys.readouterr().err and lay.snapshot() == before


def test_the_code_is_shown_once_on_stderr_and_nowhere_else(tmp_path: Path, monkeypatch, capsys, caplog) -> None:
    lay = layout(tmp_path, monkeypatch)
    with_questions(lay, question("D1"))
    capsys.readouterr()
    app = create_app()
    seen: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as c:
        err = capsys.readouterr().err
        (line,) = [x for x in err.splitlines() if x.startswith("PM decisions: ")]
        code = line.split("decision: ", 1)[1].split(" ", 1)[0]
        assert len(code) >= 16 and err.count(code) == 1
        for route in app.routes:
            if "GET" in getattr(route, "methods", ()):
                r = c.get(route.path.replace("{", "").replace("}", "").replace(":path", ""))
                seen += [r.text, json.dumps(dict(r.headers))]
        r = answer(c, "D1", "A", "ship A", code=code)
        assert r.status_code == 200, r.text
        seen += [r.text, json.dumps(dict(r.headers))]
    assert not any(code in s for s in seen)
    assert code not in capsys.readouterr().err and code not in caplog.text
    assert code not in "".join(os.environ.values())
    for p in tmp_path.rglob("*"):
        if p.is_file() and not p.is_symlink():
            assert code.encode() not in p.read_bytes(), p


def test_another_origin_is_refused_the_preflight(tmp_path: Path, monkeypatch) -> None:
    layout(tmp_path, monkeypatch)
    r = client().options("/api/pm-decisions", headers={
        "Origin": "https://example.com", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": DECISION_CODE_HEADER})
    assert "access-control-allow-origin" not in r.headers


# --- refusals --------------------------------------------------------------------


def _on_origin(lay: Layout, tmp_path: Path, **change) -> None:
    """Another clone changes D1 on the integration branch after the GUI read it."""
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", "dev", str(lay.bare), str(other))
    path = other / LEDGER
    doc = yaml.safe_load(path.read_text())
    doc["entries"][0].update(change)
    path.write_text(yaml.safe_dump(doc))
    git(other, "-c", "user.email=o@e.com", "-c", "user.name=O", "commit", "-qam", "D1 changed elsewhere")
    git(other, "push", "-q", "origin", "dev")


def _close_on_origin(lay: Layout, tmp_path: Path) -> None:
    _on_origin(lay, tmp_path, status="closed", answer="B", closed="2026-11-10")


def _options_changed_on_origin(lay: Layout, tmp_path: Path) -> None:
    _on_origin(lay, tmp_path, options=[{"label": "C", "effect": "c"}], recommendation="C", default_if_unanswered="C")


def _close_here(lay: Layout, _tmp: Path) -> None:
    path = lay.run / LEDGER
    doc = yaml.safe_load(path.read_text())
    doc["entries"][0].update(status="closed", answer="B", closed="2026-11-10")
    commit_file(lay.top, LEDGER, yaml.safe_dump(doc), "closed here")


ANSWER_REFUSALS = {   # (option, words, id, setup after the report) -> status
    "empty_words": (("A", "  ", "D1", None), 400),
    "multiline_words": (("A", "ship A\nnow", "D1", None), 400),   # no one-line sheet record could match it
    "options_changed_on_origin": (("A", "ship A", "D1", _options_changed_on_origin), 400),
    "not_a_label": (("C", "ship C", "D1", None), 400),
    "unknown_id": (("A", "ship A", "D9", None), 400),
    "preference": ((None, "drop it", "P1", None), 400),
    "closed_here": (("A", "ship A", "D1", _close_here), 409),
    "closed_on_origin": (("A", "ship A", "D1", _close_on_origin), 409),
}


@pytest.mark.parametrize("case", sorted(ANSWER_REFUSALS))
def test_an_answer_refusal_records_nothing(tmp_path: Path, monkeypatch, case: str) -> None:
    (option, words, eid, setup), status = ANSWER_REFUSALS[case]
    lay = layout(tmp_path, monkeypatch)
    with_questions(lay, question("D1"), PREFERENCE)
    if setup:
        setup(lay, tmp_path)
    before = lay.snapshot()
    r = answer(client(), eid, option, words)
    assert r.status_code == status, r.text
    assert lay.snapshot() == before


def _moved(lay: Layout, _tmp: Path) -> None:
    commit_file(lay.leaf, "src/later.py", "x\n", "one more commit")


def _second_block(lay: Layout, _tmp: Path) -> None:
    block(lay, "sol")


@pytest.mark.parametrize("case", ["empty_words", "multiline_words", "stale_commit", "stale_settles"])
def test_an_approval_refusal_records_nothing(tmp_path: Path, monkeypatch, case: str) -> None:
    lay = layout(tmp_path, monkeypatch)
    block(lay)
    c = client()
    offer = leaf_offer(c)
    {"stale_commit": _moved, "stale_settles": _second_block}.get(case, lambda *_a: None)(lay, tmp_path)
    before = lay.snapshot()
    words = {"empty_words": "", "multiline_words": "false\r\nalarm"}.get(case, "false alarm")
    r = approve(c, offer, words=words)
    assert r.status_code == (400 if case.endswith("_words") else 409), r.text
    assert lay.snapshot() == before


def _no_email(lay: Layout, monkeypatch) -> str:
    empty = lay.top.parent / "empty.gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    git(lay.top, "config", "--unset", "user.email")
    return "git identity"


def _executor(_lay: Layout, monkeypatch) -> str:
    monkeypatch.setenv(ROLE_ENV, "executor")
    return ROLE_ENV


@pytest.mark.parametrize("case", ["strong_review", "role", "identity"])
def test_a_withheld_approval_names_why_and_records_nothing(tmp_path: Path, monkeypatch, case: str) -> None:
    lay = layout(tmp_path, monkeypatch, roster=STRONG if case == "strong_review" else ROSTER)
    block(lay)
    c = client()
    offer = leaf_offer(c)
    named = {"strong_review": lambda *_a: "strong_review[0]", "role": _executor, "identity": _no_email}[case](
        lay, monkeypatch)
    before = lay.snapshot()
    r = approve(c, offer)
    assert r.status_code == 400 and named in r.json()["detail"], r.text
    assert lay.snapshot() == before


def test_a_refused_push_records_nothing(tmp_path: Path, monkeypatch) -> None:
    lay = layout(tmp_path, monkeypatch)
    hook = lay.bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho protected >&2\nexit 1\n")
    hook.chmod(0o755)
    block(lay)
    c = client()
    offer = leaf_offer(c)
    before = lay.snapshot()
    r = approve(c, offer)
    assert r.status_code == 400 and "git push origin" in r.json()["detail"], r.text
    assert lay.snapshot() == before and c.get("/api/health").status_code == 200
