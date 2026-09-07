"""CLI surface for findings 34, 36, 37 and 38.

`why-blocked` / `list-gates` exit codes, `list-nodes --status`, and the
did-you-mean redirect for an unrecognised command.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOGFOOD = REPO / "tests" / "fixtures" / "specy_road_dogfood"


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args],
        cwd=REPO, capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# Finding 34 — did you mean
# ---------------------------------------------------------------------------


def test_grind_points_at_grind_session():
    """The motivating case: every new agent types this first."""
    r = _cli("grind", "--help")

    assert r.returncode == 2
    assert "unknown command: grind" in r.stderr
    assert "grind-session" in r.stderr


def test_a_misspelling_is_matched_by_similarity():
    r = _cli("validte")

    assert r.returncode == 2
    assert "validate" in r.stderr


def test_nonsense_still_points_at_the_help():
    r = _cli("zzzzzzzz")

    assert r.returncode == 2
    assert "specy-road --help" in r.stderr


def test_a_prefix_beats_difflib():
    """`list` prefixes several real commands; difflib alone scores none of them."""
    r = _cli("list")

    assert r.returncode == 2
    assert "list-nodes" in r.stderr or "list-gates" in r.stderr


# ---------------------------------------------------------------------------
# Finding 38 — list-nodes --status
# ---------------------------------------------------------------------------


def test_list_nodes_filters_on_status():
    r = _cli("list-nodes", "--repo-root", str(DOGFOOD), "--status", "Complete")

    assert r.returncode == 0
    rows = [ln for ln in r.stdout.splitlines()[1:] if ln.strip()]
    assert rows, "expected at least one Complete node in the dogfood fixture"
    assert all("Complete" in ln for ln in rows)


def test_list_nodes_status_is_repeatable():
    one = _cli("list-nodes", "--repo-root", str(DOGFOOD), "--status", "Complete")
    two = _cli(
        "list-nodes", "--repo-root", str(DOGFOOD),
        "--status", "Complete", "--status", "Not Started",
    )

    assert len(two.stdout.splitlines()) > len(one.stdout.splitlines())


def test_list_nodes_rejects_a_status_outside_the_vocabulary():
    r = _cli("list-nodes", "--repo-root", str(DOGFOOD), "--status", "Doing")

    assert r.returncode != 0


def test_list_nodes_without_status_is_unchanged():
    r = _cli("list-nodes", "--repo-root", str(DOGFOOD))

    assert r.returncode == 0
    assert "ROLLUP" in r.stdout


# ---------------------------------------------------------------------------
# Findings 36 and 37 — why-blocked / list-gates
# ---------------------------------------------------------------------------


def test_why_blocked_exits_zero_for_a_pickable_leaf():
    r = _cli("why-blocked", "M0.2", "--repo-root", str(DOGFOOD))

    assert r.returncode == 0
    assert "not blocked" in r.stdout


def test_why_blocked_exits_two_for_an_unknown_id():
    r = _cli("why-blocked", "M9.9.9", "--repo-root", str(DOGFOOD))

    assert r.returncode == 2


def test_why_blocked_json_is_parseable():
    r = _cli("why-blocked", "M0.2", "--json", "--repo-root", str(DOGFOOD))

    payload = json.loads(r.stdout)
    assert payload["node_id"] == "M0.2"
    assert payload["state"] == "ready"


def test_list_gates_runs_and_reports_when_there_are_none():
    r = _cli("list-gates", "--repo-root", str(DOGFOOD))

    assert r.returncode == 0
    assert "No open gates" in r.stdout


def test_list_gates_json_is_a_list():
    r = _cli("list-gates", "--json", "--repo-root", str(DOGFOOD))

    assert json.loads(r.stdout) == []


@pytest.mark.parametrize("command", ["why-blocked", "list-gates"])
def test_help_works_for_both(command):
    r = _cli(command, "--help")

    assert r.returncode == 0
    assert command in r.stdout
