"""Tests for registry sync after display id renumbering."""

from __future__ import annotations

from pathlib import Path

import yaml

from roadmap_outline_ops import sync_registry_node_ids


def test_sync_registry_node_ids_updates_entries(tmp_path: Path) -> None:
    reg = tmp_path / "roadmap"
    reg.mkdir()
    reg_file = reg / "registry.yaml"
    reg_file.write_text(
        yaml.dump(
            {
                "entries": [
                    {"node_id": "M0.1", "codename": "foo"},
                ]
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    sync_registry_node_ids(tmp_path, {"M0.1": "M0.2"})
    data = yaml.safe_load(reg_file.read_text(encoding="utf-8"))
    assert data["entries"][0]["node_id"] == "M0.2"
