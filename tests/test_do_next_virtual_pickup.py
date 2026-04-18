"""Virtual completion and dependent-first ordering for do-next pickup (on_complete: pr)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))

import do_next_available as dna  # noqa: E402
import do_next_task as dnt  # noqa: E402
from roadmap_load_at_ref import load_roadmap_nodes_at_ref  # noqa: E402

_NK_PREREQ = "11111111-1111-4111-8111-111111111111"
_NK_A = "22222222-2222-4222-8222-222222222222"
_NK_B = "33333333-3333-4333-8333-333333333333"

_CHUNK_VR2_MAIN = {
    "nodes": [
        {
            "id": "N1",
            "node_key": _NK_A,
            "codename": "a",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "dependencies": [],
            "touch_zones": ["z"],
        },
        {
            "id": "N2",
            "node_key": _NK_B,
            "codename": "b",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "dependencies": [_NK_A],
            "touch_zones": ["z"],
        },
    ]
}


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_status_overrides_unblock_dependent_leaf() -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    leaf = {
        "id": "M1.1",
        "node_key": _NK_A,
        "type": "milestone",
        "title": "Next",
        "codename": "next",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [_NK_PREREQ],
        "touch_zones": ["x"],
    }
    reg = {"version": 1, "entries": []}
    # Without the status override, M1.1 is blocked on M1.0. Post-F-007
    # the human-led dep is itself eligible (all leaves are agentic), but
    # M1.1 must still not appear until M1.0 is complete.
    before = [n["id"] for n in dnt._available([dep, leaf], reg, {})]
    assert "M1.1" not in before
    out = dnt._available(
        [dep, leaf],
        reg,
        {},
        status_overrides={_NK_PREREQ: "complete"},
    )
    assert "M1.1" in [n["id"] for n in out]


def test_virtual_complete_keys_order_dependent_before_outline_peer() -> None:
    """rest_dependent tier precedes rest_other even when outline order prefers the peer."""
    parent = {
        "id": "M0",
        "node_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "type": "phase",
        "title": "Phase",
        "parent_id": None,
        "sibling_order": 0,
        "status": "Complete",
        "dependencies": [],
    }
    prereq = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "parent_id": "M0",
        "sibling_order": 0,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    leaf_peer = {
        "id": "M7.1",
        "node_key": _NK_A,
        "parent_id": "M0",
        "sibling_order": 0,
        "type": "milestone",
        "title": "Peer first in outline",
        "codename": "peer",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": ["z"],
    }
    leaf_dep = {
        "id": "M6.2",
        "node_key": _NK_B,
        "parent_id": "M0",
        "sibling_order": 1,
        "type": "milestone",
        "title": "Dependent",
        "codename": "dep",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [_NK_PREREQ],
        "touch_zones": ["z"],
    }
    nodes = [parent, prereq, leaf_peer, leaf_dep]
    reg = {"version": 1, "entries": []}
    result = dnt._available(
        nodes,
        reg,
        {},
        status_overrides={_NK_PREREQ: "complete"},
        virtual_complete_keys={_NK_PREREQ},
    )
    result_ids = [n["id"] for n in result]
    # rest_dependent tier precedes rest_other: M6.2 (depends on virtually-
    # complete M1.0) must appear before M7.1 (the outline peer).
    assert "M6.2" in result_ids and "M7.1" in result_ids
    assert result_ids.index("M6.2") < result_ids.index("M7.1")


def test_interactive_deps_blocked_entries_excludes_ready() -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    leaf = {
        "id": "M1.1",
        "node_key": _NK_A,
        "type": "milestone",
        "codename": "next",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [_NK_PREREQ],
        "touch_zones": ["x"],
    }
    reg = {"version": 1, "entries": []}
    integration = dna._statuses_by_node_key([dep, leaf])
    ready = dnt._available([dep, leaf], reg, {}, status_overrides={_NK_PREREQ: "complete"})
    blocked = dna.interactive_deps_blocked_entries(
        [dep, leaf],
        reg,
        integration_statuses=integration,
        ready_ids={n["id"] for n in ready},
    )
    assert blocked == []


def test_interactive_deps_blocked_entries_lists_integration_blocked() -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    leaf = {
        "id": "M1.1",
        "node_key": _NK_A,
        "type": "milestone",
        "codename": "next",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [_NK_PREREQ],
        "touch_zones": ["x"],
    }
    reg = {"version": 1, "entries": []}
    integration = dna._statuses_by_node_key([dep, leaf])
    ready = dnt._available([dep, leaf], reg, {})
    ready_ids = {n["id"] for n in ready}
    # M1.1 is blocked by unmet dep M1.0 (not Complete on integration).
    assert "M1.1" not in ready_ids
    blocked = dna.interactive_deps_blocked_entries(
        [dep, leaf],
        reg,
        integration_statuses=integration,
        ready_ids=ready_ids,
    )
    assert len(blocked) == 1
    assert blocked[0][0]["id"] == "M1.1"
    assert blocked[0][1] == [_NK_PREREQ]


def test_load_roadmap_nodes_at_ref_reads_feature_tip(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@e.com")
    _run_git(repo, "config", "user.name", "T")
    roadmap = repo / "roadmap"
    roadmap.mkdir(parents=True)
    (roadmap / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/t.json"]}),
        encoding="utf-8",
    )
    chunk_main = {
        "nodes": [
            {
                "id": "N1",
                "node_key": _NK_A,
                "codename": "a",
                "execution_milestone": "Agentic-led",
                "status": "Not Started",
                "dependencies": [],
                "touch_zones": ["z"],
            }
        ]
    }
    (roadmap / "phases").mkdir(parents=True)
    (roadmap / "phases" / "t.json").write_text(
        json.dumps(chunk_main, indent=2),
        encoding="utf-8",
    )
    _run_git(repo, "add", "roadmap")
    _run_git(repo, "commit", "-m", "main")
    _run_git(repo, "branch", "-M", "main")
    _run_git(repo, "checkout", "-b", "feature/rm-a")
    chunk_feat = {
        "nodes": [
            {
                "id": "N1",
                "node_key": _NK_A,
                "codename": "a",
                "execution_milestone": "Agentic-led",
                "status": "Complete",
                "dependencies": [],
                "touch_zones": ["z"],
            }
        ]
    }
    (roadmap / "phases" / "t.json").write_text(
        json.dumps(chunk_feat, indent=2),
        encoding="utf-8",
    )
    _run_git(repo, "add", "roadmap/phases/t.json")
    _run_git(repo, "commit", "-m", "finish")
    tip = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _run_git(repo, "checkout", "main")
    _run_git(repo, "update-ref", "refs/remotes/origin/feature/rm-a", tip)

    main_nodes = load_roadmap_nodes_at_ref(repo, "main")
    assert main_nodes is not None
    assert main_nodes[0]["status"] == "Not Started"
    feat_nodes = load_roadmap_nodes_at_ref(repo, "origin/feature/rm-a")
    assert feat_nodes is not None
    assert feat_nodes[0]["status"] == "Complete"


def _repo_registry_virtual_complete_pickup(tmp_path: Path) -> tuple[Path, dict]:
    """Build git repo: integration dev, registry entry, feature tip Complete for N1."""
    import yaml

    repo = tmp_path / "vr2"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@e.com")
    _run_git(repo, "config", "user.name", "T")
    roadmap = repo / "roadmap"
    roadmap.mkdir(parents=True)
    (roadmap / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/t.json"]}),
        encoding="utf-8",
    )
    chunk_main = json.loads(json.dumps(_CHUNK_VR2_MAIN))
    (roadmap / "phases").mkdir(parents=True)
    (roadmap / "phases" / "t.json").write_text(
        json.dumps(chunk_main, indent=2),
        encoding="utf-8",
    )
    (roadmap / "registry.yaml").write_text(
        yaml.dump(
            {
                "version": 1,
                "entries": [
                    {
                        "codename": "a",
                        "node_id": "N1",
                        "branch": "feature/rm-a",
                        "touch_zones": ["z"],
                    }
                ],
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    _run_git(repo, "add", "roadmap")
    _run_git(repo, "commit", "-m", "dev")
    _run_git(repo, "branch", "-M", "dev")

    _run_git(repo, "checkout", "-b", "feature/rm-a")
    chunk_feat = json.loads(json.dumps(chunk_main))
    chunk_feat["nodes"][0]["status"] = "Complete"
    (roadmap / "phases" / "t.json").write_text(
        json.dumps(chunk_feat, indent=2),
        encoding="utf-8",
    )
    _run_git(repo, "add", "roadmap/phases/t.json")
    _run_git(repo, "commit", "-m", "done")
    tip = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _run_git(repo, "checkout", "dev")
    _run_git(repo, "update-ref", "refs/remotes/origin/feature/rm-a", tip)

    with (repo / "roadmap" / "registry.yaml").open(encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    return repo, reg


def test_virtual_complete_from_registry_and_pickup_prefers_dependent_leaf(
    tmp_path: Path,
) -> None:
    import roadmap_load as rl

    repo, reg = _repo_registry_virtual_complete_pickup(tmp_path)

    keys, logs = dnt._virtual_complete_from_registry(
        reg,
        repo_root=repo,
        remote="origin",
    )
    assert _NK_A in keys
    assert any("N1" in ln for ln in logs)

    nodes_list = rl.load_roadmap(repo)["nodes"]
    enrich = dna._load_branch_enrichment(repo)
    avail = dnt._available(
        nodes_list,
        reg,
        enrich,
        status_overrides={k: "complete" for k in keys},
        virtual_complete_keys=keys,
    )
    assert [n["id"] for n in avail] == ["N2"]
