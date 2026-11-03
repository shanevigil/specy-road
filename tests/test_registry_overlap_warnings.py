"""Registry touch-zone overlap warnings (M11.18)."""

from __future__ import annotations

from specy_road.bundled_scripts.validate_registry_overlap import touch_zone_overlap

def test_touch_zone_overlap_warns_on_same_path(capsys) -> None:
    entries = [
        {"codename": "a", "touch_zones": ["src/"]},
        {"codename": "b", "touch_zones": ["src/"]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "overlap" in err.lower()


def _registry_entries() -> list[dict]:
    return [
        {"codename": "alpha", "touch_zones": ["tests/", "specy_road/a.py"]},
        {"codename": "beta", "touch_zones": ["tests/", "specy_road/b.py"]},
        {"codename": "gamma", "touch_zones": ["tests/"]},
    ]


def test_touch_zone_overlap_scoped_skips_unrelated_claim_pairs(capsys) -> None:
    touch_zone_overlap(
        _registry_entries(),
        scope_label="new-node",
        scope_touch_zones=["tests/"],
    )
    err = capsys.readouterr().err
    assert "alpha vs beta" not in err
    assert "(new-node vs alpha)" in err
    assert err.count("possible overlap") == 3


def test_touch_zone_overlap_validate_summarizes_broad_shared_zone(capsys) -> None:
    touch_zone_overlap(_registry_entries())
    err = capsys.readouterr().err
    assert "shared zone 'tests/'" in err
    assert "alpha, beta, gamma" in err
    assert err.count("tests/' vs 'tests/'") == 0


def test_touch_zone_overlap_validate_one_line_per_specific_pair(capsys) -> None:
    entries = [
        {"codename": "a", "touch_zones": ["src/foo.py", "tests/"]},
        {"codename": "b", "touch_zones": ["src/foo.py", "tests/"]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "shared zone 'tests/'" in err
    assert "src/foo.py" in err
    assert err.count("possible overlap") == 2
