"""Shared setup for the `specy-road upgrade` tests: a scaffold as 0.2.x left it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from specy_road.init_project import run_init_project

OLD_STUB = ".cursor/commands/specyrd-validate.md"
SHIPPED_DOC = "docs/supply-chain-security.md"


def old_repo(root: Path) -> Path:
    """A scaffold as 0.2.x left it: command stubs, no AGENTS block, older schemas, no profiles."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert run_init_project(root) == 0
    (root / "AGENTS.md").write_text("# Agents\n\nOur own rules.\n", encoding="utf-8")
    shutil.rmtree(root / "model-profiles")
    (root / SHIPPED_DOC).unlink()
    (root / "schemas" / "orchestration.schema.json").unlink()
    roadmap_schema = root / "schemas" / "roadmap.schema.json"
    schema = json.loads(roadmap_schema.read_text(encoding="utf-8"))
    schema["$defs"]["node"]["properties"]["type"]["enum"] = ["vision", "phase", "milestone", "task"]
    roadmap_schema.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    (root / OLD_STUB).parent.mkdir(parents=True)
    (root / OLD_STUB).write_text("old stub\n", encoding="utf-8")
    (root / ".specyrd" / "manifest.json").write_text(json.dumps({
        "specyrd_version": "0.2.3", "role": "dev", "project_root": ".",
        "agents": {"cursor": [OLD_STUB, ".specyrd/README.md"]},
    }), encoding="utf-8")
    return root
