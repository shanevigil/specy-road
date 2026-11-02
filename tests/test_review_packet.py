"""Tests for specy-road review-packet."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, diverge, git, make_review_repo

from specy_road.bundled_scripts import review_packet as rp
from specy_road.review_files import PACKET_NAME, reviews_dir


def test_packet_names_commit_base_and_acceptance(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    base = git(repo, "rev-parse", "dev")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert f"**Commit under review:** `{head}` (`feature/rm-thing`)" in text
    assert f"**Base:** `{base}`" in text
    assert "- **A1:** a.py exists" in text
    assert "+print('a')" in text


def test_packet_flags_paths_outside_touch_zones(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    reg = repo / "roadmap" / "registry.yaml"   # mark-implementation-reviewed's approval, then more work
    commit_file(repo, "roadmap/registry.yaml", reg.read_text().replace("pending", "approved"), "approve")
    commit_file(repo, "src/a.py", "print('b')\n", "more")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `src/a.py`\n" in text
    assert "- `docs/x.md`  **← outside touch zones**" in text
    assert "1 path(s) outside the touch zones" in text
    assert f"- `roadmap/registry.yaml`{rp.BOOKKEEPING_MARK}\n" in text
    assert rp.BOOKKEEPING_NOTE in text and "+  implementation_review: approved" in text   # shown, labelled


def test_packet_reviews_branch_tip_without_switching(tmp_path: Path) -> None:
    """A coordinator on dev still gets the feature branch's diff."""
    repo = make_review_repo(tmp_path)
    tip = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "dev")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert f"`{tip}` (`feature/rm-thing`)" in text
    assert git(repo, "branch", "--show-current") == "dev"


def test_packet_includes_summary_ready_verify_and_run_commands(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / "READY-exec.md").write_text(
        "---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\n"
        f"commit: {head}\nbase: {git(repo, 'rev-parse', 'dev')}\n"
        "changed_paths: [src/a.py]\nverify:\n  - {cmd: pytest, exit: 0, tail: '9 passed'}\n---\n"
    )
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=["echo checked"])
    assert "Did it." in text
    assert "### `pytest` → exit 0" in text and "9 passed" in text
    assert "### `echo checked` → exit 0 (run by review-packet)" in text
    assert "not the commit under review" not in text


def test_packet_header_names_policy_source_and_generation(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert f"- **Policy source:** `refs/heads/dev` @ `{git(repo, 'rev-parse', 'dev')}`" in text
    assert f"by review-packet at HEAD `{head}`" in text and "- **Generated:** " in text


def test_packet_policy_source_error_is_printed(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "branch", "-m", "dev", "gone")
    text = rp.build_packet(repo, "M1.1", ref="feature/rm-thing", verify_cmds=[])
    assert "- **Policy source:** _integration branch 'dev'" in text and "fails closed" in text


def test_each_section_states_its_provenance(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("Did it.\n")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / "READY-exec.md").write_text(
        f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\ncommit: {head}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\nverify: [{{cmd: pytest, exit: 0}}]\n---\n"
    )
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=["echo hi"])
    assert text.count(rp.RENDERED) == 1
    assert text.count(rp.ASSERTED) == 1           # READY tails; the summary is not committed here
    assert text.count(rp.ASSERTED_WORKING_TREE) == 1
    assert text.count("_Computed by review-packet from git (`") == 4   # changed paths, integrity, tests at risk, diff
    assert text.count(f"_Run now by review-packet at HEAD `{head}`._") == 1
    assert f"## Implementation summary\n\n{rp.ASSERTED_WORKING_TREE}\n\nDid it." in text


def test_packet_test_integrity_section_is_stable_and_lists_findings(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "tests/test_leaf.py", "def test_ok():\n    assert 1\n", "baseline test")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "dev", "--no-edit")
    text_a = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    text_b = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    start = "## Test integrity\n"
    sec_a = text_a.split(start, 1)[1].split("\n## Diff\n", 1)[0]
    sec_b = text_b.split(start, 1)[1].split("\n## Diff\n", 1)[0]
    assert sec_a == sec_b
    assert "_none_" in sec_a
    commit_file(repo, "tests/test_leaf.py", "def test_ok():\n    pass\n", "weaken")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    block = text.split(start, 1)[1].split("\n## Diff\n", 1)[0]
    assert "assert-loss: tests/test_leaf.py::test_ok 1->0" in block
    capped = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=1)   # a capped diff keeps it
    assert capped.split(start, 1)[1].split("\n## Diff\n", 1)[0] == block and "**Diff capped at 1 lines**" in capped


