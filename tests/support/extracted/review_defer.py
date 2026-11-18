"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.extracted.review_rca import ROSTER
from tests.support.same.run_651387813ee4 import run
from specy_road.review_defer_rules import answer_item
from tests.support.review import commit_file, git
from specy_road.roadmap_load import load_roadmap
import pytest
from tests.support.review import review_text
from specy_road.review_files import reviews_dir
import yaml

ROSTER4 = ROSTER + "  - {id: sonnet, family: anthropic, roles: [reviewer]}\n"

BUDGET = "policy: {max_fix_rounds: 2}\n"

def item(commit: str, **kw) -> dict:
    """Shared test helper."""
    return {"finding": "round 2/opus: CRLF input still warns", "reviewer": "opus", "commit": commit,
            "category": "boundary", "acceptance_id": "A1", "input_class": "CRLF line endings",
            "follow_up_title": "Handle CRLF input", "follow_up_acceptance": "CRLF input parses like LF", **kw}

def record(round_: int, items: list[dict] | None, *, action: str = "defer_findings", disposition_class=None) -> dict:
    """Shared test helper."""
    data = {
        "node_id": "M1.1", "model": "sol", "date": "2026-11-04",
        "trigger": {"rule": "forced", "acceptance_ids": [], "round": round_, "reason": "fix-round budget spent"},
        "classification": {"primary": "hard_problem", "confidence": 0.7},
        "evidence": [{"kind": "finding", "ref": f"round {round_}/opus", "note": "a new input class"}],
        "recommended_action": {"type": action, "instructions": "defer the new class",
                               "requires_human_approval": True},
    }
    if items is not None:
        data["deferred_findings"] = items
    if disposition_class:
        data["classification"]["primary"] = "specification"
        data["criterion_rewrite"] = {
            "acceptance_id": "A1", "original_text": "a.py exists", "proposed_text": "src/a.py exists",
            "finding_disposition": [{"finding": "round 1/opus", "label": "out_of_scope_now",
                                     "input_class": disposition_class}]}
    return data

def write_rca(repo: Path, data: dict) -> Path:
    """Shared test helper."""
    path = reviews_dir(repo, "M1.1") / f"RCA-{data['trigger']['round']}.md"
    path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nreasoning\n")
    return path

def review(repo: Path, model: str, verdict: str = "block") -> None:
    """Shared test helper."""
    notes = repo.parent / f"notes-{model}.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, verdict=verdict,
                                 a1="fail" if verdict == "block" else "pass"), encoding="utf-8")
    assert run("review", "record", "M1.1", "--model", model, "--verdict", verdict,
                "--file", str(notes), "--repo-root", str(repo)) == 0

class Tty:
    def isatty(self) -> bool:
        """Report a terminal, so the prompt is offered."""
        return True

@pytest.fixture
def human(monkeypatch):
    """A person at a terminal answering ``y``."""
    monkeypatch.setattr("sys.stdin", Tty())
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

def untouched(repo: Path) -> None:
    """Shared test helper."""
    assert not (repo / "roadmap" / "decisions.yaml").exists()
    assert not list(reviews_dir(repo, "M1.1").glob("DEFERRAL-*"))
    assert [n["id"] for n in load_roadmap(repo)["nodes"]] == ["M1.1"]

def two_fail_round(repo: Path, n: int, *, correctness: bool) -> None:
    """opus blocks on A1 (boundary) and, when ``correctness``, on A2 with a correctness finding."""
    commit_file(repo, f"src/m{n}.py", f"m = {n}\n", f"mixed {n}")
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1="fail")
    if correctness:
        text = text.replace("A2: pass", "A2: fail").replace("correctness: []", "correctness:\n  - A2 regressed")
    notes = repo.parent / "notes.md"
    notes.write_text(text.replace("boundary: []", "boundary:\n  - CRLF input still warns"))
    assert run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0

def bound_ledger(rca: str, marker_items: list[dict], did: str = "D9") -> dict:
    """A ledger whose one closed decision is worded as ``review defer``'s ``record`` words it."""
    return {"version": 1, "entries": [{
        "id": did, "node": "M1.1", "kind": "decision", "summary": "s",
        "why_now": f"{rca} recommends defer_findings: defer the new class",
        "options": [{"label": "a", "effect": "b"}], "recommendation": "a", "recommendation_reason": "r",
        "default_if_unanswered": "a", "asked": "2026-11-04", "status": "closed", "closed": "2026-11-04",
        "answer": f"Deferred by T <t@e.com> from {rca}: " + "; ".join(f"{answer_item(x)} -> M1.2"
                                                                     for x in marker_items)}]}

def forge_closed_deferral(repo: Path, items: list[dict], round_: int = 2) -> None:
    """An RCA, a closed decision in ``review defer``'s shape and a marker, all written by hand: the gate must
    still re-check the items against the history."""
    write_rca(repo, record(round_, items))
    marker = [{k: x[k] for k in ("reviewer", "commit", "finding", "category", "acceptance_id", "input_class")}
              for x in items]
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump(bound_ledger(f"RCA-{round_}.md", marker)))
    (reviews_dir(repo, "M1.1") / f"DEFERRAL-{round_}.yaml").write_text(yaml.safe_dump(
        {"node_id": "M1.1", "rca": f"RCA-{round_}.md", "round": round_, "decision": "D9", "deferred": marker}))
