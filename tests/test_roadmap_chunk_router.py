"""Tests for the automatic roadmap chunk router."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

# Bundled scripts live outside ``specy_road`` for flat imports — mirror the
# helper in tests/helpers.py so router/atomic modules are importable.
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS  # noqa: E402

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))

from roadmap_chunk_atomic import AtomicWritePlan
from roadmap_chunk_router import (
    relocate_node_if_overflow,
    write_with_routing,
)
from roadmap_chunk_router_pick import (
    chunk_max_lines,
    derive_new_chunk_path,
    insert_include_in_manifest,
    pick_target_chunk,
    simulate_chunk_lines,
)
from roadmap_chunk_utils import (
    load_json_chunk,
    load_manifest_mapping,
    render_json_chunk,
    write_json_chunk,
)


# Use distinct UUID-shaped prefixes so the 6-hex tail of node_key derived
# filenames differs across nodes (the router takes the first 6 hex chars).
_NK = "{tail:08d}-0000-4000-8000-000000000001"


def _node(
    nid: str,
    parent: str | None,
    *,
    type_: str = "task",
    title: str = "T",
    codename: str | None = None,
    n_index: int = 1,
    deps: list[str] | None = None,
) -> dict:
    nk = _NK.format(tail=n_index)
    cn = codename
    if cn is None and type_ == "task":
        cn = f"{title.lower().replace(' ', '-')}-{n_index:03d}"
    pd = (
        f"planning/{nid}_{cn or 'unnamed'}_{nk}.md"
        if type_ in ("phase", "milestone", "task", "vision", "gate")
        else None
    )
    out: dict = {
        "id": nid,
        "node_key": nk,
        "parent_id": parent,
        "type": type_,
        "title": title,
        "codename": cn,
        "planning_dir": pd,
        "execution_milestone": "Agentic-led" if type_ != "phase" else "Human-led",
        "status": "Not Started",
        "touch_zones": [],
        "dependencies": list(deps or []),
        "parallel_tracks": 1,
    }
    return {k: v for k, v in out.items() if v is not None}


def _write_planning(root: Path, node: dict) -> None:
    pd = node.get("planning_dir")
    if not isinstance(pd, str):
        return
    p = root / pd
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {node['id']}\n", encoding="utf-8")


def _seed_repo(root: Path, chunks: dict[str, list[dict]]) -> None:
    """Build a minimal-but-complete repo: schemas, constraints, planning, manifest, chunks."""
    shutil.copytree(SCHEMAS, root / "schemas")
    shutil.copytree(REPO / "constraints", root / "constraints")
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (root / "roadmap" / "phases").mkdir(parents=True)
    (root / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n", encoding="utf-8"
    )
    includes = list(chunks.keys())
    (root / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": includes}) + "\n",
        encoding="utf-8",
    )
    pl = root / "planning"
    pl.mkdir(parents=True)
    for rel, nodes in chunks.items():
        write_json_chunk(root / "roadmap" / rel, nodes)
        for n in nodes:
            _write_planning(root, n)


def _phase_M0(parent: str | None = None) -> dict:
    return _node("M0", None, type_="phase", title="phase0", codename=None, n_index=1)


def _milestone(nid: str, parent: str, *, n_index: int) -> dict:
    return _node(nid, parent, type_="milestone", title=f"m{n_index}", n_index=n_index)


def _task(nid: str, parent: str, *, n_index: int) -> dict:
    return _node(nid, parent, type_="task", title=f"t{n_index}", n_index=n_index)


@pytest.fixture()
def small_repo(tmp_path: Path) -> Path:
    """Single-phase repo with three nodes living in one chunk."""
    chunks = {
        "phases/M0.json": [
            _phase_M0(),
            _milestone("M0.1", "M0", n_index=2),
            _task("M0.1.1", "M0.1", n_index=3),
        ],
    }
    _seed_repo(tmp_path, chunks)
    return tmp_path


def test_simulate_chunk_lines_matches_disk_render(small_repo: Path) -> None:
    """The router's prediction must equal what write_json_chunk would produce."""
    chunk = small_repo / "roadmap" / "phases" / "M0.json"
    nodes = load_json_chunk(chunk)
    on_disk = chunk.read_text(encoding="utf-8")
    rendered = render_json_chunk(nodes)
    assert rendered == on_disk
    expected = on_disk.count("\n") + (0 if on_disk.endswith("\n") else 1)
    assert simulate_chunk_lines(nodes) == expected


