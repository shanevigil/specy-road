"""M3.6 triage CLI: all-or-nothing batching, realize, append-why, list --summary."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_session import read_session

SLUG = "how-do-we-expand-payments"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main(["brainstorm", *args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _start(repo: Path) -> None:
    assert _cli(repo, "start", "--topic", "How do we expand payments?")[0] == 0


def _session(repo: Path):
    return read_session(repo, SLUG)


def test_triage_checks_every_id_before_printing_or_saving(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-idea", "--title", "Two")
    code, out, err = _cli(repo, "accept", "B1", "B9")
    assert code == 1 and not out.strip() and "B9" in err
    assert _session(repo).by_id("B1").status == "proposed"
    code, out, err = _cli(repo, "park", "B1", "B9", "--reason", "later")
    assert code == 1 and not out.strip()
    assert _session(repo).by_id("B1").status == "proposed"


def test_realize_records_a_hand_built_node(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "Hand built")
    code, out, err = _cli(repo, "realize", "B1", "--node", "M1")
    assert code == 0, err
    idea = _session(repo).by_id("B1")
    assert idea.promoted_node_key
    assert "M1" in out and idea.promoted_node_key[:8] in out
    code, _, err = _cli(repo, "realize", "B1", "--node", "M1.1")
    assert code == 1 and "already on the roadmap" in err


def test_revise_append_why_adds_to_verdict_why(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "revise", "B1", "--why", "first line")
    _cli(repo, "revise", "B1", "--append-why", "second line")
    assert _session(repo).by_id("B1").verdict_why == "first line\nsecond line"


def test_list_summary_prints_status_and_recommendation_counts(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-idea", "--title", "Two")
    _cli(repo, "revise", "B1", "--recommendation", "strong")
    _cli(repo, "accept", "B1")
    _cli(repo, "reject", "B2", "--reason", "no")
    _, out, _ = _cli(repo, "list", "--summary")
    assert "status:" in out and "  proposed: 0" in out and "  accepted: 1" in out and "  rejected: 1" in out
    assert "recommendation:" in out and "  strong: 1" in out and "  -: 1" in out
