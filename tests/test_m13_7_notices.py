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
from specy_road.written_entry import Written
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
    written = [Written(".agents/skills/x/SKILL.md"), Written(".claude/skills/x/SKILL.md"),
               Written(".gitignore", "updated")]
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


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_negation_before_the_block_loses_to_the_new_rule_and_is_listed(
        tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _repo_with_prompts(tmp_path, untracked=0)
    before = f"!work/prompt-keep.md\n{MARKER_START}\n{MARKER_END}\n"
    (repo / GITIGNORE).write_text(before, encoding="utf-8")
    (repo / "work" / "prompt-keep.md").write_text("k\n", encoding="utf-8")
    apply_and_report(repo, "", [], dry_run=dry_run)
    assert "  work/prompt-keep.md (work/prompt-*.md): untracked; now hidden from git status" in (
        capsys.readouterr().out.splitlines())
    if dry_run:
        assert (repo / GITIGNORE).read_text(encoding="utf-8") == before
    else:
        assert "prompt-keep" not in _status(repo)


def _generic_repo(tmp_path: Path, rel_dir: str, *, link_to: str | None = None) -> Path:
    """A ``generic`` pack recorded under ``rel_dir``, optionally a symlink to ``link_to`` (repo-relative)."""
    stub_dir = tmp_path / rel_dir
    stub_dir.parent.mkdir(parents=True, exist_ok=True)
    if link_to:
        (tmp_path / link_to).mkdir(parents=True)
        stub_dir.symlink_to(Path(*[".."] * (len(Path(rel_dir).parts) - 1), link_to))
    else:
        stub_dir.mkdir()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        (stub_dir / name).write_text("stale\n", encoding="utf-8")
    (tmp_path / ".specyrd").mkdir()
    recorded = [f"{rel_dir}/specyrd-validate.md", f"{rel_dir}/specyrd-brief.md"]
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"generic": recorded}}), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("rel_dir", ["docs/team (commands)", "docs/équipe #1 !x"])
def test_a_generic_dir_with_parentheses_or_odd_characters_is_reported_whole(
        tmp_path: Path, capsys, dry_run: bool, rel_dir: str) -> None:
    repo = _generic_repo(tmp_path, rel_dir)
    main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])
    verb = "would write" if dry_run else "wrote"
    out = capsys.readouterr().out.splitlines()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        assert f"{verb} {rel_dir}/{name}" in out


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_symlinked_generic_dir_with_parentheses_reports_its_real_path(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _generic_repo(tmp_path, "docs/team (commands)", link_to="actual")
    main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])
    verb = "would write" if dry_run else "wrote"
    out = capsys.readouterr().out.splitlines()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        assert f"{verb} actual/{name} (docs/team (commands) → actual)" in out


def _untracked(repo: Path) -> set[str]:
    return {ln[3:].strip('"') for ln in _git(repo, "-c", "core.quotePath=false", "status", "--porcelain",
                                           "--untracked-files=all").splitlines() if ln.startswith("?? ")}


_PROBES = {
    "odd names": ("", None, ["work/prompt-a b.md", "work/prompt-β.md", "work/prompt-#x.md", "work/prompt-!y.md",
                             "work/reviews/#r.json", "work/reviews/!r.json", "#top.md", "!top.md"]),
    "no trailing newline": ("", b"node_modules", ["work/prompt-n.md", "notes.md"]),
    "crlf": ("", b"!work/prompt-keep.md\r\n" + MARKER_START.encode() + b"\r\n" + MARKER_END.encode() + b"\r\n",
             ["work/prompt-keep.md", "work/prompt-other.md"]),
    "nested project": ("sr/", None, ["sr/work/prompt-x.md", "sr/work/.sessions/s.json", "work/prompt-y.md"]),
}


