"""Prose id references after a move: `rename-refs` and the opt-in `--rewrite-refs` (M21.3).

A move rewrote ids in chunks, sheet names, claims and touch zones but never in
prose, so planning sheets and acceptance text kept citing old ids that now name
other nodes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specy_road.bundled_scripts.planning_rename import rewrite_id_refs
from specy_road.bundled_scripts.roadmap_chunk_utils import (
    load_json_chunk,
    write_json_chunk,
)
from specy_road.bundled_scripts.roadmap_move_node import move_node
from tests.move_node_helpers import (
    NK_A3,
    NK_B,
    NK_B4,
    nodes_by_key,
    run_cli,
    tree_bytes,
    wide_fixture,
)

FENCED = "```\nsee M1.3\n```\n"
HISTORICAL = "<!-- historical -->was M1.3<!-- /historical -->\n"
ACCEPTANCE = "Builds on M1.3 and M1.2.4, not M1.30"


def _sheet(renamed: dict[str, str]) -> str:
    """M2's sheet citing M1.3 and M1.2.4, after ``renamed``; fenced and historical text stays."""
    a, b = (renamed.get(i, i) for i in ("M1.3", "M1.2.4"))
    return f"# M2\n\nFollows {a} (planning/{a}_last-work) and {b}.\n" + FENCED + HISTORICAL


SHEET = _sheet({})


@pytest.mark.parametrize(
    ("text", "id_map", "expected", "count"),
    [
        ("M16.1 and M16.10", {"M16.1": "M9.1"}, "M9.1 and M16.10", 1),
        ("M16.1.2 or v2.M16.1", {"M16.1": "M9.1"}, "M16.1.2 or v2.M16.1", 0),
        ("xM16.1 _M16.1 5M16.1", {"M16.1": "M9.1"}, "xM16.1 _M16.1 5M16.1", 0),
        ("(M16.1) M16.1. M16.1_codename", {"M16.1": "M9"}, "(M9) M9. M9_codename", 3),
        ("M1 then M2", {"M1": "M2", "M2": "M1"}, "M2 then M1", 2),
        ("M1.3, M1.2", {"M1.3": "M1.2", "M1.2": "M1.1"}, "M1.2, M1.1", 2),
        ("a\n" + FENCED + "M1.3\n", {"M1.3": "M2"}, "a\n" + FENCED + "M2\n", 1),
        ("  ````py\nM1.3\n  ````\n", {"M1.3": "M2"}, "  ````py\nM1.3\n  ````\n", 0),
        (HISTORICAL + "M1.3", {"M1.3": "M2"}, HISTORICAL + "M2", 1),
    ],
    ids=[
        "no-longer-id",
        "no-child-or-dotted-prefix",
        "no-id-char-before",
        "punctuation-and-codename",
        "swap",
        "chain",
        "fenced",
        "indented-long-fence",
        "historical",
    ],
)
def test_rewrite_matches_whole_ids_only(
    text: str, id_map: dict[str, str], expected: str, count: int
) -> None:
    assert rewrite_id_refs(text, id_map) == (expected, count)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """The wide graph, with M2's sheet and M2.4's acceptance citing M1.3."""
    wide_fixture(tmp_path)
    chunk = tmp_path / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n["node_key"] == NK_B4:
            n["acceptance"] = [ACCEPTANCE]
    write_json_chunk(chunk, nodes)
    (tmp_path / nodes_by_key(tmp_path)[NK_B]["planning_dir"]).write_text(
        SHEET, encoding="utf-8"
    )
    return tmp_path


def _prose(root: Path) -> tuple[str, list[str]]:
    by_key = nodes_by_key(root)
    sheet = (root / by_key[NK_B]["planning_dir"]).read_text(encoding="utf-8")
    return sheet, by_key[NK_B4]["acceptance"]


