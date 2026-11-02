"""Fixture repos with authored and unauthored leaves, and drivers for pickup and ``grind-session --plan``.

Shared by ``test_unauthored_leaf_guard`` and ``test_one_readiness_rule``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.helpers import SCHEMAS

from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.grind_session import run_session
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.planning_artifacts import expected_planning_rel
from specy_road.bundled_scripts.planning_sheet_bootstrap import render_feature_sheet_template

FILLED = (
    "## Intent\n\nThe export writes one row per node.\n\n"
    "## Approach\n\nExtend the writer; a golden file test proves it.\n\n"
    "## Tasks / checklist\n\n- [ ] …\n\n## References\n\n- Roadmap chunk for `{nid}`\n"
)


def leaf_node(nid: str, order: int, **over) -> dict:
    n = {
        "id": nid,
        "node_key": str(uuid.uuid5(uuid.NAMESPACE_URL, nid)),
        "codename": f"leaf-{order}",
        "title": f"Leaf {order}",
        "type": "task",
        "parent_id": None,
        "sibling_order": order,
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": ["src"],
    }
    n.update(over)
    n["planning_dir"] = expected_planning_rel(n)
    return n


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def unauthored_repo(tmp_path: Path, sheets: dict[str, str], **over: dict) -> tuple[Path, list[dict]]:
    """One task leaf per ``sheets`` entry (id -> sheet text, or ``"scaffold"``)."""
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    shutil.copytree(SCHEMAS, root / "schemas")
    nodes = [leaf_node(nid, i, **over.get(nid, {})) for i, nid in enumerate(sheets, 1)]
    for n in nodes:
        text = sheets[n["id"]]
        sheet = root / n["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(
            render_feature_sheet_template(n["id"]) if text == "scaffold" else text.format(nid=n["id"]),
            encoding="utf-8",
        )
    rm = root / "roadmap"
    (rm / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M1.json"]}))
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": nodes}))
    (rm / "registry.yaml").write_text("version: 1\nentries: []\n")
    (rm / "git-workflow.yaml").write_text("version: 1\nintegration_branch: main\nremote: origin\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph")
    return root, nodes


class Picked(Exception):
    pass


def pick_leaf(monkeypatch: pytest.MonkeyPatch, root: Path, *argv: str) -> str:
    """Run pickup up to the point it announces its choice; return that node id."""
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "merge")

    def stop(node, _branch, _root):
        raise Picked(node["id"])

    monkeypatch.setattr(dnt, "print_pickup_header", stop)
    with pytest.raises(Picked) as picked:
        dnt.main(["--repo-root", str(root), *argv])
    return picked.value.args[0]


def plan_json(root: Path, *argv: str) -> None:
    """Run ``grind-session --plan --json``; the plan is the first stdout line."""
    run_session(parse_grind_session_args(["--plan", "--json", "--repo-root", str(root), *argv]))

