"""M13.12: validate notices that are short and true.

The untracked-touch-zone notice is bounded; the managed ``.gitignore`` comment
is true without a manifest; a tracked file under a new ignore rule gets the
``git rm --cached`` command; repeated ``.gitignore`` patterns get one notice;
unchanged ``context:`` warnings fold into one line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from specy_road.agent_ignores import GITIGNORE, apply_agent_ignores, apply_and_report
from specy_road.bundled_scripts.touch_zone_tracked import LISTED_LIMIT, warn_untracked_zones
from specy_road.bundled_scripts.validate_notices import notice_repeated_ignore_patterns
from specy_road.context_notice_cache import report_context_warnings
from specy_road.ignore_report import UNTRACK_HINT
from specy_road.init_project import project_template_root
from specy_road.managed_block import MARKER_END, MARKER_START
from tests.m13_7_ignore_helpers import repo_with_prompts
from tests.test_touch_zone_tracked import UNTRACKED, zone_git_repo

MANIFEST_NOTE = "`.specyrd/manifest.json`, when present, stays tracked."


# --- A1: the untracked-zone notice is bounded ---------------------------------------------------

def _many_nodes() -> list[dict]:
    """85 leaves with a zone naming no file: 2 In Progress, 1 claimed, 2 Blocked, 80 Not Started."""
    nodes = [{"id": "M1", "type": "phase", "status": "Not Started"}]
    for i in range(85):
        status = "In Progress" if i in (40, 41) else "Blocked" if i in (50, 51) else "Not Started"
        nodes.append({"id": f"M1.{i}", "parent_id": "M1", "status": status, "touch_zones": [f"pkg/new_{i}.py"]})
    return nodes


def test_85_untracked_nodes_give_a_bounded_line_claimed_and_in_progress_first(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)
    warn_untracked_zones(_many_nodes(), tmp_path, claims=[{"node_id": "M1.60"}])
    out, err = capsys.readouterr()
    assert err == ""
    assert out == (
        f"roadmap: notice — {UNTRACKED}: M1.40 'pkg/new_40.py'; M1.41 'pkg/new_41.py'; "
        "M1.60 'pkg/new_60.py'; M1.50 'pkg/new_50.py'; M1.51 'pkg/new_51.py'; "
        "and 80 more node(s) (by status: Not Started 80); `specy-road validate --all` lists every one. "
        "Keep a zone that names a file the work will create; otherwise fix the path (specy-road edit-node "
        "<NODE_ID> --set touch_zones=<paths>) — zones are paths, directories or globs (for example "
        "'pkg/worker_ops_*.py'); a bare name prefix is read as a literal path and is not supported.\n"
    )


def test_at_most_ten_nodes_are_named_and_the_rest_counted_by_status(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)
    nodes = _many_nodes()
    for n in nodes[1:16]:
        n["status"] = "Blocked"
    warn_untracked_zones(nodes, tmp_path)
    out = capsys.readouterr().out
    assert out.count("'pkg/new_") == LISTED_LIMIT
    assert "and 75 more node(s) (by status: Blocked 9, Not Started 66);" in out
    assert len(out) < 1000


def test_validate_all_names_every_node(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)
    warn_untracked_zones(_many_nodes(), tmp_path, show_all=True)
    out = capsys.readouterr().out
    assert out.count("'pkg/new_") == 85
    assert "more node(s)" not in out


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
    _gitignore(tmp_path, "node_modules/\n.specyrd/cache/\n# work/prompt-*.md\nwork/reviews/\n.specyrd/cache/\n")
    before = (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    notice_repeated_ignore_patterns(tmp_path)
    assert capsys.readouterr().out == (
        "gitignore: notice — .gitignore lists 2 pattern(s) above the specy-road managed block that the "
        "block repeats: .specyrd/cache/, work/reviews/. They can be removed from above the markers "
        "(validate never edits the file).\n"
    )
    assert (tmp_path / GITIGNORE).read_text(encoding="utf-8") == before


def test_no_repeats_print_nothing(tmp_path: Path, capsys) -> None:
    _gitignore(tmp_path, "node_modules/\n")
    (tmp_path / GITIGNORE).write_text(
        (tmp_path / GITIGNORE).read_text(encoding="utf-8") + "work/reviews/\n", encoding="utf-8")   # below: fine
    notice_repeated_ignore_patterns(tmp_path)
    assert MARKER_START in (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    assert MARKER_END in (tmp_path / GITIGNORE).read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


# --- A5: context warnings in full only when they changed -----------------------------------------

def _warner(lines: list[str]):
    def warn(_root: Path) -> None:
        for ln in lines:
            print(ln, file=sys.stderr)
    return warn


WARNINGS = ["context: warning — CLAUDE.md is 250 lines; …", "context: warning — AGENTS.md total …"]
FOLDED = "context: 2 warnings unchanged (validate --context shows them)\n"


def test_context_warnings_first_run_unchanged_run_and_changed_run(tmp_path: Path, capsys) -> None:
    full = "".join(ln + "\n" for ln in WARNINGS)
    report_context_warnings(tmp_path, _warner(WARNINGS), cached=True)
    assert capsys.readouterr().err == full                                     # first run: in full
    report_context_warnings(tmp_path, _warner(WARNINGS), cached=True)
    assert capsys.readouterr().err == FOLDED                                   # unchanged: one line
    changed = [*WARNINGS[:1], "context: warning — AGENTS.md total more …"]
    report_context_warnings(tmp_path, _warner(changed), cached=True)
    assert capsys.readouterr().err == "".join(ln + "\n" for ln in changed)    # changed: in full again
    report_context_warnings(tmp_path, _warner(changed), cached=True)
    assert capsys.readouterr().err == FOLDED
    assert (tmp_path / ".specyrd" / "cache" / "context-warnings.sha256").is_file()


def test_upgrade_and_validate_context_always_print_in_full(tmp_path: Path, capsys) -> None:
    full = "".join(ln + "\n" for ln in WARNINGS)
    report_context_warnings(tmp_path, _warner(WARNINGS), cached=True)
    capsys.readouterr()
    for _ in range(2):
        report_context_warnings(tmp_path, _warner(WARNINGS), cached=False)
        assert capsys.readouterr().err == full


def test_no_context_warnings_print_nothing(tmp_path: Path, capsys) -> None:
    for _ in range(2):
        report_context_warnings(tmp_path, _warner([]), cached=True)
        assert capsys.readouterr().err == ""


def test_patterns_git_reads_differently_are_not_repeats(tmp_path: Path, capsys) -> None:
    """A leading space, an escaped trailing space, ``\\!`` and ``\\#`` are part of the pattern to git."""
    _gitignore(tmp_path, " .specyrd/cache/\nwork/reviews/\\ \n\\!work/prompt-*.md\n\\#work/.sessions/\n")
    (tmp_path / GITIGNORE).write_text(
        (tmp_path / GITIGNORE).read_text(encoding="utf-8").replace(
            MARKER_END, "!work/prompt-*.md\n#work/.sessions/\n" + MARKER_END), encoding="utf-8")
    notice_repeated_ignore_patterns(tmp_path)
    assert capsys.readouterr().out == ""