@pytest.mark.parametrize("probe", sorted(_PROBES))
def test_the_hidden_list_is_exactly_what_git_status_stops_showing(tmp_path: Path, capsys, probe: str) -> None:
    prefix, gitignore, files = _PROBES[probe]
    repo = _repo_with_prompts(tmp_path, untracked=0)
    if gitignore is not None:
        (repo / GITIGNORE).write_bytes(gitignore)
    for rel in files:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n", encoding="utf-8")
    apply_and_report(repo, prefix, [], dry_run=True)
    dry = capsys.readouterr().out
    shown = _untracked(repo)
    apply_and_report(repo, prefix, [])
    assert capsys.readouterr().out == dry                       # dry and real agree
    listed = {ln[2:].split(" (")[0] for ln in dry.splitlines() if ln.endswith("now hidden from git status")}
    assert listed == shown - _untracked(repo) - {GITIGNORE} and listed


def test_diff_shows_stubs_under_a_parenthesised_dir(tmp_path: Path, capsys) -> None:
    repo = _generic_repo(tmp_path, "docs/team (commands)")
    main(["--repo-root", str(repo), "--diff"])
    out = capsys.readouterr().out.splitlines()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        assert f"+++ b/docs/team (commands)/{name}" in out
        assert f"would write docs/team (commands)/{name}" not in out   # diffed, not left as a bare line


@pytest.mark.parametrize("dry_run", [True, False])
def test_an_unreadable_nested_gitignore_skips_the_note_but_not_the_writes(
        tmp_path: Path, capsys, dry_run: bool) -> None:
    import os
    if os.geteuid() == 0:
        pytest.skip("root reads any file")
    repo = _repo_with_prompts(tmp_path)
    nested = repo / "work" / ".gitignore"
    nested.write_text("x\n", encoding="utf-8")
    nested.chmod(0)
    written: list[str] = []
    try:
        apply_and_report(repo, "", written, dry_run=dry_run)
    finally:
        nested.chmod(0o644)
    out = capsys.readouterr().out.splitlines()
    assert sorted(written) == [".cursorindexingignore (created)", ".gitignore (created)"]
    assert len(out) == 1 and out[0].startswith("ignore check skipped: ") and "Permission denied" in out[0]
    assert (repo / GITIGNORE).is_file() is not dry_run and (repo / ".cursorindexingignore").is_file() is not dry_run


@pytest.mark.parametrize("dry_run", [True, False])
def test_ignorecase_from_the_checkout_is_honoured(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _repo_with_prompts(tmp_path, untracked=0)
    _git(repo, "config", "core.ignorecase", "true")
    (repo / "work" / "Prompt-case.md").write_text("c\n", encoding="utf-8")
    apply_and_report(repo, "", [], dry_run=dry_run)
    assert "  work/Prompt-case.md (work/prompt-*.md): untracked; now hidden from git status" in (
        capsys.readouterr().out.splitlines())
    assert ("Prompt-case" in _status(repo)) is dry_run          # the real update does hide it


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_tracked_file_an_older_rule_already_ignores_is_still_listed(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _repo_with_prompts(tmp_path, untracked=0)
    (repo / "work" / "prompt-tracked.md").write_text("t\n", encoding="utf-8")
    _git(repo, "add", "work/prompt-tracked.md")
    _git(repo, "commit", "-qm", "tracked")
    (repo / GITIGNORE).write_text("work/*.md\n", encoding="utf-8")
    index = _git(repo, "ls-files", "-s")
    apply_and_report(repo, "", [], dry_run=dry_run)
    assert "  work/prompt-tracked.md (work/prompt-*.md): still tracked; git keeps tracking it" in (
        capsys.readouterr().out.splitlines())
    assert _git(repo, "ls-files", "-s") == index


def test_a_git_dir_from_a_hook_does_not_point_the_scratch_repo_at_the_checkout(
        tmp_path: Path, capsys, monkeypatch) -> None:
    repo = _repo_with_prompts(tmp_path)
    config = (repo / ".git" / "config").read_bytes()
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    apply_and_report(repo, "", [], dry_run=True)
    assert "  work/prompt-u00.md (work/prompt-*.md): untracked; now hidden from git status" in (
        capsys.readouterr().out.splitlines())
    assert (repo / ".git" / "config").read_bytes() == config
