"""validate refuses cycles made through inherited and group dependencies."""

from __future__ import annotations

import pytest

from specy_road.bundled_scripts import validate_roadmap as vr
from specy_road.bundled_scripts.validate_roadmap_checks import effective_cycle_check

_KP, _KP1, _KP2, _KQ = (f"{i}0000000-0000-4000-8000-00000000000{i}" for i in range(1, 5))


def _group_nodes(deps: dict[str, list[str]]) -> list[dict]:
    """Phase M1 (leaves M1.1, M1.2) and leaf M2, with ``deps`` by display id."""
    shape = [("M1", _KP, None), ("M1.1", _KP1, "M1"), ("M1.2", _KP2, "M1"), ("M2", _KQ, None)]
    return [
        {"id": nid, "node_key": nk, "parent_id": pid, "dependencies": deps.get(nid, [])}
        for nid, nk, pid in shape
    ]


@pytest.mark.parametrize(
    "deps, message",
    [
        (   # M2 -> M1.1 explicitly; M1.1 inherits M1's dependency on M2.
            {"M1": [_KQ], "M2": [_KP1]},
            "roadmap: dependency cycle: M1.1 -> M2 -> M1.1\n"
            "  M1.1 -> M2: inherited from M1, which depends on M2\n",
        ),
        (   # M2 waits on group M1, which completes only when M1.1 (waiting on M2) does.
            {"M2": [_KP], "M1.1": [_KQ]},
            "roadmap: dependency cycle: M1 -> M1.1 -> M2 -> M1\n"
            "  M1 -> M1.1: parent-child rollup: M1 completes when its child M1.1 does\n",
        ),
        (   # M1.1 would wait on itself through M1's dependency.
            {"M1": [_KP1]},
            "roadmap: inherited self-edge M1.1 via M1\n",
        ),
    ],
)
def test_validate_refuses_cycles_through_inherited_dependencies(
    deps: dict[str, list[str]], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = _group_nodes(deps)
    vr.cycle_check(nodes)   # explicit edges alone are acyclic
    with pytest.raises(SystemExit):
        effective_cycle_check(nodes)
    assert capsys.readouterr().err == message


def test_effective_cycle_check_accepts_group_dependency_without_cycle() -> None:
    effective_cycle_check(_group_nodes({"M1": [_KQ], "M1.2": [_KP1], "M2": []}))
