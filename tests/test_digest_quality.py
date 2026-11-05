"""The digest's "Quality by area" section: which areas keep costing extra review.

Every input is tracked (``specy_road/review_tally.py``): completion and gate commits reachable from HEAD, their
``Review-tally`` trailers, the live graph (or the graph at completion for an archived leaf) and the policy as
committed at HEAD. These tests pin the population, the rates, the ordering and the determinism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.digest import render_digest
from specy_road.history_index import clear_memo
from tests.test_digest import headings
from tests.test_history_walk import commit, git, repo

__all__ = ["repo"]  # re-exported fixture


@pytest.fixture(autouse=True)
def _no_memo() -> None:
    clear_memo()


def _gate_commit(repo: Path, codename: str, tally: str | None = None) -> None:
    """A leaf's gate commit as mark-implementation-reviewed writes it: a registry-only change, a tally trailer."""
    with (repo / "roadmap" / "registry.yaml").open("a", encoding="utf-8") as fh:
        fh.write(f"# gate {codename}\n")
    trailers = "Reviewed-by: human (human) approve abc1234" + (f"\nReview-tally: {tally}" if tally else "")
    commit(repo, f"chore(rm-{codename}): mark implementation reviewed\n\n{trailers}")


def _land(repo: Path, codename: str, tally: str | None = None) -> None:
    """Gate, then finish-this-task's completion commit: the leaf is completed in HEAD's history."""
    _gate_commit(repo, codename, tally)
    with (repo / "roadmap" / "registry.yaml").open("a", encoding="utf-8") as fh:
        fh.write(f"# done {codename}\n")
    commit(repo, f"chore(rm-{codename}): complete, deregister")


def _quality(text: str) -> list[str]:
    lines = text.splitlines()
    if "## Quality by area" not in lines:
        return []
    start = lines.index("## Quality by area")
    return [ln for ln in lines[start:] if ln.startswith("| `")]


def _tally(node: str, rounds: int, blocks: int, integrity: int = 0, rca: int = 0) -> str:
    return f"{node} rounds={rounds} blocks={blocks} approvals=1 integrity={integrity} rca={rca} findings=none"


def _history(repo: Path) -> None:
    _land(repo, "api-contract-outline")   # landed before tallies existed: shared/, no tally
    _land(repo, "contracts-bootstrap", _tally("M0.1", 3, 2, 1, 1))
    _land(repo, "roadmap-ci", _tally("M0.2", 1, 0))


def _set_policy(repo: Path, extra: str) -> None:
    """Commit policy keys: the section reads the policy as committed at HEAD."""
    orch = repo / "roadmap" / "orchestration.yaml"
    orch.write_text(orch.read_text().replace(
        "  reviewer_fresh_session: true\n", f"  reviewer_fresh_session: true\n{extra}"))
    commit(repo, "policy")


SECTION = [
    "| `shared` **flagged** | 2 | 1 | 3.00 | 100% | 1 | 1 |",
    "| `roadmap` | 1 | 0 | 1.00 | 0% | 0 | 0 |",
    "| `schemas` | 2 | 0 | 2.00 | 50% | 1 | 1 |",   # 50% is not above the default 0.5
]


def test_quality_section_lists_flagged_areas_first_with_their_numbers(repo: Path) -> None:
    _history(repo)
    text = render_digest(repo)
    assert _quality(text) == SECTION
    assert headings(text)[-2:] == ["Quality by area", "Reaching the detail behind this"]


def test_quality_policy_sets_window_and_threshold(repo: Path) -> None:
    _history(repo)
    _set_policy(repo, "  quality_window: 2\n  quality_threshold: 0.4\n")
    # The window is the newest two completed leaves (M0.2, M0.1); the untallied M0.3 falls out of it.
    assert _quality(render_digest(repo)) == [
        "| `schemas` **flagged** | 2 | 0 | 2.00 | 50% | 1 | 1 |",
        "| `shared` **flagged** | 1 | 0 | 3.00 | 100% | 1 | 1 |",
        "| `roadmap` | 1 | 0 | 1.00 | 0% | 0 | 0 |",
    ]


