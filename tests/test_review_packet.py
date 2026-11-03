"""Tests for specy-road review-packet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import (
    NODE, commit_file, diverge, git, git_root_relative, make_layout_finish_repo, make_review_repo,
)

from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts.review_packet_uncommitted_refs import UNCOMMITTED_REF_NOTE
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


def test_zones_added_to_the_node_on_the_branch_count_from_a_checkout_on_dev(tmp_path: Path) -> None:
    """A1: the node's touch_zones are read at the reviewed commit and joined to the claim row's."""
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    commit_file(repo, "roadmap/phases/M1.json", json.dumps({"nodes": [{**NODE, "touch_zones": ["src", "docs"]}]}),
                "zones")
    git(repo, "checkout", "-q", "dev")
    assert json.loads(chunk.read_text())["nodes"][0]["touch_zones"] == ["src"]   # dev has not seen the edit
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `docs/x.md`\n" in text and "outside touch zones" not in text
    assert "- **Touch zones:** `src`, `docs`" in text


def test_zones_fall_back_to_the_claim_when_the_node_is_unreadable_at_the_commit(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    commit_file(repo, "roadmap/phases/M1.json", "not json", "break the chunk")
    git(repo, "checkout", "-q", "dev")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `docs/x.md`  **← outside touch zones**" in text and "- **Touch zones:** `src`\n" in text


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
    assert text.count("_Computed by review-packet from git (`") == 5   # uncommitted refs, changed paths, integrity, tests at risk, diff
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


def test_a_few_long_minified_lines_past_the_byte_budget_are_listed_with_their_size(tmp_path: Path) -> None:
    """A1: three 100 KB lines are well under --max-diff-lines but past the default byte budget."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, "src/zz.min.js", "".join(f"var a{i}={'x' * 100_000};\n" for i in range(3)), "minified")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    patch = reviews_dir(repo, "M1.1") / rp.DIFF_NAME
    assert f"**Diff capped at {rp.MAX_DIFF_LINES} lines** and **{rp.MAX_DIFF_BYTES} bytes**" in text
    assert "the first 2 of 3 changed file(s)" in text and "+print('a')" in text
    size = len(next(c for c in patch.read_text().split("diff --git ") if "zz.min.js" in c).encode()) + 11
    assert f"- `src/zz.min.js` (+3 -0) — not inlined ({size} bytes of diff)" in text
    assert "x" * 1000 not in text and len(text.encode()) < rp.MAX_DIFF_BYTES and "x" * 100_000 in patch.read_text()


def test_max_diff_bytes_zero_lifts_the_byte_cap(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    commit_file(repo, "src/zz.min.js", f"var a={'x' * 300_000};\n", "minified")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_bytes=0)
    assert "x" * 300_000 in text and "Diff capped" not in text
    assert not (reviews_dir(repo, "M1.1") / rp.DIFF_NAME).exists()


