"""M13.7: notices that were correct but misleading.

A symlinked skills directory listed every skill twice; a new ``.gitignore``
rule silently matched files already in the tree. (The ``session end`` wording
is pinned in ``test_session_presence.py``.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road.agent_ignores import GITIGNORE, MATCH_LIMIT, apply_and_report
from specy_road.ignore_report import ESTIMATE_HEADER, HIDDEN_NOTE, REAL_HEADER, TRACKED_NOTE, UNTRACK_HINT
from specy_road.managed_block import MARKER_END, MARKER_START
from specy_road.written_entry import Written
from specy_road.bundled_scripts.refresh_stubs import main
from specy_road.bundled_scripts.refresh_stubs_report import report
from tests.m13_7_ignore_helpers import git, listed, repo_with_prompts, shown, write

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


def test_the_report_folds_two_names_for_one_file_into_its_real_path(tmp_path: Path, capsys) -> None:
    repo = _linked_skills_repo(tmp_path)
    written = [Written(".agents/skills/x/SKILL.md"), Written(".claude/skills/x/SKILL.md"),
               Written(".gitignore", "updated")]
    report(written, [], dry_run=True, footer=False, repo_root=repo)
    assert capsys.readouterr().out.splitlines() == [
        f"would write .claude/skills/x/SKILL.md {NOTE}",
        "would write .gitignore (updated)",
    ]






def test_the_match_list_stops_at_the_limit_then_counts(tmp_path: Path, capsys) -> None:
    repo = repo_with_prompts(tmp_path, untracked=MATCH_LIMIT + 4)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 + MATCH_LIMIT + 4
    assert out[-4:] == ["  … and 5 more",
                        "  to stop tracking them, run from the git root (specy-road never runs it):",
                        "    git rm --cached -- work/prompt-a.md",
                        UNTRACK_HINT]


def test_rules_already_in_the_file_are_not_new(tmp_path: Path, capsys) -> None:
    repo = repo_with_prompts(tmp_path)
    apply_and_report(repo, "", [])
    capsys.readouterr()
    apply_and_report(repo, "", [])
    assert capsys.readouterr().out == ""


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


def _generic_linked_parent(tmp_path: Path) -> tuple[Path, Path]:
    """A stub under a linked directory that is not an agent skills directory."""
    repo = _generic_repo(tmp_path, "docs/team (commands)", link_to="actual")
    return repo, repo / "docs" / "team (commands)"


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_stub_under_a_linked_directory_that_is_not_a_skills_directory_is_refused(
        tmp_path: Path, capsys, dry_run: bool) -> None:
    """M21.37: only an agent skills directory may be a link; skills-link shapes are in test_setup_writers_refuse_links."""
    repo, link = _generic_linked_parent(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    with pytest.raises(SystemExit) as e:
        main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])

    err = capsys.readouterr().err
    assert e.value.code == 1 and f"error: {link} is a symlink" in err, err
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and ".specyrd" not in p.parts
            and p.name not in (".gitignore", ".cursorindexingignore", "AGENTS.md")} == {
        p: b for p, b in before.items() if ".specyrd" not in p.parts}


def test_diff_shows_stubs_under_a_parenthesised_dir(tmp_path: Path, capsys) -> None:
    repo = _generic_repo(tmp_path, "docs/team (commands)")
    main(["--repo-root", str(repo), "--diff"])
    out = capsys.readouterr().out.splitlines()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        assert f"+++ b/docs/team (commands)/{name}" in out
        assert f"would write docs/team (commands)/{name}" not in out   # diffed, not left as a bare line


def test_a_git_dir_from_a_hook_does_not_point_the_scratch_repo_at_the_checkout(
        tmp_path: Path, capsys, monkeypatch) -> None:
    repo = repo_with_prompts(tmp_path)
    config = (repo / ".git" / "config").read_bytes()
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    apply_and_report(repo, "", [], dry_run=True)
    assert "  work/prompt-u00.md (work/prompt-*.md): untracked; now hidden from git status" in (
        capsys.readouterr().out.splitlines())
    assert (repo / ".git" / "config").read_bytes() == config


# --- A2, real run: the report is git's observed change -------------------------------------------



def _commit(repo: Path, rel: str) -> None:
    write(repo, rel)
    git(repo, "add", "--force", rel)
    git(repo, "commit", "-qm", rel)


def _block(before: str = "", after: str = "", eol: str = "\n") -> bytes:
    return f"{before}{MARKER_START}{eol}{MARKER_END}{eol}{after}".encode()


def _case_ignorecase(repo: Path) -> None:
    git(repo, "config", "core.ignorecase", "true")
    write(repo, "work/Prompt-case.md")


def _case_info_exclude(repo: Path) -> None:
    write(repo, ".git/info/exclude", "work/prompt-excluded.md\n")
    write(repo, "work/prompt-excluded.md")
    write(repo, "work/prompt-shown.md")


def _case_self_ignored_nested(repo: Path) -> None:
    write(repo, "work/.gitignore", ".gitignore\n!prompt-keep.md\n")
    write(repo, "work/prompt-keep.md")
    write(repo, "work/prompt-hide.md")


def _case_tracked_already_ignored(repo: Path) -> None:
    _commit(repo, "work/prompt-tracked.md")
    write(repo, GITIGNORE, "work/*.md\n")                       # older rule; the new block lands after it


def _case_tracked_by_an_older_rule_only(repo: Path) -> None:
    _commit(repo, "work/old.md")
    write(repo, GITIGNORE, "work/old.md\n")


def _case_older_rule_after_the_block(repo: Path) -> None:
    write(repo, GITIGNORE, _block(after="work/*.md\n"))          # git lets the later, older rule decide


def _case_nested_rule_decides(repo: Path) -> None:
    write(repo, "work/.gitignore", "*.md\n")                      # git lets the nested rule decide
    git(repo, "add", "work/.gitignore")
    git(repo, "commit", "-qm", "nested")


def _case_tracked_negated_after_the_block(repo: Path) -> None:
    write(repo, GITIGNORE, _block(after="!work/prompt-a.md\n"))   # not ignored at all: no notice


def _case_tracked_negated_in_a_nested_file(repo: Path) -> None:
    write(repo, "work/.gitignore", "!prompt-a.md\n")


#: name -> (setup, prefix, expected now-hidden, expected still-tracked). Every repo also tracks work/prompt-a.md.
CASES = {
    "plain": (lambda r: write(r, "work/prompt-u.md"), "", {"work/prompt-u.md"}, {"work/prompt-a.md"}),
    "r1 pathspec-only match": (lambda r: write(r, "work/prompt-dir/sub.md"), "", set(), {"work/prompt-a.md"}),
    "r1 negation after block": (lambda r: (write(r, GITIGNORE, _block(after="!work/prompt-keep.md\n")),
                                           write(r, "work/prompt-keep.md")), "", set(), {"work/prompt-a.md"}),
    "r2 negation before block": (lambda r: (write(r, GITIGNORE, _block(before="!work/prompt-keep.md\n")),
                                            write(r, "work/prompt-keep.md")), "",
                                 {"work/prompt-keep.md"}, {"work/prompt-a.md"}),
    "r2 crlf": (lambda r: (write(r, GITIGNORE, _block(before="!work/prompt-keep.md\r\n", eol="\r\n")),
                           write(r, "work/prompt-keep.md")), "", {"work/prompt-keep.md"}, {"work/prompt-a.md"}),
    "r2 no trailing newline": (lambda r: (write(r, GITIGNORE, "node_modules"), write(r, "work/prompt-n.md")), "",
                               {"work/prompt-n.md"}, {"work/prompt-a.md"}),
    "r2 odd names": (lambda r: [write(r, p) for p in ("work/prompt-a b.md", "work/prompt-β.md", "work/prompt-#x.md",
                                                       "work/prompt-!y.md", "work/reviews/#r.json", "#top.md")], "",
                     {"work/prompt-a b.md", "work/prompt-β.md", "work/prompt-#x.md", "work/prompt-!y.md",
                      "work/reviews/#r.json"}, {"work/prompt-a.md"}),
    "r2 nested project": (lambda r: [write(r, p) for p in ("sr/work/prompt-x.md", "sr/work/.sessions/s.json",
                                                            "work/prompt-y.md")], "sr/",
                          {"sr/work/prompt-x.md", "sr/work/.sessions/s.json"}, set()),
    "r3 ignorecase": (_case_ignorecase, "", {"work/Prompt-case.md"}, {"work/prompt-a.md"}),
    "r3 info/exclude": (_case_info_exclude, "", {"work/prompt-shown.md"}, {"work/prompt-a.md"}),
    "r3 tracked already ignored": (_case_tracked_already_ignored, "", set(),
                                   {"work/prompt-a.md", "work/prompt-tracked.md"}),
    "r5 tracked by an older rule only": (_case_tracked_by_an_older_rule_only, "", set(), {"work/prompt-a.md"}),
    "r5 older rule after the block decides": (_case_older_rule_after_the_block, "", set(), {"work/prompt-a.md"}),
    "r7 nested rule decides": (_case_nested_rule_decides, "", set(), {"work/prompt-a.md"}),
    "r7 tracked negated after the block": (_case_tracked_negated_after_the_block, "", set(), set()),
    "r7 tracked negated in a nested file": (_case_tracked_negated_in_a_nested_file, "", set(), set()),
    "r4 self-ignored nested .gitignore": (_case_self_ignored_nested, "", {"work/prompt-hide.md"}, {"work/prompt-a.md"}),
}




def _tracked_ignored(repo: Path) -> set[str]:
    return {p for p in git(repo, "ls-files", "-c", "-i", "--exclude-standard", "-z").split("\0") if p}




@pytest.mark.parametrize("case", list(CASES))
def test_the_real_run_reports_exactly_the_visibility_change_git_shows(tmp_path: Path, capsys, case: str) -> None:
    setup, prefix, hidden, tracked = CASES[case]
    repo = repo_with_prompts(tmp_path, untracked=0)
    setup(repo)
    was_shown, index = shown(repo), git(repo, "ls-files", "-s")
    apply_and_report(repo, prefix, [])
    out = capsys.readouterr().out
    assert listed(out, HIDDEN_NOTE) == was_shown - shown(repo) == hidden
    assert listed(out, TRACKED_NOTE) == tracked <= _tracked_ignored(repo)   # attributed to a new rule, not a diff
    assert out.startswith(REAL_HEADER) if hidden | tracked else out == ""
    assert git(repo, "ls-files", "-s") == index                    # nothing untracked


# --- A2, dry run: a labelled estimate ------------------------------------------------------------

@pytest.mark.parametrize("case", list(CASES))
def test_the_dry_run_estimate_lists_what_the_real_run_reports(tmp_path: Path, capsys, case: str) -> None:
    setup, prefix, hidden, tracked = CASES[case]
    repo = repo_with_prompts(tmp_path, untracked=0)
    setup(repo)
    apply_and_report(repo, prefix, [], dry_run=True)
    dry = capsys.readouterr().out
    apply_and_report(repo, prefix, [])
    real = capsys.readouterr().out
    assert (listed(dry, HIDDEN_NOTE), listed(dry, TRACKED_NOTE)) == (hidden, tracked)
    assert dry.startswith(ESTIMATE_HEADER) if hidden | tracked else dry == ""
    assert dry.splitlines()[1:] == real.splitlines()[1:]


def test_the_dry_run_is_labelled_an_estimate_and_gets_the_self_ignored_nested_case_right(
        tmp_path: Path, capsys) -> None:
    repo = repo_with_prompts(tmp_path, untracked=0)
    _case_self_ignored_nested(repo)
    apply_and_report(repo, "", [], dry_run=True)
    dry = capsys.readouterr().out
    assert dry.splitlines()[0] == ESTIMATE_HEADER
    assert listed(dry, HIDDEN_NOTE) == {"work/prompt-hide.md"}
    assert listed(dry, TRACKED_NOTE) == {"work/prompt-a.md"}
    assert not (repo / GITIGNORE).exists()
    apply_and_report(repo, "", [])
    real = capsys.readouterr().out
    assert dry.splitlines()[1:] == real.splitlines()[1:]          # same paths, rules and notes as observed


# --- A2: the note never stops the writes ---------------------------------------------------------

@pytest.mark.parametrize("dry_run", [True, False])
def test_a_failed_git_capture_skips_the_note_and_the_writes_still_happen(tmp_path: Path, capsys, dry_run: bool) -> None:
    (tmp_path / ".git").write_text("gitdir: missing-git-dir\n", encoding="utf-8")   # a broken worktree link
    written: list[str] = []
    apply_and_report(tmp_path, "", written, dry_run=dry_run)
    out = capsys.readouterr().out.splitlines()
    assert sorted(written) == [".cursorindexingignore (created)", ".gitignore (created)"]
    assert len(out) == 1 and out[0].startswith("ignore check skipped: git ls-files: ")
    assert (tmp_path / GITIGNORE).is_file() is not dry_run


def test_an_unreadable_nested_gitignore_skips_the_estimate(tmp_path: Path, capsys) -> None:
    import os
    if os.geteuid() == 0:
        pytest.skip("root reads any file")
    repo = repo_with_prompts(tmp_path)
    nested = repo / "work" / ".gitignore"
    nested.write_text("x\n", encoding="utf-8")
    nested.chmod(0)
    try:
        apply_and_report(repo, "", [], dry_run=True)
    finally:
        nested.chmod(0o644)
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 and out[0].startswith("ignore check skipped: ") and "Permission denied" in out[0]
