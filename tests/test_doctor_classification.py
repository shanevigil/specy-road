"""``doctor_worktrees.CLASSIFICATION``: one row per verdict, each with a concrete input (M14.2 A3).

The expected (label, fix) pairs are written out here, not read back from the table, so a
changed row fails until this list is changed with it.
"""

from __future__ import annotations

import itertools

import pytest

from specy_road.doctor_worktrees import CLASSIFICATION, CONTAINMENT, EVIDENCE, LIVE_SOURCES, REF_KINDS, classify

ROWS = [   # (row index, an input it matches first, expected verdict)
    (0, ("claim", "commit", "yes", "local"), ("live", False)),
    (1, ("worker", "finish-merge", "yes", "remote"), ("live", False)),
    (2, ("session", "none", "same-patch", "local"), ("live", False)),
    (3, ("none", "creation-only", "no", "remote"), ("no commits yet", False)),
    (4, ("none", "copy-only", "yes", "local"), ("no commits yet", False)),
    (5, ("none", "rename-only", "yes", "local"), ("no commits yet", False)),
    (6, ("none", "commit", "yes", "local"), ("merged", True)),
    (7, ("none", "finish-merge", "yes", "remote"), ("merged", True)),
    (8, ("none", "finish-merge", "yes", "local"), ("merged", True)),
    (9, ("none", "none", "yes", "remote"), ("merged, no evidence", False)),
    (10, ("none", "none", "same-patch", "local"), ("same patch", True)),
    (11, ("none", "commit", "no", "local"), ("not merged", True)),
]


@pytest.mark.parametrize("index, key, expected", ROWS, ids=[f"row{r[0]}" for r in ROWS])
def test_each_classification_row(index: int, key: tuple[str, str, str, str], expected: tuple[str, bool]) -> None:
    pattern, verdict = CLASSIFICATION[index]
    assert all(want in ("*", got) for want, got in zip(pattern, key))
    assert verdict == expected
    assert classify(*key) == expected


def test_the_rows_are_all_tested_and_cover_every_input() -> None:
    assert len(ROWS) == len(CLASSIFICATION)
    for key in itertools.product(LIVE_SOURCES, EVIDENCE, CONTAINMENT, REF_KINDS):
        label, fix = classify(*key)
        if key[0] != "none":
            assert (label, fix) == ("live", False)   # liveness first, whatever else holds
        if key[1] in ("creation-only", "copy-only", "rename-only") and key[0] == "none":
            assert (label, fix) == ("no commits yet", False)   # never merged
        if fix:
            assert key[0] == "none" and key[1] not in ("creation-only", "copy-only", "rename-only")
            assert key[2] != "yes" or key[1] in ("commit", "finish-merge")   # contained: positive evidence only
