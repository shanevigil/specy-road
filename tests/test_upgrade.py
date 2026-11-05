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

from specy_road.agent_guide_block import render_guide_lines
from specy_road.agents_md_block import LOCAL_MD, RULES_MD, TEAM_MD, agents_md_block_state, render_rules
from specy_road.bundled_scripts.upgrade import copy_missing_docs, run_upgrade
from specy_road.init_project import run_init_project
from specy_road.managed_block import HTML_COMMENT, render_block
from specy_road.specyrd_init import run_init

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
    assert f"wrote {SHIPPED_DOC} (named in the .specyrd/AGENTS.md load order)" in out
    assert (root / SHIPPED_DOC).is_file()
    assert "OK: roadmap and registry validate." in out
    for warning in ("agents: warning", "schemas: warning", "specyrd: warning"):
        assert warning not in err
    assert not (root / ".cursor" / "commands").exists()
    assert (root / ".agents" / "skills" / "specyrd-validate" / "SKILL.md").is_file()
    assert any((root / "model-profiles").rglob("*.md"))
    assert "Our own rules." in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert (root / "roadmap" / "manifest.json").read_text(encoding="utf-8") == roadmap_before


def test_no_roster_upgrade_writes_only_the_readme_and_names_profiles_all_on_every_run(tmp_path: Path, capsys) -> None:
    """M13.5 A1: with no roster, upgrade adds only model-profiles/README.md and, on the first run and a
    repeat, names `--profiles all` instead of claiming every shipped profile is present."""
    root = _old_repo(tmp_path)
    (root / "roadmap" / "orchestration.yaml").unlink()
    hint = "`specy-road refresh-profiles --profiles all` adds every one"
    for _run in range(2):
        assert run_upgrade(root) == 0
        out = capsys.readouterr().out
        assert hint in out and "every profile this version ships" not in out
        assert [p.name for p in (root / "model-profiles").rglob("*.md")] == ["README.md"]


def test_a_missing_digest_is_a_next_step_not_a_failure(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)

    assert run_upgrade(root) == 0

    out = capsys.readouterr().out
    assert "Run specy-road digest" in out and "Not specy-road sync" in out


def test_dry_run_writes_nothing_and_validates_a_copy(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout

    assert run_upgrade(root, dry_run=True, prune=True) == 0

    out = capsys.readouterr().out
    assert "would remove .cursor/commands/specyrd-validate.md" in out
    assert "migration: 1 command stubs (*/commands/) become 1 skills under .agents/skills/" in out
    assert f"would write {SHIPPED_DOC}" in out
    assert "== validate" in out and "OK: roadmap and registry validate." in out
    assert "== other worktrees" not in out
    assert (root / OLD_STUB).is_file()
    assert not (root / SHIPPED_DOC).exists()
    assert not (root / "schemas" / "orchestration.schema.json").exists()
    assert subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout == status


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


def test_upgrade_moves_the_full_agents_md_section_into_the_rules_file_once(tmp_path: Path, capsys) -> None:
    """2026-11-04: an adopter's full AGENTS.md and CLAUDE.md sections become stubs; their own text stays."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    run_init_project(tmp_path)
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None,
             write_claude_md=True)
    for rel in (RULES_MD, TEAM_MD):
        (tmp_path / rel).unlink()
    old = render_block(render_rules().splitlines(), style=HTML_COMMENT)   # the size of the section rc2 wrote
    (tmp_path / "AGENTS.md").write_text(f"# Ours\n\nTeam text before.\n\n{old}\nTeam text after.\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(f"# Claude\n\n{old}\nClaude text after.\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    capsys.readouterr()

    assert run_upgrade(tmp_path) == 0
    out = capsys.readouterr().out
    assert f"migration: the specy-road section of AGENTS.md ({len(old.splitlines())} lines) becomes a" in out
    assert f"points at {RULES_MD}" in out and TEAM_MD in out and LOCAL_MD in out
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# Ours\n\nTeam text before.\n") and agents.endswith("Team text after.\n")
    assert agents_md_block_state(tmp_path) == "current"
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith("# Claude\n") and claude.endswith("Claude text after.\n")
    assert "@.specyrd/AGENTS.md" in claude.splitlines() and "\n".join(render_guide_lines()) in claude
    assert (tmp_path / RULES_MD).read_text(encoding="utf-8") == render_rules()
    assert (tmp_path / TEAM_MD).is_file() and not (tmp_path / LOCAL_MD).exists()
    assert LOCAL_MD in (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()

    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert run_upgrade(tmp_path) == 0
    out = capsys.readouterr().out
    assert "migration:" not in out and "stubs and managed blocks already current" in out
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and ".git" not in p.parts} == files
