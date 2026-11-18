"""The IDE-indexing policy: what is hidden from the index, and what is not."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.agent_ignores import (
    CURSOR_INDEXING_IGNORE,
    GITIGNORE,
    INDEXING_IGNORE_LINES,
    apply_agent_ignores,
)
from specy_road.managed_block import CREATED, UNCHANGED
import shlex
from specy_road.agent_ignores import MATCH_LIMIT, apply_and_report
from specy_road.ignore_report import UNTRACK_HINT, UNTRACK_LABEL
from tests.support.extracted.agent_ignores import git, write
from specy_road.ignore_report import ESTIMATE_HEADER, HIDDEN_NOTE, REAL_HEADER, TRACKED_NOTE
from specy_road.managed_block import MARKER_END, MARKER_START
from tests.support.extracted.agent_ignores import listed, repo_with_prompts, shown
from specy_road.validate_roadmap_runner import notice_repeated_ignore_patterns
from specy_road.runtime_paths import project_template_root


def test_it_writes_the_cursor_indexing_ignore_not_the_hard_one(tmp_path: Path) -> None:
    """.cursorignore would block reading and break every path search returns."""
    apply_agent_ignores(tmp_path)

    assert (tmp_path / CURSOR_INDEXING_IGNORE).is_file()
    assert not (tmp_path / ".cursorignore").exists()


def test_it_never_writes_claude_code_read_denials(tmp_path: Path) -> None:
    """Claude Code builds no index, and deny rules would break pointer-following."""
    apply_agent_ignores(tmp_path)

    settings = tmp_path / ".claude" / "settings.json"
    assert not settings.exists()


def test_the_archived_and_duplicated_corpus_is_excluded(tmp_path: Path) -> None:
    apply_agent_ignores(tmp_path)
    text = (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8")

    assert "roadmap/archive/" in text
    assert "work/brief-*.md" in text


def test_unique_prose_stays_indexed(tmp_path: Path) -> None:
    """Implementation summaries are the one non-duplicated record in work/."""
    assert not any("implementation-summary" in ln for ln in INDEXING_IGNORE_LINES)


def test_the_ignore_file_says_how_to_reach_what_it_hides(tmp_path: Path) -> None:
    apply_agent_ignores(tmp_path)
    text = (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8")

    assert "specy-road search" in text
    assert "roadmap-context.md" in text


def test_the_derived_caches_are_gitignored(tmp_path: Path) -> None:
    """Fixes an upgrade gap: init project skips a .gitignore that already exists."""
    (tmp_path / GITIGNORE).write_text("node_modules/\n", encoding="utf-8")

    apply_agent_ignores(tmp_path)
    text = (tmp_path / GITIGNORE).read_text(encoding="utf-8")

    assert ".specyrd/cache/" in text
    assert "node_modules/" in text


def test_git_actually_ignores_the_caches_afterwards(tmp_path: Path) -> None:
    """The rule is only worth writing if git honours it."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    apply_agent_ignores(tmp_path)
    cache = tmp_path / ".specyrd" / "cache"
    cache.mkdir(parents=True)
    (cache / "roadmap-history.json").write_text("{}", encoding="utf-8")

    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert ".specyrd/cache" not in porcelain
    assert ".specyrd/manifest.json" not in porcelain  # not created, but never ignored


def test_applying_twice_reports_unchanged(tmp_path: Path) -> None:
    first = apply_agent_ignores(tmp_path)
    second = apply_agent_ignores(tmp_path)

    assert first[CURSOR_INDEXING_IGNORE] == CREATED
    assert all(outcome == UNCHANGED for outcome in second.values())


# --- nested layout ----------------------------------------------------------