def test_rename_refs_rewrites_sheets_and_acceptance_and_prints_counts(
    repo: Path,
) -> None:
    id_map = repo / "map.json"
    id_map.write_text(json.dumps({"M1.3": "M1.2.4", "M1.2.4": "M1.3"}), encoding="utf-8")

    r = run_cli(repo, "rename-refs", str(id_map))

    assert r.returncode == 0, r.stderr
    assert _prose(repo) == (
        _sheet({"M1.3": "M1.2.4", "M1.2.4": "M1.3"}),
        ["Builds on M1.2.4 and M1.3, not M1.30"],
    )
    assert "M2.4 title/acceptance: 2" in r.stdout
    assert f"planning/M2_unnamed_{NK_B}.md: 3" in r.stdout


def test_rename_refs_dry_run_writes_nothing(repo: Path) -> None:
    id_map = repo / "map.json"
    id_map.write_text(json.dumps({"M1.3": "M9"}), encoding="utf-8")
    before = tree_bytes(repo)

    r = run_cli(repo, "rename-refs", str(id_map), "--dry-run")

    assert r.returncode == 0, r.stderr
    assert "M2.4 title/acceptance: 1" in r.stdout
    assert tree_bytes(repo) == before


@pytest.mark.parametrize(
    ("args", "old", "new"),
    [
        (("move-node", "M1.3", "--to-parent", "M2"), "M1.3", "M2.5"),
        (("indent", "M1.3"), "M1.3", "M1.2.5"),
        (("outdent", "M1.2.4"), "M1.2.4", "M1.4"),
        (("group-nodes", "M1.3", "--into-new", "M1.4", "--title", "G"), "M1.3", "M1.4.1"),
    ],
    ids=["move-node", "indent", "outdent", "group-nodes"],
)
@pytest.mark.parametrize("rewrite", [True, False], ids=["rewrite-refs", "default"])
def test_moves_rewrite_prose_only_with_the_flag(
    repo: Path, args: tuple[str, ...], old: str, new: str, rewrite: bool
) -> None:
    r = run_cli(repo, *args, *(("--rewrite-refs",) if rewrite else ()))

    assert r.returncode == 0, r.stderr
    if rewrite:
        expected = (_sheet({old: new}), [ACCEPTANCE.replace(old, new, 1)])
    else:
        expected = (_sheet({}), [ACCEPTANCE])
    assert _prose(repo) == expected


def test_a_failed_move_rewrites_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = tree_bytes(repo)

    def boom(_root: Path) -> None:
        raise ValueError("roadmap: synthetic validation failure")

    monkeypatch.setattr(
        "specy_road.bundled_scripts.roadmap_move_node.run_validate_raise", boom
    )
    with pytest.raises(ValueError, match="synthetic"):
        move_node(repo, NK_A3, "M2", None, rewrite_refs=True)

    assert tree_bytes(repo) == before


@pytest.fixture()
def client(repo: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


@pytest.mark.parametrize(
    ("url", "body"),
    [
        ("/api/outline/move", {"node_key": NK_A3, "new_parent_id": "M2", "new_index": 0}),
        ("/api/nodes/M1.3/indent", {}),
        ("/api/nodes/M1.2.4/outdent", {}),
        ("/api/outline/group", {"into_new": "M1.4", "title": "G", "node_ids": ["M1.3"]}),
    ],
    ids=["move", "indent", "outdent", "group"],
)
@pytest.mark.parametrize("rewrite", [True, False, None], ids=["true", "false", "omitted"])
def test_gui_rewrite_refs_is_opt_in(
    client: TestClient, repo: Path, url: str, body: dict, rewrite: bool | None
) -> None:
    if rewrite is not None:
        body = {**body, "rewrite_refs": rewrite}
    fp = client.get("/api/roadmap").json()["fingerprint"]

    r = client.post(url, json=body, headers={"X-PM-Gui-Fingerprint": str(fp)})

    assert r.status_code == 200, r.text
    unchanged = _prose(repo) == (SHEET, [ACCEPTANCE])
    assert unchanged is (not rewrite)
