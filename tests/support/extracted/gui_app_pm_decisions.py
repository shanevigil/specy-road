"""PM decision helpers shared by the GUI, grind-status, and human-acceptance tests."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from starlette.testclient import TestClient

from specy_road.gui_app import DECISION_CODE_HEADER, create_app
from specy_road.review_files import reviews_dir
from tests.support.extracted.review_override import ROSTER
from tests.support.review import (
    commit_file,
    git,
    make_layout_finish_repo,
    make_review_repo,
    review_text,
)

CODE = "c0de"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
LEDGER = "roadmap/decisions.yaml"
FINDINGS = {"correctness": ["A1 regressed"]}


def question(eid: str, **extra) -> dict:
    """One open decision entry."""
    return {
        "id": eid,
        "node": "M1.1",
        "kind": "decision",
        "summary": f"question {eid}",
        "asked": "2026-11-01",
        "status": "open",
        "why_now": "the leaf needs it",
        "options": [
            {"label": "A", "effect": "a"},
            {"label": "B", "effect": "b"},
        ],
        "recommendation": "A",
        "recommendation_reason": "simpler",
        "default_if_unanswered": "A",
        **extra,
    }


PREFERENCE = {
    "id": "P1",
    "kind": "preference",
    "summary": "docs leaves go to sonnet",
    "asked": "2026-11-01",
    "status": "open",
}


class Layout:
    """The GUI checkout, the leaf worktree, and the origin those decisions push to."""

    def __init__(self, top: Path, prefix: str, leaf: Path, bare: Path | None) -> None:
        self.top, self.prefix, self.leaf, self.bare = top, prefix, leaf, bare
        self.run = top / prefix

    def snapshot(self) -> tuple:
        """Tips, operator markers, the leaf registry, and the server ledger."""
        d = reviews_dir(self.run, "M1.1")
        ledger = self.run / LEDGER
        return (
            git(self.top, "rev-parse", "dev"),
            self.bare and git(self.bare, "rev-parse", "dev"),
            sorted(p.name for p in d.glob("OPERATOR-*")),
            (self.leaf / "roadmap" / "registry.yaml").read_bytes(),
            ledger.read_bytes() if ledger.exists() else None,
        )

    def tip(self) -> str:
        """The integration tip the decision lands on."""
        if self.bare:
            return git(self.bare, "rev-parse", "dev")
        return git(self.top, "rev-parse", "dev")

    def on_dev(self, rel: str, text: str, msg: str) -> None:
        """Commit on the integration branch, and push it when a remote exists."""
        commit_file(self.top, f"{self.prefix}{rel}", text, msg)
        if self.bare:
            git(self.top, "push", "-q", "origin", "dev")


def layout(
    tmp_path: Path,
    monkeypatch,
    shape: str = "root",
    remote: bool = True,
    roster: str = ROSTER,
) -> Layout:
    """A pm-decisions repo of the requested shape."""
    if shape == "root":
        top, prefix = make_review_repo(tmp_path, orchestration=roster), ""
    else:
        top, prefix = make_layout_finish_repo(tmp_path, "nested")[0], "sr/"
        git(top, "checkout", "-q", "dev")
        commit_file(top, f"{prefix}roadmap/orchestration.yaml", roster, "roster")
        git(top, "checkout", "-q", "feature/rm-thing")
        git(top, "merge", "-q", "--no-edit", "dev")
    git(top, "checkout", "-q", "dev")
    commit_file(
        top,
        f"{prefix}.gitignore",
        "work/\n.specyrd/cache/\nroadmap/decisions.local.yaml\n",
        "ignores",
    )
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
    data = yaml.safe_load(
        review_text(commit, model=model, verdict="block", a1="fail").split("---\n")[1]
    )
    data["findings"].update(FINDINGS)
    d = reviews_dir(lay.leaf, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    text = "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n"
    (d / f"REVIEW-{model}.md").write_text(text)


def client(**kw) -> TestClient:
    """A test client whose clock and decision code are fixed."""
    app = create_app(clock=lambda: NOW, **({"decision_code": CODE} | kw))
    return TestClient(app, raise_server_exceptions=False)


def leaf_offer(c: TestClient) -> dict:
    """The claimed leaf's item in the status the modal shows."""
    r = c.get("/api/grind-status", params={"until": "M1.1"}).json()
    return next(i for i in r["held"] + r["active"] if i["id"] == "M1.1")


def approve(c: TestClient, offer: dict, words: str = "false alarm", code: str | None = CODE):
    """Post an approval of the offer."""
    body = {
        "kind": "approve-over-block",
        "node_id": "M1.1",
        "commit": offer["commit"],
        "settles": offer["settles"],
        "words": words,
    }
    headers = {DECISION_CODE_HEADER: code} if code else {}
    return c.post("/api/pm-decisions", json=body, headers=headers)


def answer(c: TestClient, eid: str, option: str | None, words: str, code: str | None = CODE):
    """Post an answer to one decision."""
    body = {"kind": "answer", "id": eid, "option": option, "words": words}
    headers = {DECISION_CODE_HEADER: code} if code else {}
    return c.post("/api/pm-decisions", json=body, headers=headers)


def ledger_at(lay: Layout, rev: str) -> dict:
    """The ledger entries at a git revision, keyed by id."""
    shown = git(lay.top, "show", f"{rev}:{lay.prefix}{LEDGER}")
    return {e["id"]: e for e in yaml.safe_load(shown)["entries"]}


def with_questions(lay: Layout, *entries: dict) -> None:
    """Commit a ledger of these entries on dev."""
    lay.on_dev(LEDGER, yaml.safe_dump({"version": 1, "entries": list(entries)}), "ledger")


def clean(lay: Layout) -> str:
    """The worktree status, which an answer leaves empty."""
    return git(lay.top, "status", "--porcelain")
