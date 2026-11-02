"""Skills ship once: `.agents/skills` plus `.claude/skills`, never a `.cursor`/`.codex` copy.

Cursor and Codex already read `.agents/skills`, so a copy under `.cursor/skills`,
`.codex/skills` or `.cursor/commands` loads each skill twice
(docs/design-notes/harness-compatibility-triage.md, finding 6). `init` writes
none; `upgrade --prune` deletes the ones nothing is lost by deleting; `validate`
warns while any remains.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts.refresh_stubs import refresh_stubs
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.init_project import run_init_project
from specy_road.specyrd_init import run_init, warn_if_skills_mirrored
from specy_road.specyrd_skills import SKILL_AGENTS, mirrored_copies

SKILLS = Path(".agents/skills")
NAMES = ("specyrd-validate.md", "specyrd-brief.md")


def _init(root: Path, agent: str) -> None:
    run_init(target=root, agent=agent, dry_run=False, force=False, ai_commands_dir=None, role="dev")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert run_init_project(root) == 0
    _init(root, "cursor")
    return root


def _flat_stub(where: Path, name: str) -> Path:
    """The flat stub ``specyrd init --ai generic`` writes, made outside the repository under test."""
    where.mkdir()
    run_init(target=where, agent="generic", dry_run=False, force=False, ai_commands_dir=Path("cmds"), role="dev")
    return where / "cmds" / name


@pytest.mark.parametrize("agent", sorted(SKILL_AGENTS))
def test_init_writes_nothing_under_cursor_or_codex(tmp_path: Path, agent: str) -> None:
    _init(tmp_path, agent)
    assert (tmp_path / SKILLS / "specyrd-validate" / "SKILL.md").is_file()
    assert not (tmp_path / ".cursor").exists() and not (tmp_path / ".codex").exists()


def _mirror(repo: Path) -> dict[str, Path]:
    """A verbatim copy, a link, a verbatim flat stub, a hand-edited copy and an unrelated skill."""
    copy = repo / ".cursor/skills/specyrd-validate"
    shutil.copytree(repo / SKILLS / "specyrd-validate", copy)
    link = repo / ".codex/skills/specyrd-validate"
    link.parent.mkdir(parents=True)
    os.symlink("../../.agents/skills/specyrd-validate", link, target_is_directory=True)
    flat = repo / ".cursor/commands/specyrd-brief.md"
    flat.parent.mkdir(parents=True)
    shutil.copyfile(_flat_stub(repo.parent / "generic", "specyrd-brief.md"), flat)
    edited = repo / ".codex/skills/specyrd-brief"
    edited.mkdir(parents=True)
    (edited / "SKILL.md").write_text("---\nname: specyrd-brief\n---\nmy own edits\n", encoding="utf-8")
    ours = repo / ".cursor/skills/my-skill"
    ours.mkdir(parents=True)
    (ours / "SKILL.md").write_text("mine\n", encoding="utf-8")
    return {"copy": copy, "link": link, "flat": flat, "edited": edited, "ours": ours}


def test_only_verbatim_copies_and_links_are_disposable(repo: Path) -> None:
    _mirror(repo)
    assert mirrored_copies(repo, NAMES, set()) == (
        [".cursor/skills/specyrd-validate", ".codex/skills/specyrd-validate", ".cursor/commands/specyrd-brief.md"],
        [".codex/skills/specyrd-brief"],
    )


def test_upgrade_prune_removes_the_copies_and_keeps_the_rest(repo: Path, capsys) -> None:
    paths = _mirror(repo)
    warn_if_skills_mirrored(repo)
    err = capsys.readouterr().err
    assert err.startswith("skills: warning — .cursor/skills/specyrd-validate, ")
    assert "Run: specy-road upgrade --prune; then delete .codex/skills/specyrd-brief by hand" in err

    run_upgrade(repo, prune=True)
    out = capsys.readouterr().out
    assert "removed .cursor/skills/specyrd-validate (no longer installed)" in out
    assert not any(paths[k].exists() or paths[k].is_symlink() for k in ("copy", "link", "flat"))
    assert paths["edited"].is_dir() and paths["ours"].is_dir()
    assert (repo / SKILLS / "specyrd-validate" / "SKILL.md").is_file()

    warn_if_skills_mirrored(repo)
    err = capsys.readouterr().err
    assert err.startswith("skills: warning — .codex/skills/specyrd-brief duplicates skills in .agents/skills/")
    assert "upgrade --prune" not in err and "Delete .codex/skills/specyrd-brief by hand" in err

    shutil.rmtree(paths["edited"])
    warn_if_skills_mirrored(repo)
    assert capsys.readouterr().err == ""


def test_without_prune_the_copies_are_listed_not_deleted(repo: Path) -> None:
    paths = _mirror(repo)
    _written, orphans = refresh_stubs(repo)
    assert ".cursor/skills/specyrd-validate" in orphans and ".codex/skills/specyrd-brief" not in orphans
    assert paths["copy"].is_dir()


def test_a_generic_pack_in_cursor_commands_is_not_a_copy(repo: Path, capsys) -> None:
    run_init(target=repo, agent="generic", dry_run=False, force=False,
             ai_commands_dir=Path(".cursor/commands"), role="dev")
    warn_if_skills_mirrored(repo)
    assert capsys.readouterr().err == ""
    assert refresh_stubs(repo, prune=True)[1] == []
    assert (repo / ".cursor/commands/specyrd-validate.md").is_file()


def test_a_mirror_dir_linked_to_agents_skills_is_never_pruned(repo: Path, capsys) -> None:
    (repo / ".cursor").mkdir()
    os.symlink("../.agents/skills", repo / ".cursor/skills", target_is_directory=True)
    warn_if_skills_mirrored(repo)
    assert capsys.readouterr().err == ""
    refresh_stubs(repo, prune=True)
    assert (repo / SKILLS / "specyrd-validate" / "SKILL.md").is_file()


def test_a_copy_with_no_installed_skill_is_not_a_mirror(tmp_path: Path) -> None:
    copy = tmp_path / ".cursor/skills/specyrd-validate"
    copy.mkdir(parents=True)
    (copy / "SKILL.md").write_text("anything\n", encoding="utf-8")
    assert mirrored_copies(tmp_path, NAMES, set()) == ([], [])