def test_nested_layout_prefixes_every_entry(tmp_path: Path) -> None:
    """The shipped breakage: entries are project-relative, the file is not.

    Both ignore files land at the git root. Under a nested layout an unprefixed
    ``roadmap/archive/`` matches nothing there, so archived material stayed in
    the IDE index while appearing to be excluded.
    """
    apply_agent_ignores(tmp_path, "sr/")
    text = (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8")

    assert "sr/roadmap/archive/" in text
    assert "sr/work/brief-*.md" in text
    assert "sr/roadmap.md" in text
    assert "\nroadmap/archive/" not in text  # never the unprefixed form


def test_nested_layout_prefixes_the_gitignore_block_too(tmp_path: Path) -> None:
    apply_agent_ignores(tmp_path, "sr/")
    text = (tmp_path / GITIGNORE).read_text(encoding="utf-8")

    assert "sr/.specyrd/cache/" in text
    assert "sr/roadmap/orchestration.local.yaml" in text


@pytest.mark.parametrize("prefix", ["", "sr/"])
def test_orchestration_local_overlay_is_gitignored(tmp_path: Path, prefix: str) -> None:
    """Per-checkout availability overlay must not be committable (flat or nested)."""
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True, capture_output=True)
    apply_agent_ignores(tmp_path, prefix)
    overlay = tmp_path / prefix / "roadmap" / "orchestration.local.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text("roster: []\n", encoding="utf-8")
    rel = f"{prefix}roadmap/orchestration.local.yaml"
    assert subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "-q", rel],
        check=False,
    ).returncode == 0


def test_embedded_layout_is_byte_identical_to_before(tmp_path: Path) -> None:
    """An empty prefix must change nothing for the overwhelmingly common case."""
    other = tmp_path / "other"
    other.mkdir()
    apply_agent_ignores(tmp_path)
    apply_agent_ignores(other, "")

    assert (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8") == (
        other / CURSOR_INDEXING_IGNORE
    ).read_text(encoding="utf-8")


def test_a_prefixed_block_actually_matches_in_git(tmp_path: Path) -> None:
    """End-to-end: git must agree the nested archive path is ignored."""
    subprocess.run(
        ["git", "-C", str(tmp_path), "init", "-q", "-b", "main"],
        check=True,
        capture_output=True,
    )
    (tmp_path / "sr" / "roadmap" / "archive").mkdir(parents=True)
    apply_agent_ignores(tmp_path, "sr/")
    # .cursorindexingignore is not a git file, so assert through the gitignore
    # block, which uses the same prefixing path.
    (tmp_path / "sr" / ".specyrd" / "cache").mkdir(parents=True)
    (tmp_path / "sr" / ".specyrd" / "cache" / "x.json").write_text("{}")

    proc = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "sr/.specyrd/cache/x.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, "nested cache path should be gitignored"


@pytest.mark.parametrize("prefix", ["", "sr/"])
def test_all_of_work_is_ignored_but_the_scaffold_and_re_includes(tmp_path: Path, prefix: str) -> None:
    """``work/*``: run files and child directories are ignored; the scaffold and a user re-include are not."""
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True, capture_output=True)
    apply_agent_ignores(tmp_path, prefix)

    def ignored(rel: str) -> bool:
        path = tmp_path / prefix / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        return subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", prefix + rel],
                              check=False).returncode == 0

    assert ignored("work/.workers/w-0001.events.jsonl")
    assert ignored("work/.worktrees/thing/README.md")
    assert ignored("work/chores/tidy.json") and ignored("work/chores/tidy.md")
    assert ignored("work/brief-M1.1.md") and ignored("work/implementation-summary-M1.1.md")
    assert ignored("work/done/implementation-summary-M1.1.md")
    assert ignored("work/worker-logs/M1.1/w-0001.events.jsonl")
    for scaffold in ("work/README.md", "work/.gitkeep", "work/review-record.template.md",
                     "work/handoff-ready.template.md", "work/implementation-summary.template.md"):
        assert not ignored(scaffold), scaffold
    with (tmp_path / GITIGNORE).open("a", encoding="utf-8") as fh:
        fh.write(f"!{prefix}work/worker-logs/\n")   # a project's re-include after the block
    assert not ignored("work/worker-logs/M1.1/w-0001.events.jsonl")