def test_trailing_unescaped_spaces_and_a_crlf_are_what_git_drops(tmp_path: Path, capsys) -> None:
    _gitignore(tmp_path, "work/reviews/   \r\n")
    notice_repeated_ignore_patterns(tmp_path)
    assert "block repeats: work/reviews/. They can be removed" in capsys.readouterr().out


# The complete rule for reading a .gitignore (validate_notices._patterns), one row per item:
# (bytes above the block, extra lines inside the block, patterns the notice must name).
GIT_READS = {
    "utf8-bom-dropped": (b"\xef\xbb\xbfwork/reviews/\n", "", ["work/reviews/"]),
    "lf": (b"work/reviews/\n", "", ["work/reviews/"]),
    "crlf": (b"work/reviews/\r\n", "", ["work/reviews/"]),
    "lone-cr-does-not-split": (b"x\rwork/reviews/\n", "", []),
    "blank-and-space-only-lines-skipped": (b"\n   \n\r\n", "", []),
    "hash-comment-skipped": (b"#x\n", "#x\n", []),
    "escaped-hash-is-a-pattern": (b"\\#x\n", "\\#x\n", ["\\#x"]),
    "trailing-unescaped-spaces-trimmed": (b"work/reviews/   \n", "", ["work/reviews/"]),
    "escaped-trailing-space-kept": (b"work/reviews/\\ \n", "", []),
    "leading-space-kept": (b" work/reviews/\n", "", []),
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
