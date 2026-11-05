"""M15.17: review friction — delegate builds a missing packet, the packet skips ignored evidence and numbers
suppressions at the commit, refusals quote the line, and superseded failed runs say so."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.integrity import compare_integrity
from specy_road.review_delegate import load_run
from specy_road.review_files import PACKET_NAME, review_path, reviews_dir
from specy_road.review_record_rules import approve_defect_problem, clause_problem


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _delegate(repo: Path) -> int:
    return _run("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--retries", "0",
                "--repo-root", str(repo))


# A1 — delegate builds a missing or other-commit packet


def test_delegate_builds_the_packet_when_none_exists(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    packet = reviews_dir(repo, "M1.1") / PACKET_NAME
    packet.unlink()
    set_steps(repo, spec, verdict_step(repo))
    assert _delegate(repo) == 0
    head = git(repo, "rev-parse", "HEAD")
    assert f"**Commit under review:** `{head}`" in packet.read_text()
    err = capsys.readouterr().err
    assert f"review packet is missing: built {packet} ({packet.stat().st_size} bytes) for {head[:12]}" in err
    assert load_run(repo, "M1.1", "opus")["state"] == "complete"


def test_delegate_rebuilds_a_packet_built_for_another_commit(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    packet = reviews_dir(repo, "M1.1") / PACKET_NAME
    old = git(repo, "rev-parse", "HEAD~1")
    packet.write_text(f"# Review packet\n\n- **Commit under review:** `{old}` (`x`)\n")
    set_steps(repo, spec, verdict_step(repo))
    assert _delegate(repo) == 0
    head = git(repo, "rev-parse", "HEAD")
    assert f"**Commit under review:** `{head}`" in packet.read_text()
    assert f"review packet was built for {old[:12]}, not {head[:12]}: built {packet}" in capsys.readouterr().err


def test_delegate_keeps_a_packet_for_the_commit_under_review(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    packet = reviews_dir(repo, "M1.1") / PACKET_NAME
    text = f"# Review packet\n\n- **Commit under review:** `{git(repo, 'rev-parse', 'HEAD')}` (`x`)\n"
    packet.write_text(text)
    set_steps(repo, spec, verdict_step(repo))
    assert _delegate(repo) == 0
    assert packet.read_text() == text and "review packet" not in capsys.readouterr().err


# A2 — ignored paths and globs that match nothing are not warned about


def _cite(repo: Path, text: str) -> None:
    sheet = repo / NODE["planning_dir"]
    commit_file(repo, NODE["planning_dir"], sheet.read_text() + f"\n{text}\n", "cite")


def test_packet_does_not_warn_about_an_ignored_build_path(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    commit_file(repo, ".gitignore", (repo / ".gitignore").read_text() + "build/\n", "ignore build")
    (repo / "build").mkdir()
    (repo / "build" / "out.js").write_text("x\n")
    # every glob form counts: *, ?, [...], a glob extension, and a top-level glob with no directory
    # patterns are packet text: "**x" (which Path.glob refuses) and a lone "[" are matched, never raised on
    globs = ["planning/M9_*.md", "planning/M9_?.md", "planning/M9_[ab].md", "planning/M9.m?", "NOTES?.md",
             "planning/**draft.md", "planning/M9_[.md"]
    _cite(repo, "The bundle lands in `build/out.js` and the sheets match "
                + ", ".join(f"`{g}`" for g in globs) + "; also `shared/missing.md`.")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    err = capsys.readouterr().err
    assert "build/out.js" not in err and not any(g in err for g in globs)
    block = text.split("## Uncommitted references\n", 1)[1].split("\n## Changed paths\n", 1)[0]
    assert "- `shared/missing.md`" in block and "build/out.js" not in block and "planning/M9" not in block
    assert "NOTES" not in block
    assert "warning: `shared/missing.md` is named in the packet but not at commit" in err   # no wildcard: warned
    assert err.count(f"note: {1 + len(globs)} path(s) named in the packet but not at commit") == 1


def test_a_glob_that_matches_a_committed_file_is_not_missing(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    _cite(repo, "Sheets: `planning/M1*.md`.")
    rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    err = capsys.readouterr().err
    assert "planning/M1*.md" not in err and "note:" not in err


# A3 — suppression line numbers are the lines at the commit under review


def test_suppression_line_numbers_are_those_at_the_commit(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    base = commit_file(repo, "src/m.py", "".join(f"v{i} = {i}\n" for i in range(1, 21)), "base")
    lines = [f"v{i} = {i}\n" for i in range(1, 21)]
    del lines[2:5]                                        # unrelated edits first: three lines gone ...
    lines[0:0] = ["import os\n", "import sys\n"]          # ... two added at the top
    commit_file(repo, "src/m.py", "".join(lines), "unrelated edits")
    lines[9] = lines[9].rstrip("\n") + "  # noqa: E501\n"   # then a suppression on an existing line
    lines.append("x = os  # type: ignore\n")             # and one on a new last line
    commit_file(repo, "src/m.py", "".join(lines), "suppressions")
    git(repo, "mv", "src/m.py", "src/n.py")               # renamed: the numbers are the new file's
    git(repo, "commit", "-qm", "rename")
    at_commit = git(repo, "show", "HEAD:src/n.py").splitlines()
    want = {str(n) for n, line in enumerate(at_commit, 1) if "noqa" in line or "type: ignore" in line}
    assert want == {"10", str(len(at_commit))}
    got = {f.detail for f in compare_integrity(repo, base, "HEAD") if f.kind == "new-suppression"}
    assert got == want


# A4 — the refusal quotes each offending line and states the rule in one sentence


def _record(repo: Path, notes: str) -> int:
    p = repo.parent / "notes-opus.md"
    p.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus").replace("---\nnotes\n", "---\n" + notes))
    return _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve", "--file", str(p),
                "--repo-root", str(repo))


ONE_AI = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
          "  - {id: opus, family: anthropic, roles: [reviewer]}\n")


def test_refusal_quotes_a_two_clause_line_and_the_rule(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    line = "The cache is cold and the lock leaks, not a defect because both are expected."
    assert _record(repo, f"## Acceptance\n\n- **A1:** pass\n\n{line}\n") == 1
    err = capsys.readouterr().err
    assert "verdict: approve refused: each line below has no required_changes entry and no 'not a defect because'" \
           " line" in err
    assert (f'notes line 5 says "leaks", two observations joined by "and": "The cache is cold" and '
            f'"the lock leaks": {line}') in err
    assert not review_path(repo, "M1.1", "opus").exists()


def test_refusal_quotes_a_line_with_no_marker(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, "## Acceptance\n\n- **A1:** pass\n\nRe-ran the record tests.\n") == 1
    err = capsys.readouterr().err
    assert "  notes line 5 is an observation: Re-ran the record tests." in err
    assert "say on it why it is not a defect ('not a defect because <reason>'" in err


def test_refusal_text_has_the_rule_once_then_one_line_per_offence() -> None:
    why = approve_defect_problem({"verdict": "approve", "findings": {"correctness": ["Minor: x"]}},
                                 "Line one is here.\nok\nLine three is here.\n")
    rule, *rest = why.split("\n")
    assert rule.count(".") == 1 and rule.endswith("and block.")
    assert rest == ['  findings.correctness[0] says "Minor": Minor: x',
                    "  notes line 1 is an observation: Line one is here.",
                    "  notes line 3 is an observation: Line three is here."]


# A6 — the joining word and both parts are named; quoted spans are not split


@pytest.mark.parametrize("line", [
    'The packet compares "base and HEAD" of the leaf branch, not a defect because that is the brief\'s range.',
    "The packet compares 'base and HEAD' of the leaf branch, not a defect because that is the brief's range.",
    "The packet compares `base and HEAD` of the leaf branch, not a defect because that is the brief's range.",
    "The diff is empty; not a defect because base and HEAD are the same commit.",
])
def test_a_conjunction_inside_quotes_is_not_a_split_point(line: str) -> None:
    assert clause_problem(line) is None


def test_the_reported_shape_is_refused_with_the_word_and_both_parts() -> None:
    line = "The packet compares base and HEAD of the leaf branch crashes, not a defect because that is the brief's range."
    assert clause_problem(line) == ('says "crashes", two observations joined by "and": "The packet compares '
                                    'base" and "HEAD of the leaf branch crashes"')


# A5 — a failed run superseded by a record filed later at the same commit


def test_a_failed_run_is_marked_superseded_by_a_later_record(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"raw": "not a verdict"})
    assert _delegate(repo) == 1
    assert load_run(repo, "M1.1", "opus")["state"] == "incomplete"
    capsys.readouterr()
    _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    before = json.loads(capsys.readouterr().out)["nodes"][0]
    assert any("delegated review of this commit is incomplete" in p for p in before["problems"])
    notes = repo.parent / "notes-opus.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve", "--file", str(notes),
                "--repo-root", str(repo)) == 0
    capsys.readouterr()
    assert _run("review", "list", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "RUN-opus.json: incomplete run by opus" in out
    assert "— superseded: REVIEW-opus.md was filed later at this commit" in out
    _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert st["review_runs"][0]["superseded"] == "REVIEW-opus.md"
    assert not any("delegated review of this commit is incomplete" in p for p in st["problems"])
    assert "reviewer failure" not in st["policy"]
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    assert "— superseded: REVIEW-opus.md was filed later at this commit" in capsys.readouterr().out


def test_a_record_filed_before_the_failed_run_does_not_supersede_it(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    path = review_path(repo, "M1.1", "opus")
    path.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    import os
    os.utime(path, (1_000_000_000, 1_000_000_000))       # filed long before the run
    set_steps(repo, spec, {"raw": "not a verdict"})
    _delegate(repo)
    capsys.readouterr()
    _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert st["review_runs"][0]["superseded"] is None


# A4/A6 on refusals reviewers really hit after M8.3 (from RUN-*.log final answers, 2026-11-05): each is still refused,
# and the refusal names its trigger and quotes the line.

_REAL = [
    # M14.1 cursor-grok-4.6-high, findings.boundary[0]: joined by "plus"
    ({"boundary": ["Changed paths are the touch zones plus sr/work/implementation-summary-M14.1.md, not a defect "
                   "because that summary is the leaf hand-off."]}, "",
     'findings.boundary[0] is a finding, two observations joined by "plus": "Changed paths are the touch zones" plus '
     '"sr/work/implementation-summary-M14.1.md": Changed paths are the touch zones plus '
     'sr/work/implementation-summary-M14.1.md, not a defect because that summary is the leaf hand-off.'),
    # M14.1 grok-4.7-low, findings.boundary[0]
    ({"boundary": ["The diff stays inside the listed touch zones plus the required implementation summary not a "
                   "defect because no other product module is edited."]}, "",
     'findings.boundary[0] is a finding, two observations joined by "plus": "The diff stays inside the listed touch '
     'zones" plus "the required implementation summary": The diff stays inside'),
    # M13.12 grok-4.7-low, findings.test_integrity[0]: the reason names a defect word
    ({"test_integrity": ["The packet's test-integrity section lists no removals not a defect because no test was "
                         "dropped."]}, "",
     'findings.test_integrity[0] says "was dropped" in its reason: The packet\'s test-integrity section lists no '
     'removals not a defect because no test was dropped.'),
    # M12.5 grok-4.7-low, notes line 3: joined by "and", which names no defect, so one observation (M15.37)
    ({}, "## Acceptance\nA1: pass.\nA2: pass. Refusals print one reason line and leave the worktree in place not a "
         "defect because `test_cleanup_refuses_and_removes_nothing` covers unmerged files.\n",
     None),
]


@pytest.mark.parametrize("findings, notes, want", _REAL)
def test_a_real_refusal_names_its_trigger_and_quotes_the_line(findings: dict, notes: str, want: str | None) -> None:
    why = approve_defect_problem({"verdict": "approve", "findings": findings}, notes)
    if want is None:   # a line the M15.37 rule accepts
        assert why is None
        return
    assert why is not None and why.startswith("verdict: approve refused: each line below has no required_changes")
    assert f"\n  {want}" in why
