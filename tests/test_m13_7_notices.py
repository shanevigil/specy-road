"""M13.7: notices that were correct but misleading.

A symlinked skills directory listed every skill twice; a new ``.gitignore``
rule silently matched files already in the tree. (The ``session end`` wording
is pinned in ``test_session_presence.py``.)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.agent_ignores import GITIGNORE, MATCH_LIMIT, apply_and_report
from specy_road.managed_block import MARKER_END, MARKER_START
from specy_road.bundled_scripts.refresh_stubs import main
from specy_road.bundled_scripts.refresh_stubs_report import report

NOTE = "(.agents/skills → .claude/skills)"


def _linked_skills_repo(tmp_path: Path) -> Path:
    """``.agents/skills`` is a symlink to ``.claude/skills``, with a claude-code pack recorded."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "skills").symlink_to(Path("..") / ".claude" / "skills")
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"claude-code": [".agents/skills/specyrd-brief/SKILL.md"]}}), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_symlinked_skills_dir_reports_each_skill_once_with_the_link(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _linked_skills_repo(tmp_path)
    main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])
    brief = [ln for ln in capsys.readouterr().out.splitlines() if "specyrd-brief" in ln]
    verb = "would write" if dry_run else "wrote"
    assert brief == [f"{verb} .claude/skills/specyrd-brief/SKILL.md {NOTE}"]


def _reverse_linked_repo(tmp_path: Path) -> Path:
    """``.claude/skills`` is a symlink to ``.agents/skills`` (the other direction)."""
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").symlink_to(Path("..") / ".agents" / "skills")
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"claude-code": [".agents/skills/specyrd-brief/SKILL.md"]}}), encoding="utf-8")
    return tmp_path


def _skill_lines(out: str, verb: str) -> list[str]:
    return [ln.removeprefix(verb) for ln in out.splitlines() if "specyrd-" in ln and ln.startswith(verb)]


def test_a_reverse_symlinked_skills_dir_reports_each_skill_once_and_runs_agree(tmp_path: Path, capsys) -> None:
    repo = _reverse_linked_repo(tmp_path)
    main(["--repo-root", str(repo), "--dry-run"])
    dry = _skill_lines(capsys.readouterr().out, "would write ")
    main(["--repo-root", str(repo)])
    real = _skill_lines(capsys.readouterr().out, "wrote ")
    assert [ln for ln in dry if "specyrd-brief" in ln] == [".agents/skills/specyrd-brief/SKILL.md"]
    assert dry == real and len(dry) == len({ln.split("/")[2] for ln in dry})


def _outward_and_back_repo(tmp_path: Path) -> Path:
    """``.agents/skills`` links outside the repo; the skill folder there links back inside."""
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    (repo / "real" / "brief").mkdir(parents=True)
    outside.mkdir()
    (repo / ".agents").mkdir()
    (repo / ".agents" / "skills").symlink_to(outside)
    (outside / "specyrd-brief").symlink_to(repo / "real" / "brief")
    (repo / ".specyrd").mkdir()
    (repo / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"codex": [".agents/skills/specyrd-brief/SKILL.md"]}}), encoding="utf-8")
    return repo


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_link_out_of_the_repo_and_back_names_its_target_absolutely(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _outward_and_back_repo(tmp_path)
    main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])
    verb = "would write" if dry_run else "wrote"
    brief = [ln for ln in capsys.readouterr().out.splitlines() if "brief/SKILL.md" in ln]
    assert brief == [f"{verb} real/brief/SKILL.md (.agents/skills → {(tmp_path / 'outside').resolve().as_posix()})"]


def test_the_report_folds_two_names_for_one_file_into_its_real_path(tmp_path: Path, capsys) -> None:
    repo = _linked_skills_repo(tmp_path)
    written = [".agents/skills/x/SKILL.md", ".claude/skills/x/SKILL.md", ".gitignore (updated)"]
    report(written, [], dry_run=True, footer=False, repo_root=repo)
    assert capsys.readouterr().out.splitlines() == [
        f"would write .claude/skills/x/SKILL.md {NOTE}",
        "would write .gitignore (updated)",
    ]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout


def _repo_with_prompts(tmp_path: Path, untracked: int = 1) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "prompt-a.md").write_text("a\n", encoding="utf-8")
    _git(tmp_path, "add", "work/prompt-a.md")
    _git(tmp_path, "commit", "-qm", "tracked prompt")
    for i in range(untracked):
        (tmp_path / "work" / f"prompt-u{i:02d}.md").write_text("u\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_new_ignore_rule_lists_tracked_and_untracked_matches(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _repo_with_prompts(tmp_path)
    written: list[str] = []
    apply_and_report(repo, "", written, dry_run=dry_run)
    out = capsys.readouterr().out.splitlines()
    assert out == [
        ".gitignore: new rules match files already in the tree (nothing was untracked):",
        "  work/prompt-a.md (work/prompt-*.md): still tracked; git keeps tracking it",
        "  work/prompt-u00.md (work/prompt-*.md): untracked; now hidden from git status",
    ]
    assert f"{GITIGNORE} (created)" in written
    assert "work/prompt-a.md" in _git(repo, "ls-files").split()   # nothing untracked


def test_the_match_list_stops_at_the_limit_then_counts(tmp_path: Path, capsys) -> None:
    repo = _repo_with_prompts(tmp_path, untracked=MATCH_LIMIT + 4)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 + MATCH_LIMIT + 1
    assert out[-1] == "  … and 5 more"


def test_rules_already_in_the_file_are_not_new(tmp_path: Path, capsys) -> None:
    repo = _repo_with_prompts(tmp_path)
    apply_and_report(repo, "", [])
    capsys.readouterr()
    apply_and_report(repo, "", [])
    assert capsys.readouterr().out == ""


def _status(repo: Path) -> str:
    return _git(repo, "status", "--porcelain", "--untracked-files=all")


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_path_the_new_rule_only_matches_as_a_pathspec_is_not_called_hidden(
        tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _repo_with_prompts(tmp_path, untracked=0)
    (repo / "work" / "prompt-dir").mkdir()
    (repo / "work" / "prompt-dir" / "sub.md").write_text("s\n", encoding="utf-8")
    apply_and_report(repo, "", [], dry_run=dry_run)
    assert "prompt-dir" not in capsys.readouterr().out
    assert "?? work/prompt-dir/sub.md" in _status(repo)


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_later_negation_keeps_the_file_visible_and_unlisted(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _repo_with_prompts(tmp_path, untracked=0)
    (repo / GITIGNORE).write_text(f"{MARKER_START}\n{MARKER_END}\n!work/prompt-keep.md\n", encoding="utf-8")
    (repo / "work" / "prompt-keep.md").write_text("k\n", encoding="utf-8")
    apply_and_report(repo, "", [], dry_run=dry_run)
    out = capsys.readouterr().out
    assert "prompt-keep" not in out
    assert "  work/prompt-a.md (work/prompt-*.md): still tracked; git keeps tracking it" in out.splitlines()
    assert "?? work/prompt-keep.md" in _status(repo)
