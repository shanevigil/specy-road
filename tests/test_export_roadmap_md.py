"""Tests for markdown export."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import export_roadmap_md as em


def test_export_check_matches_repo() -> None:
    script = str(REPO / "scripts" / "export_roadmap_md.py")
    subprocess.run([sys.executable, script, "--check"], cwd=REPO, check=True)


def _phase_subtree(**extra) -> list[dict]:
    node = {
        "id": "M1",
        "parent_id": None,
        "type": "phase",
        "title": "Test phase",
        "status": "Not Started",
    }
    node.update(extra)
    return [node]


def test_render_phase_doc_includes_goal() -> None:
    subtree = _phase_subtree(goal="Ship the feature.")
    out = em.render_phase_doc("M1", subtree)
    assert "**Goal:** Ship the feature." in out


def test_render_phase_doc_includes_acceptance() -> None:
    subtree = _phase_subtree(acceptance=["All tests pass", "Docs updated"])
    out = em.render_phase_doc("M1", subtree)
    assert "**Acceptance criteria:**" in out
    assert "- All tests pass" in out
    assert "- Docs updated" in out


def test_render_phase_doc_decision_pending() -> None:
    subtree = _phase_subtree(decision={"status": "pending"})
    out = em.render_phase_doc("M1", subtree)
    assert "> Decision pending" in out


def test_render_phase_doc_decision_decided() -> None:
    subtree = _phase_subtree(
        decision={
            "status": "decided",
            "decided_date": "2026-04-05",
            "adr_ref": "docs/adr/ADR-001.md",
        }
    )
    out = em.render_phase_doc("M1", subtree)
    assert "> Decided (2026-04-05) — docs/adr/ADR-001.md" in out


def test_render_phase_doc_no_details_section_when_absent() -> None:
    subtree = _phase_subtree()
    out = em.render_phase_doc("M1", subtree)
    assert "## Details" not in out