def test_pick_target_chunk_uses_hint_when_room(small_repo: Path) -> None:
    new = _task("M0.1.2", "M0.1", n_index=4)
    decision = pick_target_chunk(small_repo, "M0.1", "phases/M0.json", new)
    assert decision.chunk_rel == "phases/M0.json"
    assert decision.is_new_chunk is False
    assert any(n["id"] == "M0.1.2" for n in decision.nodes_after)


def _seed_with_cap(tmp_path: Path, cap_lines: int, fat_count: int) -> None:
    """Seed a fixture where ``phases/M0.json`` is *just below* ``cap_lines``."""
    fat = [_phase_M0()] + [
        _milestone(f"M0.{i}", "M0", n_index=10 + i) for i in range(1, fat_count + 1)
    ]
    _seed_repo(tmp_path, {"phases/M0.json": fat})
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        f"roadmap_json_chunk_max_lines: {cap_lines}\n", encoding="utf-8"
    )


def test_pick_target_chunk_falls_back_when_hint_full(tmp_path: Path) -> None:
    """Hint chunk full → router picks a same-phase chunk that fits."""
    # 15 milestones ≈ 227 lines; cap = 235 → adding one more pushes over.
    # Sibling chunk has 1 node, plenty of room.
    fat = [_phase_M0()] + [_milestone(f"M0.{i}", "M0", n_index=10 + i) for i in range(1, 16)]
    sibling = [_milestone("M0.40", "M0", n_index=40)]
    _seed_repo(tmp_path, {"phases/M0.json": fat, "phases/M0__sib.json": sibling})
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 215\n", encoding="utf-8"
    )
    src_lines = simulate_chunk_lines(load_json_chunk(tmp_path / "roadmap" / "phases" / "M0.json"))
    assert src_lines <= 235
    new = _task("M0.40.1", "M0.40", n_index=41)
    decision = pick_target_chunk(tmp_path, "M0.40", "phases/M0.json", new)
    assert decision.chunk_rel == "phases/M0__sib.json"
    assert decision.is_new_chunk is False


def test_pick_target_chunk_creates_new_chunk_when_none_fit(tmp_path: Path) -> None:
    fat = [_phase_M0()] + [_milestone(f"M0.{i}", "M0", n_index=10 + i) for i in range(1, 16)]
    _seed_repo(tmp_path, {"phases/M0.json": fat})
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 215\n", encoding="utf-8"
    )
    new = _task("M0.99", "M0", n_index=99)
    decision = pick_target_chunk(tmp_path, "M0", "phases/M0.json", new)
    assert decision.is_new_chunk is True
    assert decision.chunk_rel.startswith("phases/M0__")
    assert decision.chunk_rel.endswith(".json")
    assert decision.nodes_after == [new]


def test_derive_new_chunk_path_is_deterministic_per_node_key(tmp_path: Path) -> None:
    chunks = {"phases/M0.json": [_phase_M0()]}
    _seed_repo(tmp_path, chunks)
    new = _task("M0.99", "M0", n_index=99)
    a = derive_new_chunk_path(tmp_path, "phases/M0.json", new)
    b = derive_new_chunk_path(tmp_path, "phases/M0.json", new)
    assert a == b
    other = _task("M0.100", "M0", n_index=100)
    c = derive_new_chunk_path(tmp_path, "phases/M0.json", other)
    assert c != a, "different node_keys must derive different filenames"


def test_write_with_routing_creates_chunk_and_updates_manifest(tmp_path: Path) -> None:
    fat = [_phase_M0()] + [_milestone(f"M0.{i}", "M0", n_index=10 + i) for i in range(1, 16)]
    _seed_repo(tmp_path, {"phases/M0.json": fat})
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 215\n", encoding="utf-8"
    )
    new = _task("M0.99", "M0", n_index=99)
    _write_planning(tmp_path, new)
    chunk = write_with_routing(tmp_path, "M0", "phases/M0.json", new)
    assert chunk.is_file()
    assert chunk.parent.name == "phases"
    doc = load_manifest_mapping(tmp_path)
    rels = doc["includes"]
    assert chunk.relative_to(tmp_path / "roadmap").as_posix() in rels


