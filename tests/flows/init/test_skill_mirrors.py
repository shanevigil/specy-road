"""Skills ship once: `.agents/skills` plus `.claude/skills`, never a `.cursor`/`.codex` copy.

Cursor and Codex already read `.agents/skills`, so a copy under `.cursor/skills`,
`.codex/skills` or `.cursor/commands` loads each skill twice
(harness compatibility triage, finding 6). `init` writes
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



def test_a_users_own_skill_directory_is_reported_skipped(tmp_path: Path, capsys) -> None:
    mine = tmp_path / ".claude" / "skills" / "specyrd-validate"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: specyrd-validate\n---\nmy own\n")
    (mine / "extra.txt").write_text("x")
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None)
    assert ".claude/skills/specyrd-validate (skipped (not ours))" in res.skipped
    assert not any(w.startswith(".claude/skills/specyrd-validate") for w in res.written)
    assert (mine / "extra.txt").is_file()



def test_a_foreign_skill_link_is_left_alone_on_first_install(tmp_path: Path) -> None:
    link = tmp_path / ".claude" / "skills" / "specyrd-brief"
    link.parent.mkdir(parents=True)
    os.symlink("../../../mine", link)
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    assert os.readlink(link) == "../../../mine"
    assert ".claude/skills/specyrd-brief (skipped (not ours))" in res.skipped
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=True, ai_commands_dir=None, role="dev")
    assert os.readlink(link) == "../../../mine"          # round 6 B18: no manifest record, so --force is refused too
    assert ".claude/skills/specyrd-brief (skipped (not ours))" in res.skipped



# --- Gemini F3 / Sol B2 ---------------------------------------------------------

def test_no_link_to_a_skipped_canonical_skill_and_no_rmtree_without_force(tmp_path: Path) -> None:
    mine = tmp_path / ".agents" / "skills" / "specyrd-validate" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("USER SKILL\n")
    theirs = tmp_path / ".claude" / "skills" / "specyrd-brief" / "SKILL.md"
    theirs.parent.mkdir(parents=True)
    theirs.write_text("---\nname: specyrd-brief\n---\nThin stub — my own specyrd notes\n")   # looks like ours; is not
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    assert ".agents/skills/specyrd-validate/SKILL.md" in res.skipped
    assert not (tmp_path / ".claude" / "skills" / "specyrd-validate").exists()
    assert theirs.read_text().endswith("my own specyrd notes\n") and not theirs.parent.is_symlink()
