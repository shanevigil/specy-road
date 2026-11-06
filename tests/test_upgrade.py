"""`specy-road upgrade`: the four upgrade commands in order, one invocation.

rc1 adopters ran refresh-schemas / refresh-stubs / validate from memory and
each stopped somewhere different: duplicate /specyrd-… commands left behind,
no AGENTS.md block, model-profiles/ never added. The contract tested here is
that one run on a 0.2.x-shaped repo clears every upgrade warning `validate`
knows about, and touches nothing outside the refreshers' own paths.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.agent_guide_block import render_guide_lines
from specy_road.agents_md_block import LOCAL_MD, RULES_MD, TEAM_MD, agents_md_block_state, render_rules
from specy_road.bundled_scripts.digest_cli import cmd_digest
from specy_road.bundled_scripts.export_roadmap_md import export_markdown
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.upgrade import copy_missing_docs, run_upgrade
from specy_road.digest import render_digest
from specy_road.init_project import run_init_project
from specy_road.managed_block import HTML_COMMENT, render_block
from specy_road.specyrd_init import run_init
from tests.test_digest_quality import land
from tests.test_history_walk import commit, git
from tests.upgrade_repo_helpers import OLD_STUB, SHIPPED_DOC, old_repo

def test_one_run_clears_every_upgrade_warning(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
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
    root = old_repo(tmp_path)
    (root / "roadmap" / "orchestration.yaml").unlink()
    hint = "`specy-road refresh-profiles --profiles all` adds every one"
    for _run in range(2):
        assert run_upgrade(root) == 0
        out = capsys.readouterr().out
        assert hint in out and "every profile this version ships" not in out
        assert [p.name for p in (root / "model-profiles").rglob("*.md")] == ["README.md"]


DIGEST, INDEX = "roadmap-context.md", "roadmap.md"
WROTE_DIGEST, WROTE_INDEX = "wrote roadmap-context.md (specy-road digest)", "wrote roadmap.md (specy-road export)"
REFUSED_DIGEST = "refused roadmap-context.md (a symlink leads outside the project)"
REFUSED_INDEX = "refused roadmap.md (a symlink leads outside the project)"
NEXT_DIGEST = "Run specy-road digest (and specy-road export if roadmap.md is tracked), then commit them. Not specy-road sync"


def _finished_leaf(root: Path, outside: Path) -> None:
    """M1.1 completed and landed with a tally after the digest was committed: the digest now lacks Quality by area."""
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    chunk = root / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text(encoding="utf-8"))
    doc["nodes"][1]["status"] = "Complete"
    chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (root / DIGEST).write_text(render_digest(root), encoding="utf-8")
    commit(root, "base")
    land(root, "project-setup", "M1.1 rounds=1 blocks=0 approvals=1 integrity=0 rca=0 findings=none")
    assert "## Quality by area" in render_digest(root)


def _hand_drifted_digest(root: Path, outside: Path) -> None:
    (root / DIGEST).write_text("an old digest\n", encoding="utf-8")


def _tracked_index(root: Path, outside: Path) -> None:
    (root / INDEX).write_text("old index\n", encoding="utf-8")
    git(root, "add", INDEX)


def _untracked_index(root: Path, outside: Path) -> None:
    (root / INDEX).write_text("old index\n", encoding="utf-8")


def _invalid_graph(root: Path, outside: Path) -> None:
    chunk = root / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text(encoding="utf-8"))
    doc["nodes"][1]["dependencies"] = ["M9.9"]
    chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (root / DIGEST).write_text(render_digest(root), encoding="utf-8")   # current: the next step stays anyway


def _dangling_link_out(root: Path, outside: Path) -> None:
    (root / DIGEST).symlink_to(outside / "digest.md")


def _link_to_outside_file(root: Path, outside: Path) -> None:
    """Not UTF-8, so reading it before the boundary check would raise instead of refusing."""
    (outside / "digest.md").write_bytes(b"\xff\xfe\x00")
    (root / DIGEST).symlink_to(outside / "digest.md")


def _tracked_index_link_to_outside_file(root: Path, outside: Path) -> None:
    (outside / "index.md").write_bytes(b"\xff\xfe\x00")
    (root / INDEX).symlink_to(outside / "index.md")
    git(root, "add", INDEX)


def _non_utf8_digest(root: Path, outside: Path) -> None:
    (root / DIGEST).write_bytes(b"\xff\xfe\x00")


def _state(path: Path) -> object:
    return ("link", os.readlink(path)) if path.is_symlink() else path.read_bytes() if path.exists() else None


@pytest.mark.parametrize(("setup", "dry_run", "rendered", "said", "unsaid", "exit_code"), [
    pytest.param(None, False, {DIGEST}, [WROTE_DIGEST], [NEXT_DIGEST], 0, id="missing-digest"),
    pytest.param(_finished_leaf, False, {DIGEST}, [WROTE_DIGEST], [NEXT_DIGEST], 0, id="drifted-after-finished-leaf"),
    pytest.param(_tracked_index, False, {DIGEST, INDEX}, [WROTE_DIGEST, WROTE_INDEX], [NEXT_DIGEST], 0,
                 id="tracked-drifted-roadmap-md"),
    pytest.param(_untracked_index, False, {DIGEST}, [WROTE_DIGEST], [WROTE_INDEX, NEXT_DIGEST], 0,
                 id="untracked-roadmap-md"),
    pytest.param(_invalid_graph, False, set(), ["OK: roadmap-context.md matches the roadmap.", NEXT_DIGEST], [WROTE_DIGEST, "== generated files"], 1,
                 id="invalid-graph"),
    pytest.param(_dangling_link_out, False, set(), [REFUSED_DIGEST, NEXT_DIGEST], [WROTE_DIGEST], 0,
                 id="dangling-link-out"),
    pytest.param(_link_to_outside_file, False, set(), [REFUSED_DIGEST, NEXT_DIGEST], [WROTE_DIGEST], 0,
                 id="link-to-outside-file"),
    pytest.param(_tracked_index_link_to_outside_file, False, {DIGEST}, [WROTE_DIGEST, REFUSED_INDEX, NEXT_DIGEST],
                 [WROTE_INDEX], 0, id="tracked-roadmap-md-link-to-outside-file"),
    pytest.param(_non_utf8_digest, False, {DIGEST}, [WROTE_DIGEST], [NEXT_DIGEST], 0, id="non-utf8-digest"),
    pytest.param(_hand_drifted_digest, True, set(), ["would write roadmap-context.md (specy-road digest)"],
                 [WROTE_DIGEST], 0, id="dry-run-drifted-digest"),
])
def test_upgrade_regenerates_the_drifted_generated_files(
    tmp_path: Path, capsys, setup, dry_run: bool, rendered: set[str], said: list[str], unsaid: list[str],
    exit_code: int,
) -> None:
    """M21.16 A3: validate passed → the drifted digest and a tracked roadmap.md are written, never through a link out."""
    root, outside = old_repo(tmp_path / "repo"), tmp_path / "outside"
    outside.mkdir()
    if setup:
        setup(root, outside)
    kept = {rel: _state(root / rel) for rel in (DIGEST, INDEX) if rel not in rendered}
    checkout, theirs = _files(root), _files(outside)
    capsys.readouterr()

    assert run_upgrade(root, dry_run=dry_run) == exit_code

    lines = capsys.readouterr().out.splitlines()
    for text in said:
        assert any(line.removeprefix("- ").startswith(text) for line in lines), text
    for text in unsaid:
        assert not any(text in line for line in lines), text
    assert {rel: _state(root / rel) for rel in kept} == kept
    assert _files(outside) == theirs
    if dry_run:
        assert _files(root) == checkout
    if DIGEST in rendered:
        assert (root / DIGEST).read_text(encoding="utf-8") == render_digest(root)
        assert cmd_digest(argparse.Namespace(output=DIGEST, check=True, repo_root=root)) == 0
    if INDEX in rendered:
        assert (root / INDEX).read_text(encoding="utf-8") == export_markdown(load_roadmap(root)["nodes"])


def _files(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def test_dry_run_writes_nothing_and_validates_a_copy(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
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
