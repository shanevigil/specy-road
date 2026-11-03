"""`why-blocked` reports the touch-zone hold `grind-session --plan` puts on a leaf.

The plan held a leaf behind another for sharing a touch zone while
`why-blocked` on the same leaf said it was not blocked (M11.65).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road.bundled_scripts import roadmap_query_cli as rq
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.bundled_scripts.session_plan_render import zone_overlaps
from tests.review_repo_helpers import git
from tests.test_orchestrate_plan import plan_repo
from tests.test_session_plan_touch_zones import _leaf

# plan_repo's M1.1 is ready with touch zone `src`.
M1_1_KEY = "11111111-1111-5111-8111-111111111111"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """M1.2 shares `src` with M1.1 (zone hold), M1.3 depends on M1.1, M1.4 is free."""
    repo = plan_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text())
    data["nodes"] += [
        {**_leaf(2, ["src/a.py"]), "codename": "held"},
        {**_leaf(3, ["lib/c.py"]), "codename": "after", "dependencies": [M1_1_KEY]},
        {**_leaf(4, ["docs/d.md"]), "codename": "free"},
    ]
    chunk.write_text(json.dumps(data))
    git(repo, "commit", "-qam", "held, dependent and free leaves")
    return repo


def _why(repo: Path, node_id: str, *extra: str, capsys) -> tuple[int, str]:
    with pytest.raises(SystemExit) as exc:
        rq.main(["why-blocked", node_id, "--repo-root", str(repo), *extra])
    return exc.value.code, capsys.readouterr().out


def test_zone_hold_names_the_holder_and_zones_and_says_pickup_ignores_it(repo, capsys):
    _nodes, _reg, plan = gather_session_plan(repo, None)
    assert plan.parallel_batches == [["M1.1", "M1.4"], ["M1.2"]]  # the plan does hold it

    code, out = _why(repo, "M1.2", capsys=capsys)

    assert code == 0  # pickup would still claim it
    assert "M1.2 is not blocked" in out
    assert "grind-session --plan holds M1.2 for a later parallel batch, behind M1.1" in out
    assert "touch zone `src/a.py` overlaps `src`" in out
    assert "Pickup does not honour this hold" in out


def test_zone_hold_in_json(repo, capsys):
    code, out = _why(repo, "M1.2", "--json", capsys=capsys)

    payload = json.loads(out)
    assert code == 0
    assert payload["state"] == "ready"
    assert payload["plan_hold"] == {
        "waits_for": "M1.1", "zones": ["src/a.py", "src"], "pickup_honours": False,
    }
    # Exactly what --plan's "Held for the next batch" section reads.
    _nodes, _reg, plan = gather_session_plan(repo, None)
    assert zone_overlaps(plan) == [
        {"node_id": "M1.2", "waits_for": "M1.1", "zones": ["src/a.py", "src"]},
    ]


def test_dependency_block_reports_the_chain_and_no_hold(repo, capsys):
    code, out = _why(repo, "M1.3", capsys=capsys)

    assert code == rq.EXIT_BLOCKED
    assert "waiting on:" in out and "M1.1" in out
    assert "holds" not in out

    _code, out = _why(repo, "M1.3", "--json", capsys=capsys)
    assert json.loads(out)["plan_hold"] is None


def test_free_leaf_has_no_hold(repo, capsys):
    code, out = _why(repo, "M1.4", capsys=capsys)

    assert code == 0
    assert "M1.4 is not blocked" in out
    assert "holds" not in out and "Pickup" not in out

    _code, out = _why(repo, "M1.4", "--json", capsys=capsys)
    assert json.loads(out)["plan_hold"] is None


def test_the_holder_itself_is_not_held(repo, capsys):
    _code, out = _why(repo, "M1.1", "--json", capsys=capsys)

    assert json.loads(out)["plan_hold"] is None
