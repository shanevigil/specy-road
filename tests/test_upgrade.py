"""`specy-road upgrade`: the four upgrade commands in order, one invocation.

rc1 adopters ran refresh-schemas / refresh-stubs / validate from memory and
each stopped somewhere different: duplicate /specyrd-… commands left behind,
no AGENTS.md block, model-profiles/ never added. The contract tested here is
that one run on a 0.2.x-shaped repo clears every upgrade warning `validate`
knows about, and touches nothing outside the refreshers' own paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from specy_road.bundled_scripts.upgrade import copy_missing_docs, run_upgrade
from specy_road.init_project import run_init_project

OLD_STUB = ".cursor/commands/specyrd-validate.md"
SHIPPED_DOC = "docs/supply-chain-security.md"


def _old_repo(root: Path) -> Path:
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


def test_one_run_clears_every_upgrade_warning(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)
    roadmap_before = (root / "roadmap" / "manifest.json").read_text(encoding="utf-8")

    assert run_upgrade(root, prune=True) == 0

    out, err = capsys.readouterr()
    assert "wrote schemas/orchestration.schema.json (new in this version)" in out
    assert "removed .cursor/commands/specyrd-validate.md" in out
    assert f"wrote {SHIPPED_DOC} (named in the AGENTS.md load order)" in out
    assert (root / SHIPPED_DOC).is_file()
    assert "OK: roadmap and registry validate." in out
    for warning in ("agents: warning", "schemas: warning", "specyrd: warning"):
        assert warning not in err
    assert not (root / ".cursor" / "commands").exists()
    assert (root / ".agents" / "skills" / "specyrd-validate" / "SKILL.md").is_file()
    assert any((root / "model-profiles").rglob("*.md"))
    assert "Our own rules." in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert (root / "roadmap" / "manifest.json").read_text(encoding="utf-8") == roadmap_before


def test_a_missing_digest_is_a_next_step_not_a_failure(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)

    assert run_upgrade(root) == 0

    out = capsys.readouterr().out
    assert "Run specy-road digest" in out and "Not specy-road sync" in out


def test_dry_run_writes_nothing_and_skips_validate(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)

    assert run_upgrade(root, dry_run=True, prune=True) == 0

    out = capsys.readouterr().out
    assert "would remove .cursor/commands/specyrd-validate.md" in out
    assert "migration: 1 command stubs (*/commands/) become 1 skills under .agents/skills/" in out
    assert f"would write {SHIPPED_DOC}" in out
    assert "== validate" not in out
    assert (root / OLD_STUB).is_file()
    assert not (root / SHIPPED_DOC).exists()
    assert not (root / "schemas" / "orchestration.schema.json").exists()


def test_a_doc_the_project_has_is_kept(tmp_path: Path) -> None:
    run_init_project(tmp_path)
    (tmp_path / SHIPPED_DOC).write_text("our policy\n", encoding="utf-8")

    assert copy_missing_docs(tmp_path) == []
    assert (tmp_path / SHIPPED_DOC).read_text(encoding="utf-8") == "our policy\n"


def test_a_docs_link_out_of_the_repo_is_not_followed(tmp_path: Path, capsys) -> None:
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    run_init_project(root)
    shutil.rmtree(root / "docs")
    (root / "docs").symlink_to(outside, target_is_directory=True)

    assert copy_missing_docs(root) == []
    assert f"skipped {SHIPPED_DOC}" in capsys.readouterr().out
    assert not any(outside.iterdir())
