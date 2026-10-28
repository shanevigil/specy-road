"""Proposal §3.4 and §5 traps: sibling_order on add-node, owner on claims, --local pickup."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tests.review_repo_helpers import git, make_review_repo

from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.do_next_task_args import parse_do_next_task_args
from specy_road.bundled_scripts.do_next_task_pickup_helpers import register_and_commit
from specy_road.bundled_scripts.roadmap_crud_prepare import next_sibling_order


def _nodes(tmp_path: Path, orders: list[int | None]) -> Path:
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    nodes = [{"id": "M1", "node_key": "11111111-1111-5111-8111-111111111111", "type": "phase",
              "title": "P", "parent_id": None, "status": "Not Started"}]
    for i, o in enumerate(orders, 1):
        n = {"id": f"M1.{i}", "node_key": f"22222222-2222-5222-8222-22222222222{i}", "type": "task",
             "title": f"T{i}", "parent_id": "M1", "status": "Not Started"}
        if o is not None:
            n["sibling_order"] = o
        nodes.append(n)
    (root / "roadmap" / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M1.json"]}))
    (root / "roadmap" / "phases" / "M1.json").write_text(json.dumps({"nodes": nodes}))
    return root


def test_new_node_goes_after_the_last_sibling(tmp_path: Path) -> None:
    root = _nodes(tmp_path, [0, 1, 2])
    assert next_sibling_order(root, "M1", None) == 3
    assert next_sibling_order(root, "M1", 1) == 1          # explicit wins
    assert next_sibling_order(root, "M9", None) == 1        # no siblings
    assert next_sibling_order(_nodes(tmp_path / "b", [None, None]), "M1", None) == 3  # unordered siblings


def test_add_node_cli_writes_sibling_order(tmp_path: Path) -> None:
    from specy_road.bundled_scripts.roadmap_crud import main as crud_main
    import pytest

    repo = make_review_repo(tmp_path)  # M1.1 at sibling_order 1, parent None
    try:
        crud_main(["--repo-root", str(repo), "add-node", "--id", "M1.2", "--type", "task",
                   "--title", "Second", "--parent-id", "null"])
    except SystemExit as e:  # the CRUD main returns normally on success
        assert (e.code or 0) == 0
    chunk = json.loads((repo / "roadmap" / "phases" / "M1.json").read_text())
    by_id = {n["id"]: n for n in chunk["nodes"]}
    assert by_id["M1.2"]["sibling_order"] == 2


def test_claim_row_carries_owner(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    calls: list[tuple] = []
    reg = {"version": 1, "entries": []}
    node = {"id": "M1.2", "codename": "two", "touch_zones": ["src"]}
    register_and_commit(registry_path=repo / "roadmap" / "registry.yaml", git_runner=lambda *a: calls.append(a),
                        node=node, branch="feature/rm-two", reg=reg, commit_message="m",
                        impl_review_gate=False, owner="Shane V")
    row = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())["entries"][-1]
    assert row["owner"] == "Shane V" and row["touch_zones"] == ["src"]
    register_and_commit(registry_path=repo / "roadmap" / "registry.yaml", git_runner=lambda *a: calls.append(a),
                        node={"id": "M1.3", "codename": "three"}, branch="feature/rm-three", reg=reg,
                        commit_message="m", impl_review_gate=False, owner=None)
    assert "owner" not in yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())["entries"][-1]


def test_pickup_args_local_and_owner() -> None:
    ns = parse_do_next_task_args(["--local", "--owner", "me"])
    assert ns.local and ns.owner == "me"
    ns = parse_do_next_task_args([])
    assert not ns.local and ns.owner is None


def test_local_pickup_skips_sync_and_push(tmp_path: Path, monkeypatch) -> None:
    """--local: no fetch/merge, no push; the claim is still committed locally."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    # The helper models a claimed, In Progress leaf; pickup skips those by
    # design (an in-progress leaf should already have a claim). Free it.
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    chunk.write_text(chunk.read_text().replace('"status": "In Progress"', '"status": "Not Started"'))
    git(repo, "commit", "-qam", "free the claim")
    monkeypatch.setattr(dnt, "ROOT", repo)
    synced: list[str] = []
    pushed: list[tuple] = []
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *a, **k: synced.append("sync"))
    monkeypatch.setattr(dnt, "_push_integration_branch", lambda remote, base: pushed.append((remote, base)),
                        raising=False)
    monkeypatch.setattr(dnt, "git_config_user_name", lambda _r: "Shane V")
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _r, oc: "merge")
    import pytest
    try:
        dnt.main(["--local", "--on-complete", "merge", "--repo-root", str(repo)])
    except SystemExit as e:
        assert (e.code or 0) == 0
    assert synced == []
    assert pushed == []
    row = yaml.safe_load(git(repo, "show", "dev:roadmap/registry.yaml"))["entries"][0]
    assert row["node_id"] == "M1.1" and row["owner"] == "Shane V"
    assert git(repo, "branch", "--show-current") == "feature/rm-thing"