def test_write_with_routing_rolls_back_on_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation failure must restore both pre-existing chunks and unlink any net-new file."""
    _seed_repo(tmp_path, {"phases/M0.json": [_phase_M0()]})
    original_chunk = (tmp_path / "roadmap" / "phases" / "M0.json").read_bytes()
    original_manifest = (tmp_path / "roadmap" / "manifest.json").read_bytes()

    new = _task("M0.99", "M0", n_index=99)
    _write_planning(tmp_path, new)

    # Force the router into the auto-create branch by simulating overflow on
    # any chunk. Easiest: monkeypatch chunk_max_lines low.
    monkeypatch.setattr(
        "roadmap_chunk_router_pick.chunk_max_lines", lambda _root: 1
    )
    # Force validation to always fail.
    import roadmap_chunk_router as router_mod

    def boom(root):  # noqa: ANN001
        def do() -> None:
            raise ValueError("synthetic validate failure")
        return do

    monkeypatch.setattr(router_mod, "_validate_callback", boom)

    with pytest.raises(ValueError, match="synthetic"):
        write_with_routing(tmp_path, "M0", "phases/M0.json", new)

    assert (tmp_path / "roadmap" / "phases" / "M0.json").read_bytes() == original_chunk
    assert (tmp_path / "roadmap" / "manifest.json").read_bytes() == original_manifest
    # No phantom auto-created chunk left behind.
    extras = sorted(
        p.name for p in (tmp_path / "roadmap" / "phases").iterdir()
        if p.suffix == ".json" and p.name != "M0.json"
    )
    assert extras == []


def test_relocate_node_if_overflow_moves_node(tmp_path: Path) -> None:
    """When edit-node growth pushes a chunk over, the edited node moves out."""
    nodes = [_phase_M0()] + [_milestone(f"M0.{i}", "M0", n_index=10 + i) for i in range(1, 6)]
    _seed_repo(tmp_path, {"phases/M0.json": nodes})
    chunk = tmp_path / "roadmap" / "phases" / "M0.json"
    # Now bump one node's notes to be huge so the chunk is over the cap.
    on_disk = load_json_chunk(chunk)
    on_disk[-1]["notes"] = "x" * 1000
    write_json_chunk(chunk, on_disk)
    # Tighten the cap below current size so relocation triggers.
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 80\n", encoding="utf-8"
    )
    edited_id = on_disk[-1]["id"]
    new_chunk = relocate_node_if_overflow(tmp_path, edited_id, chunk)
    assert new_chunk is not None
    assert new_chunk != chunk
    # Source no longer contains the evicted node.
    src = load_json_chunk(chunk)
    assert all(n["id"] != edited_id for n in src)
    dst = load_json_chunk(new_chunk)
    assert any(n["id"] == edited_id for n in dst)


def test_atomic_plan_rollback_restores_existing_and_unlinks_new(tmp_path: Path) -> None:
    _seed_repo(tmp_path, {"phases/M0.json": [_phase_M0()]})
    chunk_existing = tmp_path / "roadmap" / "phases" / "M0.json"
    chunk_new = tmp_path / "roadmap" / "phases" / "new.json"
    original = chunk_existing.read_bytes()
    plan = AtomicWritePlan(root=tmp_path)
    plan.stage_chunk(chunk_existing, [_milestone("M0.1", "M0", n_index=2)])
    plan.stage_chunk(chunk_new, [_milestone("M0.2", "M0", n_index=3)])
    with pytest.raises(RuntimeError):
        plan.commit(_raise_runtime)
    assert chunk_existing.read_bytes() == original
    assert not chunk_new.is_file()


def _raise_runtime() -> None:
    raise RuntimeError("force rollback")


def test_insert_include_in_manifest_idempotent_and_grouped() -> None:
    doc = {"version": 1, "includes": ["phases/M0.json", "phases/M1.json"]}
    insert_include_in_manifest(doc, "phases/M0__abc123.json", "phases/M0.json")
    assert doc["includes"] == [
        "phases/M0.json",
        "phases/M0__abc123.json",
        "phases/M1.json",
    ]
    # Idempotent.
    insert_include_in_manifest(doc, "phases/M0__abc123.json", "phases/M0.json")
    assert doc["includes"].count("phases/M0__abc123.json") == 1


def test_chunk_max_lines_reads_constraint_file(tmp_path: Path) -> None:
    assert chunk_max_lines(tmp_path) == 500  # default with no constraints file
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 250\n", encoding="utf-8"
    )
    assert chunk_max_lines(tmp_path) == 250
