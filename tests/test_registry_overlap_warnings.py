"""Registry touch-zone overlap warnings (M11.18)."""

from __future__ import annotations

from types import SimpleNamespace

from specy_road.bundled_scripts.roadmap_crud_ops import cmd_edit
from specy_road.bundled_scripts.validate_registry_overlap import touch_zone_overlap
from tests.review_repo_helpers import make_review_repo


def _zones_clash(x: str, y: str) -> bool:
    x_base, y_base = x.rstrip("/"), y.rstrip("/")
    return x == y or x.startswith(y_base + "/") or y.startswith(x_base + "/")


def _assert_colliding_claims_appear(entries: list[dict], err: str) -> None:
    names: set[str] = set()
    for i, a in enumerate(entries):
        za = a.get("touch_zones") or []
        ac = a.get("codename") or "?"
        for b in entries[i + 1 :]:
            zb = b.get("touch_zones") or []
            bc = b.get("codename") or "?"
            if any(_zones_clash(x, y) for x in za for y in zb):
                names.add(ac)
                names.add(bc)
    for name in names:
        assert name in err, f"colliding claim {name!r} missing from overlap output"


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


def test_touch_zone_overlap_scoped_skips_the_authored_nodes_own_claim(capsys) -> None:
    entries = [
        {
            "codename": "thing",
            "node_id": "M1.1",
            "touch_zones": ["tests/"],
        },
    ]
    touch_zone_overlap(
        entries,
        scope_label="thing",
        scope_touch_zones=["tests/"],
        scope_node_id="M1.1",
    )
    assert capsys.readouterr().err == ""


def test_edit_node_cli_does_not_warn_self_overlap_on_claim(
    tmp_path, capsys
) -> None:
    repo = make_review_repo(tmp_path)
    cmd_edit(
        SimpleNamespace(
            repo_root=str(repo),
            node_id="M1.1",
            set=["touch_zones=tests/"],
            sync_codename=False,
        )
    )
    err = capsys.readouterr().err
    assert "possible overlap" not in err


def test_touch_zone_overlap_validate_summarizes_broad_shared_zone(capsys) -> None:
    entries = _registry_entries()
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "shared zone 'tests/'" in err
    assert "alpha, beta, gamma" in err
    assert err.count("tests/' vs 'tests/'") == 0
    _assert_colliding_claims_appear(entries, err)


def test_touch_zone_overlap_validate_skips_nested_clashes_under_summarized_broad(
    capsys,
) -> None:
    entries = [
        {"codename": "alpha", "touch_zones": ["tests/", "tests/a.py"]},
        {"codename": "beta", "touch_zones": ["tests/", "tests/b.py"]},
        {"codename": "gamma", "touch_zones": ["tests/", "tests/c.py"]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "shared zone 'tests/'" in err
    assert err.count("possible overlap") == 1
    _assert_colliding_claims_appear(entries, err)


def test_touch_zone_overlap_lists_nested_only_claim_in_shared_zone_summary(
    capsys,
) -> None:
    entries = [
        {"codename": "alpha", "touch_zones": ["tests/"]},
        {"codename": "beta", "touch_zones": ["tests/"]},
        {"codename": "gamma", "touch_zones": ["tests/nested/"]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "shared zone 'tests/'" in err
    assert "alpha, beta, gamma" in err
    assert err.count("possible overlap") == 1
    _assert_colliding_claims_appear(entries, err)


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
    _assert_colliding_claims_appear(entries, err)


def test_touch_zone_overlap_keeps_same_specific_file_under_shared_directory(
    capsys,
) -> None:
    entries = [
        {"codename": "a", "touch_zones": ["tests/", "tests/shared.py"]},
        {"codename": "b", "touch_zones": ["tests/", "tests/shared.py"]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "shared zone 'tests/'" in err
    assert "tests/shared.py" in err
    assert err.count("possible overlap") == 2
    _assert_colliding_claims_appear(entries, err)