ODD = ["work/prompt-a b.md", "work/prompt-it's.md", 'work/prompt-"q".md', "work/prompt-(x).md", "work/prompt-$HOME;.md"]



def tracked_prompts(repo: Path, names: list[str]) -> Path:
    git(repo, "init", "-q")
    for rel in names:
        write(repo, rel)
    git(repo, "add", "--", *names)
    git(repo, "commit", "-qm", "tracked prompts")
    return repo



def commands(out: list[str]) -> list[list[str]]:
    """Each printed command line (four-space indent) parsed as a shell would."""
    return [shlex.split(ln) for ln in out if ln.startswith("    ")]


# Every command the ignore note prints is a line of its own that a shell parses
# back to its argv. Paths with spaces, quotes and parentheses are quoted; when
# more tracked files match than the note lists, the overflow note is its own
# line, never part of the command.


def test_odd_paths_round_trip_through_the_shell(tmp_path: Path, capsys) -> None:
    repo = tracked_prompts(tmp_path, ODD)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert commands(out) == [["git", "rm", "--cached", "--", *sorted(ODD)]]
    assert out[-3] == UNTRACK_LABEL and out[-1] == UNTRACK_HINT



def test_more_tracked_matches_than_listed_put_the_overflow_on_its_own_line(tmp_path: Path, capsys) -> None:
    names = [f"work/prompt-{i:02d} (copy).md" for i in range(MATCH_LIMIT + 1)]
    repo = tracked_prompts(tmp_path, names)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert commands(out) == [
        ["git", "rm", "--cached", "--", *sorted(names)[:MATCH_LIMIT]],
        ["git", "ls-files", "-ci", "--exclude-standard"],
    ]
    assert "  1 more tracked file(s) match a new rule; this lists every tracked file git ignores:" in out
    assert out[-1] == UNTRACK_HINT







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



def test_a_git_dir_from_a_hook_does_not_point_the_scratch_repo_at_the_checkout(
        tmp_path: Path, capsys, monkeypatch) -> None:
    repo = repo_with_prompts(tmp_path)
    config = (repo / ".git" / "config").read_bytes()
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    apply_and_report(repo, "", [], dry_run=True)
    assert "  work/prompt-u00.md (work/*): untracked; now hidden from git status" in (
        capsys.readouterr().out.splitlines())
    assert (repo / ".git" / "config").read_bytes() == config



# Notices that were correct but misleading.
# A symlinked skills directory listed every skill twice; a new .gitignore
# rule silently matched files already in the tree. (The session end wording
# is pinned in test_session_presence.py.)

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
    _commit(repo, "notes/old.md")                               # outside work/: no block rule reaches it
    write(repo, GITIGNORE, "notes/old.md\n")



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
    # A pathspec `work/*.template.md` matches across `/`; the block's re-include does not, so this stays hidden.
    "r1 pathspec-only match": (lambda r: write(r, "work/sub/x.template.md"), "", {"work/sub/x.template.md"},
                               {"work/prompt-a.md"}),
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
    # The committed nested file is itself under work/*, so it is now a tracked match too.
    "r7 nested rule decides": (_case_nested_rule_decides, "", set(), {"work/prompt-a.md", "work/.gitignore"}),
    "r7 tracked negated after the block": (_case_tracked_negated_after_the_block, "", set(), set()),
    "r7 tracked negated in a nested file": (_case_tracked_negated_in_a_nested_file, "", {"work/.gitignore"}, set()),
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


MANIFEST_NOTE = "`.specyrd/manifest.json`, when present, stays tracked."



# Validate notices stay short and true. The managed .gitignore comment is true
# without a manifest; a tracked file under a new ignore rule gets the
# git rm --cached command; repeated .gitignore patterns get one notice.