def test_a_gated_leaf_that_has_not_completed_is_not_counted_and_evicts_nothing(repo: Path) -> None:
    _set_policy(repo, "  quality_window: 1\n")
    _land(repo, "contracts-bootstrap", _tally("M0.1", 3, 2))
    _gate_commit(repo, "roadmap-ci", _tally("M0.2", 4, 4))   # approved, still In Progress: no completion commit
    assert _quality(render_digest(repo)) == [
        "| `schemas` **flagged** | 1 | 0 | 3.00 | 100% | 0 | 0 |",
        "| `shared` **flagged** | 1 | 0 | 3.00 | 100% | 0 | 0 |",
    ]


def test_an_archived_completed_leaf_keeps_its_place_in_the_window(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    _history(repo)
    archive_node(repo, "M0.1")
    commit(repo, "archive M0.1")
    clear_memo()
    assert _quality(render_digest(repo)) == SECTION


def test_quality_section_is_byte_identical_across_runs_clocks_overlays_and_checkouts(
    repo: Path, tmp_path: Path, monkeypatch
) -> None:
    _history(repo)
    first = render_digest(repo)
    # Local review records and the availability overlay are gitignored and differ per checkout; neither matters.
    history = repo / "work" / "reviews" / "M0.2" / "history"
    history.mkdir(parents=True)
    (history / "001.md").write_text("---\nverdict: block\n---\n", encoding="utf-8")
    monkeypatch.setattr("time.time", lambda: 4_000_000_000.0)
    assert render_digest(repo) == first
    local = repo / "roadmap" / "orchestration.local.yaml"
    for overlay in ("roster: [\n", "roster:\n  human: {available: false}\n"):   # malformed, then valid
        local.write_text(overlay, encoding="utf-8")
        assert render_digest(repo) == first, overlay
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    clear_memo()
    assert _quality(render_digest(clone)) == _quality(first) == SECTION


def test_a_local_overlay_cannot_change_the_committed_quality_policy(repo: Path) -> None:
    _history(repo)
    _set_policy(repo, "  quality_threshold: 1\n")
    clean = _quality(render_digest(repo))
    assert clean[0] == "| `roadmap` | 1 | 0 | 1.00 | 0% | 0 | 0 |"   # 100% is not above 1: nothing flagged
    (repo / "roadmap" / "orchestration.local.yaml").write_text("roster: [\n", encoding="utf-8")
    assert _quality(render_digest(repo)) == clean


def test_legacy_only_history_counts_its_leaves_with_no_rates(repo: Path) -> None:
    assert "Quality by area" not in render_digest(repo)   # no completed leaf: no section
    _gate_commit(repo, "roadmap-ci", _tally("M0.2", 1, 0))   # gated, not completed: still none
    assert "Quality by area" not in headings(render_digest(repo))
    _land(repo, "api-contract-outline")   # completed before tallies existed
    assert _quality(render_digest(repo)) == ["| `shared` | 1 | 1 | — | — | 0 | 0 |"]


def test_a_leaf_whose_branch_nets_no_change_under_the_project_still_counts(repo: Path) -> None:
    """Claim, approve and deregister can leave the project tree as it was, so the merge is TREESAME to the
    integration parent; its gate and completion commits must still be found."""
    git(repo, "checkout", "-q", "-b", "feature/rm-roadmap-ci")
    registry = repo / "roadmap" / "registry.yaml"
    before = registry.read_text(encoding="utf-8")
    _gate_commit(repo, "roadmap-ci", _tally("M0.2", 2, 1))
    registry.write_text(before, encoding="utf-8")
    commit(repo, "chore(rm-roadmap-ci): complete, deregister")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'feature/rm-roadmap-ci' into main",
        "feature/rm-roadmap-ci")
    assert _quality(render_digest(repo)) == [
        "| `roadmap` **flagged** | 1 | 0 | 2.00 | 100% | 0 | 0 |",
        "| `schemas` **flagged** | 1 | 0 | 2.00 | 100% | 0 | 0 |",
    ]
