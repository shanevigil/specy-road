"""M21.17: no writer follows a symlink out of the directory it owns; M21.37: none follows any symlink."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

import pytest
import yaml

from tests.review_delegate_helpers import delegate_repo, run_review_cli, set_steps, verdict_step
from tests.review_repo_helpers import git, make_review_repo, review_text
from tests.test_review_cli import ONE_AI

from specy_road.finish_land_deterministic import DeterministicResolveError, resolve_deterministic_paths
from specy_road.generated_files import regenerate_generated_files
from specy_road.init_project import run_init_project
from specy_road.review_delegate_packet import ensure_packet
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.review_rejected import rejected_path, write_rejected
from specy_road.review_target import resolve_target
from specy_road.safe_write import SafeWriteError

# A packet naming another commit, so ensure_packet rebuilds it when it may write.
OLD = b"# old\n\n**Commit under review:** `0000000`\n"
LAYOUTS = ("file", "dangling_out", "link_out", "link_in")


def _place(layout: str, path: Path, outside: Path) -> Path:
    """Put ``layout`` at ``path``; returns the file whose bytes must (not) change."""
    if layout == "file":
        path.write_bytes(OLD)
        return path
    target = {"dangling_out": outside / "made.md", "link_out": outside / "theirs.md",
              "link_in": path.with_name("inner.md")}[layout]
    if layout != "dangling_out":
        target.write_bytes(OLD)
    path.symlink_to(target)
    return target


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "p"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _init(force: bool) -> Callable[[Path], tuple[Path, str, Callable[[], object]]]:
    def setup(tmp_path: Path):
        root = _project(tmp_path)
        return root, "roadmap.md", lambda: run_init_project(root, force=force, profiles="none")
    return setup


def _inited(call: Callable[[Path], object]) -> Callable[[Path], tuple[Path, str, Callable[[], object]]]:
    def setup(tmp_path: Path):
        root = _project(tmp_path)
        assert run_init_project(root, profiles="none") == 0
        (root / "roadmap.md").unlink()
        return root, "roadmap.md", lambda: call(root)
    return setup


def _finish(root: Path) -> object:
    try:
        return resolve_deterministic_paths(root, codename=None)
    except DeterministicResolveError as exc:
        return exc


def _rejected(tmp_path: Path):
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    return reviews, rejected_path(reviews, "opus").name, lambda: write_rejected(reviews, "opus", "abc", "error: x")


def _packet(tmp_path: Path):
    repo = make_review_repo(tmp_path)
    reviews = reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    t = resolve_target(repo, "M1.1", None)

    def run() -> object:
        try:
            return ensure_packet(repo, t, None)
        except SafeWriteError as exc:
            return exc
    return reviews, PACKET_NAME, run


def _refusal(path: Path) -> str:
    """The safe-write rule's sentence for a symlink at ``path``."""
    return f"{path} is a symlink (to {os.readlink(path)}), not a regular file"


# writer -> (setup, writes regular file and in-root link target, refuses every link)
# M21.37: the generated files are on the safe-write rule, so an in-repo link is refused too.
WRITERS = {
    "init": (_init(False), None, None),
    "init --force": (_init(True), True, True),
    "regenerate_generated_files": (_inited(regenerate_generated_files), True, True),
    "finish": (_inited(_finish), True, True),
    "write_rejected": (_rejected, True, True),
    "ensure_packet": (_packet, True, True),
}


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("writer", list(WRITERS))
def test_writer_refuses_a_link_out_of_its_root(tmp_path: Path, capsys, writer: str, layout: str) -> None:
    setup, writes, any_link = WRITERS[writer]
    owned, name, run = setup(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    path = owned / name
    watched = _place(layout, path, outside)
    linked = path.is_symlink()

    result = run()
    out = capsys.readouterr()

    assert path.is_symlink() == linked   # a link stays a link
    if layout == "dangling_out":
        assert not watched.exists()
    if writes is None:   # init without --force: either path present skips both, nothing touched
        assert watched.exists() is (layout != "dangling_out")
        assert layout == "dangling_out" or watched.read_bytes() == OLD
        assert not (owned / "roadmap-context.md").exists()
        assert f"skipped (exists): {name}" in out.out
        return
    refused = layout in ("dangling_out", "link_out") or (any_link and layout == "link_in")
    if not refused:
        assert watched.read_bytes() != OLD
        assert not isinstance(result, Exception)
        return
    if layout != "dangling_out":
        assert watched.read_bytes() == OLD
    named = _refusal(path)
    if writer in ("finish", "ensure_packet"):
        assert isinstance(result, Exception) and named in str(result)
    elif writer == "regenerate_generated_files":
        assert result == [name] and named in out.err
    elif writer == "init --force":   # checked before anything is written: exit 1, nothing reported as written
        assert result == 1 and f"error: {named}" in out.err
        assert not out.out.startswith("wrote")
    else:
        assert named in out.err


def test_review_delegate_refuses_a_linked_packet_before_launching(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    packet = reviews_dir(repo, "M1.1") / PACKET_NAME
    packet.unlink()
    packet.symlink_to(tmp_path / "elsewhere.md")

    assert run_review_cli("review", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) != 0

    assert _refusal(packet) in capsys.readouterr().err
    assert not spec.with_name("calls.json").exists()   # no harness started
    assert not (reviews_dir(repo, "M1.1") / "RUN-opus.json").exists()
    assert not (tmp_path / "elsewhere.md").exists()


@pytest.mark.parametrize("linked", [False, True])
def test_a_refused_marker_leaves_the_record_refusal_unchanged(tmp_path: Path, capsys, linked: bool) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    marker = rejected_path(reviews_dir(repo, "M1.1"), "opus")
    marker.parent.mkdir(parents=True, exist_ok=True)
    theirs = tmp_path / "theirs.md"
    theirs.write_bytes(OLD)
    if linked:
        marker.symlink_to(theirs)
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="approve")
    data = yaml.safe_load(text.split("---")[1])
    data["findings"]["correctness"] = ["Advisory: x drops y"]
    notes = tmp_path / "notes.md"
    notes.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")

    code = run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                          "--file", str(notes), "--repo-root", str(repo))

    err = capsys.readouterr().err
    assert code == 1 and "Advisory" in err
    assert marker.is_symlink() is linked
    assert theirs.read_bytes() == OLD
    assert (f"{marker} is a symlink (to {theirs})" in err) is linked