def test_a_generated_bundle_is_listed_as_generated_and_never_inlined(tmp_path: Path) -> None:
    """A2: a file under GENERATED_PATHS is listed even with both budgets off; DIFF.patch holds it."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, f"{rp.GENERATED_PATHS[0]}assets/index.js", "bundle()\n", "rebuild the GUI")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=0, max_diff_bytes=0)
    assert "**Diff not inlined in full**" in text and rp.GENERATED_NOTE in text
    assert f"- `{rp.GENERATED_PATHS[0]}assets/index.js` (+1 -0) — not inlined, generated (" in text
    assert "+bundle()" not in text and "+print('a')" in text
    assert "+bundle()" in (reviews_dir(repo, "M1.1") / rp.DIFF_NAME).read_text()


def test_a_linguist_generated_path_at_the_reviewed_commit_is_never_inlined(tmp_path: Path) -> None:
    """A2: .gitattributes is read at the commit under review, not from the working tree."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, ".gitattributes", "src/gen.py linguist-generated\n", "attrs")
    commit_file(repo, "src/gen.py", "made = 1\n", "generated module")
    (repo / ".gitattributes").unlink()
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `src/gen.py` (+1 -0) — not inlined, generated (" in text and "+made = 1" not in text
    assert "+src/gen.py linguist-generated" in text and "the first 3 of 4 changed file(s)" in text


def test_a_large_lockfile_sorting_first_is_listed_and_later_files_are_inlined(tmp_path: Path) -> None:
    """A2: a lockfile with no .gitattributes entry is generated and does not use up the budgets."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, "package-lock.json", "".join(f'"dep{i}": "1.0.{i}",\n' for i in range(3000)), "lock")
    commit_file(repo, "gui/yarn.lock", "dep@1:\n", "nested lock")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `package-lock.json` (+3000 -0) — not inlined, generated (" in text and '"dep0"' not in text
    assert "- `gui/yarn.lock` (+1 -0) — not inlined, generated (" in text and rp.GENERATED_NOTE in text
    assert "+print('a')" in text and "+# x" in text and "the first 2 of 4 changed file(s)" in text


def test_linguist_generated_false_inlines_a_lockfile(tmp_path: Path) -> None:
    """A2: a .gitattributes entry at the reviewed commit decides for a lockfile."""
    repo = make_review_repo(tmp_path)
    commit_file(repo, ".gitattributes", "uv.lock linguist-generated=false\n", "attrs")
    commit_file(repo, "uv.lock", "version = 1\n", "lock")
    commit_file(repo, "Cargo.lock", "version = 3\n", "cargo lock")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "+version = 1" in text and "- `uv.lock` (" not in text
    assert "- `Cargo.lock` (+1 -0) — not inlined, generated (" in text and "+version = 3" not in text


def test_main_passes_max_diff_bytes_through(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rp.main(["M1.1", "--max-diff-bytes", "1", "--repo-root", str(repo)])
    text = (reviews_dir(repo, "M1.1") / PACKET_NAME).read_text()
    assert f"**Diff capped at {rp.MAX_DIFF_LINES} lines** and **1 bytes**" in text
    assert "the first 0 of 2 changed file(s)" in text and "- `src/a.py` (+1 -0) — not inlined (" in text


def _uncommitted_block(text: str) -> str:
    start = "## Uncommitted references\n"
    return text.split(start, 1)[1].split("\n## Changed paths\n", 1)[0]


def test_packet_warns_when_a_planning_sheet_names_an_uncommitted_file(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    sheet = repo / NODE["planning_dir"]
    commit_file(repo, NODE["planning_dir"], sheet.read_text() + "\nTrack `shared/missing.md`.\n", "cite missing")
    (repo / "shared").mkdir(exist_ok=True)
    (repo / "shared" / "missing.md").write_text("untracked\n", encoding="utf-8")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    block = _uncommitted_block(text)
    assert UNCOMMITTED_REF_NOTE in block and "- `shared/missing.md`" in block
    assert "warning: `shared/missing.md` is named in the packet but not at commit" in capsys.readouterr().err


def test_packet_is_silent_when_a_named_file_is_at_the_reviewed_commit(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    commit_file(repo, "shared/ok.md", "# ok\n", "shared contract")
    sheet = repo / NODE["planning_dir"]
    commit_file(repo, NODE["planning_dir"], sheet.read_text() + "\nSee `shared/ok.md`.\n", "cite shared")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "_none_" in _uncommitted_block(text)
    assert "shared/ok.md" not in capsys.readouterr().err


def test_packet_ignores_path_like_tokens_that_are_not_repository_paths(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    sheet = repo / NODE["planning_dir"]
    commit_file(
        repo,
        NODE["planning_dir"],
        sheet.read_text() + "\nUse branch `feature/rm-thing` and `path/to/nowhere`; "
        "not `src/a.py::test_ok`, `docs/x.md:12` or `docs/x.md#anchor`.\n",
        "path-like noise",
    )
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "_none_" in _uncommitted_block(text)
    err = capsys.readouterr().err
    assert "path/to/nowhere" not in err and "feature/rm-thing" not in err
    assert "src/a.py" not in err and "docs/x.md" not in err
    assert "docs/x.md#anchor" not in err


def test_packet_warns_when_an_untracked_file_lives_outside_the_top_allowlist(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "app").mkdir()
    (repo / "app" / "x.py").write_text("x\n", encoding="utf-8")
    sheet = repo / NODE["planning_dir"]
    commit_file(repo, NODE["planning_dir"], sheet.read_text() + "\nTrack `app/x.py`.\n", "cite app")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    block = _uncommitted_block(text)
    assert UNCOMMITTED_REF_NOTE in block and "- `app/x.py`" in block
    assert "warning: `app/x.py` is named in the packet but not at commit" in capsys.readouterr().err


def test_packet_accepts_a_git_root_path_named_in_a_nested_layout_brief(tmp_path: Path, capsys) -> None:
    git_top, project = make_layout_finish_repo(tmp_path, "nested")
    commit_file(git_top, "tests/at-git-root.py", "ok\n", "at git root")
    sheet = project / NODE["planning_dir"]
    commit_file(
        git_top,
        git_root_relative(git_top, project, NODE["planning_dir"]),
        sheet.read_text() + "\nSee `src/a.py` and `tests/at-git-root.py`.\n",
        "cite committed",
    )
    text = rp.build_packet(project, "M1.1", ref=None, verify_cmds=[])
    assert "_none_" in _uncommitted_block(text)
    err = capsys.readouterr().err
    assert "src/a.py" not in err and "tests/at-git-root.py" not in err