# --- A2: the managed .gitignore comment is true without a manifest -------------------------------

def test_the_gitignore_comment_is_true_in_a_repo_with_no_stub_pack(tmp_path: Path) -> None:
    assert not (tmp_path / ".specyrd").exists()
    apply_agent_ignores(tmp_path)
    text = (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    assert MANIFEST_NOTE in text
    assert "manifest.json` stays tracked" not in text
    template = (project_template_root() / ".gitignore").read_text(encoding="utf-8")
    assert ".specyrd/manifest.json, when present, stays tracked." in template



# --- A3: a tracked match gets the command to untrack it ------------------------------------------

def test_a_tracked_match_prints_the_untrack_command_and_when_to_keep_tracking(tmp_path: Path, capsys) -> None:
    repo = repo_with_prompts(tmp_path, untracked=0)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert out[-3:] == [
        "  to stop tracking them, run from the git root (specy-road never runs it):",
        "    git rm --cached -- work/prompt-a.md",
        "  keep tracking a file meant to be shared (the rule only hides new files); "
        "untrack one that is session scratch",
    ]
    assert out[-1] == UNTRACK_HINT



# --- A4: managed patterns repeated above the markers ---------------------------------------------

def _gitignore(root: Path, above: str) -> None:
    apply_agent_ignores(root)
    path = root / GITIGNORE
    path.write_text(above + path.read_text(encoding="utf-8"), encoding="utf-8")



def test_two_repeated_patterns_get_one_notice(tmp_path: Path, capsys) -> None:
    _gitignore(tmp_path, "node_modules/\n.specyrd/cache/\n# work/prompt-*.md\nwork/*\n.specyrd/cache/\n")
    before = (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    notice_repeated_ignore_patterns(tmp_path)
    assert capsys.readouterr().out == (
        "gitignore: notice — .gitignore lists 2 pattern(s) above the specy-road managed block that the "
        "block repeats: .specyrd/cache/, work/*. They can be removed from above the markers "
        "(validate never edits the file).\n"
    )
    assert (tmp_path / GITIGNORE).read_text(encoding="utf-8") == before



def test_no_repeats_print_nothing(tmp_path: Path, capsys) -> None:
    _gitignore(tmp_path, "node_modules/\n")
    (tmp_path / GITIGNORE).write_text(
        (tmp_path / GITIGNORE).read_text(encoding="utf-8") + "work/*\n", encoding="utf-8")   # below: fine
    notice_repeated_ignore_patterns(tmp_path)
    assert MARKER_START in (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    assert MARKER_END in (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""



def test_patterns_git_reads_differently_are_not_repeats(tmp_path: Path, capsys) -> None:
    """A leading space, an escaped trailing space, ``\\!`` and ``\\#`` are part of the pattern to git."""
    _gitignore(tmp_path, " .specyrd/cache/\nwork/*\\ \n\\!work/prompt-*.md\n\\#work/.sessions/\n")
    (tmp_path / GITIGNORE).write_text(
        (tmp_path / GITIGNORE).read_text(encoding="utf-8").replace(
            MARKER_END, "!work/prompt-*.md\n#work/.sessions/\n" + MARKER_END), encoding="utf-8")
    notice_repeated_ignore_patterns(tmp_path)
    assert capsys.readouterr().out == ""



def test_trailing_unescaped_spaces_and_a_crlf_are_what_git_drops(tmp_path: Path, capsys) -> None:
    _gitignore(tmp_path, "work/*   \r\n")
    notice_repeated_ignore_patterns(tmp_path)
    assert "block repeats: work/*. They can be removed" in capsys.readouterr().out



# The complete rule for reading a .gitignore (validate_roadmap_runner._patterns), one row per item:
# (bytes above the block, extra lines inside the block, patterns the notice must name).
GIT_READS = {
    "utf8-bom-dropped": (b"\xef\xbb\xbfwork/*\n", "", ["work/*"]),
    "lf": (b"work/*\n", "", ["work/*"]),
    "crlf": (b"work/*\r\n", "", ["work/*"]),
    "lone-cr-does-not-split": (b"x\rwork/*\n", "", []),
    "blank-and-space-only-lines-skipped": (b"\n   \n\r\n", "", []),
    "hash-comment-skipped": (b"#x\n", "#x\n", []),
    "escaped-hash-is-a-pattern": (b"\\#x\n", "\\#x\n", ["\\#x"]),
    "trailing-unescaped-spaces-trimmed": (b"work/*   \n", "", ["work/*"]),
    "escaped-trailing-space-kept": (b"work/*\\ \n", "", []),
    "leading-space-kept": (b" work/*\n", "", []),
    "bang-and-escaped-bang-differ": (b"\\!x\n", "!x\n", []),
    "bang-repeated": (b"!x\n", "!x\n", ["!x"]),
}



@pytest.mark.parametrize("case", list(GIT_READS))
def test_the_notice_reads_gitignore_as_git_does(tmp_path: Path, capsys, case: str) -> None:
    above, inside, repeated = GIT_READS[case]
    apply_agent_ignores(tmp_path)
    path = tmp_path / GITIGNORE
    block = path.read_bytes().replace(MARKER_END.encode(), inside.encode() + MARKER_END.encode())
    path.write_bytes(above + block)
    notice_repeated_ignore_patterns(tmp_path)
    expected = (
        f"gitignore: notice — .gitignore lists {len(repeated)} pattern(s) above the specy-road managed block "
        f"that the block repeats: {', '.join(repeated)}. They can be removed from above the markers "
        "(validate never edits the file).\n"
    ) if repeated else ""
    assert capsys.readouterr().out == expected
    assert path.read_bytes() == above + block   # report only



def _case_symlinked_nested(repo: Path) -> None:
    write(repo, "elsewhere.txt", "!prompt-keep.md\n")
    (repo / "work" / GITIGNORE).symlink_to("../elsewhere.txt")   # git does not read a symlinked .gitignore
    write(repo, "work/prompt-keep.md")
    write(repo, "work/prompt-hide.md")



def _case_symlinked_top(repo: Path) -> None:
    write(repo, "real-ignore", "node_modules\n")
    (repo / GITIGNORE).symlink_to("real-ignore")                   # the update writes through it; git reads neither
    write(repo, "work/prompt-hide.md")



def _case_dangling_top(repo: Path) -> None:
    (repo / GITIGNORE).symlink_to("missing-ignore")
    write(repo, "work/prompt-hide.md")



# The dry-run estimate treats a symlinked .gitignore as git does (it does not read one).
#: name -> (setup, expected now-hidden): ``.gitignore`` symlinks the estimate must keep as symlinks.
SYMLINK_CASES = {
    # The link itself sits under work/*, so it is hidden too.
    "nested symlink": (_case_symlinked_nested, {"work/prompt-hide.md", "work/prompt-keep.md", "work/.gitignore"}),
    "top-level symlink": (_case_symlinked_top, set()),
    "dangling top-level symlink": (_case_dangling_top, set()),
}



@pytest.mark.parametrize("case", list(SYMLINK_CASES))
def test_the_dry_run_estimate_treats_a_symlinked_gitignore_as_git_does(tmp_path: Path, capsys, case: str) -> None:
    setup, hidden = SYMLINK_CASES[case]
    repo = repo_with_prompts(tmp_path, untracked=0)
    setup(repo)
    files = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    apply_and_report(repo, "", [], dry_run=True)
    dry = capsys.readouterr().out
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts} == files
    was_shown = shown(repo)
    apply_and_report(repo, "", [])
    real = capsys.readouterr().out
    assert listed(dry, HIDDEN_NOTE) == listed(real, HIDDEN_NOTE) == was_shown - shown(repo) == hidden
    assert dry.splitlines()[1:] == real.splitlines()[1:]