def test_main_writes_packet_file(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    rp.main(["M1.1", "--repo-root", str(repo)])
    out = reviews_dir(repo, "M1.1") / PACKET_NAME
    assert out.is_file()
    assert str(out) in capsys.readouterr().out
    # -o adds a copy; the canonical path `prompt --role reviewer` reads is still written
    out.unlink()
    extra = tmp_path / "elsewhere.md"
    rp.main(["M1.1", "-o", str(extra), "--repo-root", str(repo)])
    assert out.read_text() == extra.read_text() and "+print('a')" in extra.read_text()
    printed = capsys.readouterr().out
    assert f"Wrote {out}" in printed and f"Wrote {extra}" in printed


@pytest.mark.parametrize(("case", "line"), [
    ("clean", "- **Trial merge:** `refs/heads/dev` is 1 commit(s) ahead; merges cleanly\n"),
    ("bookkeeping", "conflicts on bookkeeping only (`planning/M1.1_thing_"),
    ("code", "- **Trial merge:** `refs/heads/dev` is 1 commit(s) ahead; **conflicts on `src/a.py`**\n"),
])
def test_packet_reports_trial_merge_with_integration_branch(tmp_path: Path, case: str, line: str) -> None:
    repo = make_review_repo(tmp_path)
    assert "- **Trial merge:** up to date with `refs/heads/dev`" in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    diverge(repo, case)
    tip = git(repo, "rev-parse", "feature/rm-thing")
    for base in (None, tip):   # --base moves the diff range only; the trial merge stays on the integration branch
        text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], base=base)
        assert line in text
        assert ("**Stop: refs/heads/dev is 1 commit(s) ahead and a trial merge conflicts on src/a.py: "
                "merge it into this branch and resolve before review.**" in text) == (case == "code")


def test_an_empty_merge_base_diff_is_explained_and_base_sets_the_range(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    before = git(repo, "rev-parse", "dev")
    git(repo, "update-ref", "refs/heads/dev", "feature/rm-thing")   # the leaf is already merged
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "_(the diff is empty: `" in text and "`review-packet --base <ref>` sets the diff range" in text
    assert "warning: the diff is empty" in capsys.readouterr().err
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], base=before)
    assert f"**Base:** `{before}` (merge base with `{before}`)" in text and "+print('a')" in text
    assert "warning:" not in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], base="no-such-ref")
    assert e.value.code == 1 and "--base 'no-such-ref' does not resolve" in capsys.readouterr().err


def test_diff_past_the_cap_keeps_first_files_whole_lists_the_rest_and_writes_the_patch(tmp_path: Path) -> None:
    """A1: whole files up to --max-diff-lines, +/- counts for the rest, DIFF.patch named."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, "src/big.py", "".join(f"x{i} = {i}\n" for i in range(300)), "big")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=40)
    patch = reviews_dir(repo, "M1.1") / rp.DIFF_NAME
    assert "**Diff capped at 40 lines**" in text and f"the full diff is at `{patch}`" in text
    assert "- `src/big.py` (+300 -0) — not inlined" in text
    assert "+print('a')" in text and "x299 = 299" not in text   # git orders docs/x.md, src/a.py, src/big.py
    assert "x299 = 299" in patch.read_text() and "+print('a')" in patch.read_text()


def test_max_diff_lines_zero_means_no_cap_and_no_patch(tmp_path: Path) -> None:
    """A1: 0 inlines everything and removes a DIFF.patch left by an earlier capped run."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, "src/big.py", "".join(f"x{i} = {i}\n" for i in range(2000)), "big")
    patch = reviews_dir(repo, "M1.1") / rp.DIFF_NAME
    rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=1)
    assert patch.is_file()
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=0)
    assert all(s in text for s in ("+print('a')", "x0 = 0", "x1999 = 1999")) and "Diff capped" not in text
    assert rp.DIFF_NAME not in text and not patch.exists()


def test_a_packet_under_the_cap_is_byte_identical_to_an_uncapped_one(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[]) == \
        rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=0)
    assert not (reviews_dir(repo, "M1.1") / rp.DIFF_NAME).exists()


def test_main_passes_max_diff_lines_through(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    rp.main(["M1.1", "--max-diff-lines", "1", "--repo-root", str(repo)])
    text = (reviews_dir(repo, "M1.1") / PACKET_NAME).read_text()
    assert "**Diff capped at 1 lines**" in text and "the first 0 of 2 changed file(s)" in text
    assert "- `docs/x.md` (+1 -0) — not inlined" in text and "- `src/a.py` (+1 -0) — not inlined" in text
    assert (reviews_dir(repo, "M1.1") / rp.DIFF_NAME).is_file()
