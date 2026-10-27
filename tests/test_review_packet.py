"""Tests for specy-road review-packet."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import git, make_review_repo

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
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `src/a.py`\n" in text
    assert "- `docs/x.md`  **← outside touch zones**" in text
    assert "1 path(s) outside the touch zones" in text


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
    assert text.count("_Computed by review-packet from git (`") == 2   # changed paths and diff
    assert text.count(f"_Run now by review-packet at HEAD `{head}`._") == 1
    assert f"## Implementation summary\n\n{rp.ASSERTED_WORKING_TREE}\n\nDid it." in text


def test_main_writes_packet_file(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    rp.main(["M1.1", "--repo-root", str(repo)])
    out = reviews_dir(repo, "M1.1") / PACKET_NAME
    assert out.is_file()
    assert str(out) in capsys.readouterr().out
