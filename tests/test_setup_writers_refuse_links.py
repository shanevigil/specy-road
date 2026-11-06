"""M21.37: the setup and upgrade writers refuse any symlink on the path, and upgrade never writes outside the checkout.

Each row: refused with ``error: <path> ...`` on stderr, exit 1, no traceback, and
every byte (and the existence of every path) outside and in the checkout unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

from specy_road import safe_write
from specy_road.archive_deep import deepen_archive
from specy_road.archive_index import load_archive_index, write_archive_index
from specy_road.archive_ops import archive_node
from specy_road.archive_restore import restore_archive
from specy_road.bundled_scripts import digest_cli, export_roadmap_md, refresh_schemas, refresh_stubs, upgrade
from specy_road.bundled_scripts.do_next_task_register import regenerated_tracked_paths
from specy_road.bundled_scripts.upgrade_plan import Entry, Plan, apply_plan
from specy_road.init_project import run_init_project
from specy_road.specyrd_init import run_init
from tests.helpers import DOGFOOD
from tests.upgrade_repo_helpers import OLD_STUB, old_repo

SCHEMA = "schemas/roadmap.schema.json"


def _tree(*dirs: Path) -> dict[str, object]:
    """Every path under ``dirs``, links not followed: a link's text, a file's bytes, or ``dir``.

    ``.git`` and the derived ``.specyrd/cache/`` (the digest's read cache) are left out.
    """
    out: dict[str, object] = {}
    for top in dirs:
        for dirpath, subdirs, names in os.walk(top):
            subdirs[:] = [d for d in subdirs if d != ".git" and Path(dirpath, d) != top / ".specyrd" / "cache"]
            for name in subdirs + names:
                p = Path(dirpath, name)
                out[str(p)] = ("link", os.readlink(p)) if p.is_symlink() else p.read_bytes() if p.is_file() else "dir"
    return out


def _refused(run: Callable[[], object], capsys, path: Path, *dirs: Path) -> None:
    """``run`` exits 1 naming ``path`` as a refused symlink, and nothing under ``dirs`` changed."""
    before = _tree(*dirs)
    try:
        code = run()
    except SystemExit as e:
        code = e.code
    err = capsys.readouterr().err
    assert code == 1, err
    assert any(line.startswith("error: ") and f"{path} is a symlink" in line for line in err.splitlines()), err
    assert "Traceback" not in err
    assert _tree(*dirs) == before


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "theirs.json").write_text('{"theirs": true}\n', encoding="utf-8")
    (outside / "docs").mkdir(exist_ok=True)
    return outside


# layout -> (the path that is a link, its target) relative to the repo and the outside directory
INIT_LAYOUTS = {
    "final-link-out": (SCHEMA, lambda repo, out: out / "theirs.json"),
    "dangling": (SCHEMA, lambda repo, out: out / "made.json"),
    "docs-parent-link": ("docs", lambda repo, out: out / "docs"),
    "schemas-parent-link": ("schemas", lambda repo, out: out),
    "in-repo-link": (SCHEMA, lambda repo, out: repo / "mine.json"),
    "gitignore-in-repo-link": (".gitignore", lambda repo, out: repo / "mine.json"),
}


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("layout", list(INIT_LAYOUTS))
def test_init_project_refuses_a_link(tmp_path: Path, capsys, layout: str, force: bool) -> None:
    repo, outside = tmp_path / "repo", _outside(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "mine.json").write_text("mine\n", encoding="utf-8")
    rel, target = INIT_LAYOUTS[layout]
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).symlink_to(target(repo, outside))

    _refused(lambda: run_init_project(repo, force=force, profiles="none"), capsys, repo / rel, repo, outside)
    assert not (outside / "made.json").exists()


def _inited(tmp_path: Path) -> tuple[Path, Path]:
    repo, outside = tmp_path / "repo", _outside(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert run_init_project(repo, profiles="none") == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
                   check=True)
    return repo, outside


def _relink(path: Path, target: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    path.unlink(missing_ok=True)
    path.symlink_to(target)


SCHEMA_LAYOUTS = {   # grok's reproduction first
    "schema-link-out": (SCHEMA, lambda out: out / "theirs.json"),
    "schemas-dir-link": ("schemas", lambda out: out),
    "dangling": (SCHEMA, lambda out: out / "made.json"),
}
SCHEMA_RUNNERS = {
    "refresh-schemas": lambda repo: refresh_schemas.main(["--repo-root", str(repo)]),
    "upgrade": lambda repo: upgrade.main(["--repo-root", str(repo)]),
    "upgrade --dry-run": lambda repo: upgrade.main(["--repo-root", str(repo), "--dry-run"]),
}


@pytest.mark.parametrize("runner", list(SCHEMA_RUNNERS))
@pytest.mark.parametrize("layout", list(SCHEMA_LAYOUTS))
def test_schema_refresh_and_upgrade_refuse_a_linked_schema(tmp_path: Path, capsys, layout: str, runner: str) -> None:
    repo, outside = _inited(tmp_path)
    rel, target = SCHEMA_LAYOUTS[layout]
    _relink(repo / rel, target(outside))
    (outside / "schemas-copy").mkdir()   # the outside dir must not gain a schema either
    if rel == SCHEMA:   # a stale schema sorted before the linked one is not written either
        (repo / "schemas" / "decisions.schema.json").write_text("{}\n", encoding="utf-8")

    _refused(lambda: SCHEMA_RUNNERS[runner](repo), capsys, repo / rel, repo, outside)
    assert not (outside / "made.json").exists()


def test_apply_plan_writes_nothing_when_one_change_lands_outside(tmp_path: Path) -> None:
    """The backstop: a refresher that bypassed the rule still never reaches outside, nor the dry run's copy."""
    checkout, outside, copy = tmp_path / "repo", _outside(tmp_path), tmp_path / "copy"
    checkout.mkdir()
    copy.mkdir()
    plan = Plan(checkout, checkout / "work", [
        Entry(path="ok.md", target=checkout.resolve() / "ok.md", action="write", data=b"x"),
        Entry(path=str(outside / "theirs.json"), target=outside.resolve() / "theirs.json", action="write", data=b"x"),
    ])
    before = _tree(checkout, outside)

    for locate in (lambda p: p, lambda p: copy / p.name):
        with pytest.raises(safe_write.SafeWriteError, match=f"{outside.resolve() / 'theirs.json'} is outside"):
            apply_plan(plan, locate)
    assert _tree(checkout, outside) == before and not any(copy.iterdir())


@pytest.mark.parametrize("layout", ["file-link-out", "specyrd-dir-link", "gitignore-in-repo-link"])
def test_specyrd_init_refuses_a_linked_manifest_or_ignore_file(tmp_path: Path, capsys, layout: str) -> None:
    repo, outside = _inited(tmp_path)
    path = {"file-link-out": repo / ".specyrd" / "manifest.json", "specyrd-dir-link": repo / ".specyrd",
            "gitignore-in-repo-link": repo / ".gitignore"}[layout]
    target = {"file-link-out": outside / "theirs.json", "specyrd-dir-link": outside / "specyrd",
              "gitignore-in-repo-link": repo / "mine.txt"}[layout]
    if layout == "specyrd-dir-link":
        shutil.copytree(repo / ".specyrd", outside / "specyrd")
    (repo / "mine.txt").write_text("mine\n", encoding="utf-8")
    _relink(path, target)

    _refused(lambda: run_init(target=repo, agent="cursor", dry_run=False, force=False, ai_commands_dir=None),
             capsys, path, repo, outside)


GENERATED_LAYOUTS = {
    "final-link-out": lambda repo, out, name: _relink(repo / name, out / "theirs.json") or repo / name,
    "dangling": lambda repo, out, name: _relink(repo / name, out / "made.md") or repo / name,
    "in-repo-link": lambda repo, out, name: _relink(repo / name, repo / "mine.json") or repo / name,
}


def _export(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export", "--repo-root", str(repo)])
    export_roadmap_md.main()


@pytest.mark.parametrize("layout", list(GENERATED_LAYOUTS))
@pytest.mark.parametrize("command", ["export", "digest"])
def test_export_and_digest_refuse_a_linked_output(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch,
                                                  command: str, layout: str) -> None:
    repo, outside = _inited(tmp_path)
    (repo / "mine.json").write_text("mine\n", encoding="utf-8")
    name = "roadmap.md" if command == "export" else "roadmap-context.md"
    path = GENERATED_LAYOUTS[layout](repo, outside, name)
    run = (lambda: _export(repo, monkeypatch)) if command == "export" else (
        lambda: digest_cli.main(["--repo-root", str(repo)]))

    _refused(run, capsys, path, repo, outside)
    assert not (outside / "made.md").exists()


@pytest.mark.parametrize("layout", ["final-link-out", "parent-link"])
def test_digest_refuses_a_linked_relative_output(tmp_path: Path, capsys, layout: str) -> None:
    repo, outside = _inited(tmp_path)
    (repo / "out").mkdir()
    path = repo / "out" / "ctx.md" if layout == "final-link-out" else repo / "out"
    _relink(path, outside / "theirs.json" if layout == "final-link-out" else outside / "docs")

    _refused(lambda: digest_cli.main(["--repo-root", str(repo), "-o", "out/ctx.md"]), capsys, path, repo, outside)


@pytest.mark.parametrize("output", ["checkout", "checkout-sibling-link"])
def test_digest_checks_an_absolute_output_against_the_checkout(tmp_path: Path, capsys, output: str) -> None:
    """Nested project at ``sr/``: an absolute ``-o`` outside the project but in the checkout, or the checkout itself."""
    checkout, outside = tmp_path / "repo", _outside(tmp_path)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    assert run_init_project(checkout / "sr", profiles="none") == 0
    (checkout / "other").symlink_to(outside / "docs")
    dest = checkout if output == "checkout" else checkout / "other" / "ctx.md"
    before = _tree(checkout, outside)

    with pytest.raises(SystemExit) as e:
        digest_cli.main(["--repo-root", str(checkout / "sr"), "-o", str(dest)])

    err = capsys.readouterr().err
    named = f"error: {checkout} is a directory" if output == "checkout" else f"error: {checkout / 'other'} is a symlink"
    assert e.value.code == 1 and named in err and "Traceback" not in err
    assert _tree(checkout, outside) == before


@pytest.mark.parametrize("tracked", [(), ("roadmap.md",)])
def test_pickup_regenerates_only_tracked_files_and_refuses_a_link(tmp_path: Path, tracked: tuple[str, ...]) -> None:
    repo, outside = _inited(tmp_path)
    for name in ("roadmap.md", "roadmap-context.md"):
        if name not in tracked:
            subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", name], check=True)
            (repo / name).unlink()
    assert regenerated_tracked_paths(repo) == []   # nothing drifted: no untracked name created
    assert not (repo / "roadmap-context.md").exists()
    assert (repo / "roadmap.md").exists() is bool(tracked)
    if not tracked:
        return
    _relink(repo / "roadmap.md", outside / "theirs.json")
    before = _tree(repo, outside)
    with pytest.raises(safe_write.SafeWriteError, match=f"^{repo / 'roadmap.md'} is a symlink"):
        regenerated_tracked_paths(repo)
    assert _tree(repo, outside) == before


def test_refresh_stubs_refuses_a_linked_stub_and_still_makes_the_skill_links(tmp_path: Path, capsys) -> None:
    repo, outside = _inited(tmp_path)
    run_init(target=repo, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None)
    stub = repo / ".agents" / "skills" / "specyrd-validate" / "SKILL.md"
    (repo / "mine.md").write_text("mine\n", encoding="utf-8")
    _relink(stub, repo / "mine.md")
    skill_link = repo / ".claude" / "skills" / "specyrd-brief"
    skill_link.unlink()
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        refresh_stubs.main(["--repo-root", str(repo)])
    err = capsys.readouterr().err
    assert e.value.code == 1 and f"error: {stub} is a symlink (to {repo / 'mine.md'})" in err
    assert "Traceback" not in err
    assert stub.is_symlink() and (repo / "mine.md").read_text(encoding="utf-8") == "mine\n"
    assert skill_link.is_symlink() and skill_link.resolve() == (repo / ".agents" / "skills" / "specyrd-brief").resolve()


@pytest.mark.parametrize("sibling", [True, False], ids=["with-sibling", "only-entry"])
def test_upgrade_prune_refuses_an_orphan_under_a_linked_directory(tmp_path: Path, capsys, sibling: bool) -> None:
    repo, outside = old_repo(tmp_path / "repo"), _outside(tmp_path)
    linked = repo / Path(OLD_STUB).parent
    shutil.copytree(linked, outside / "old")
    if sibling:
        (outside / "old" / "sibling.md").write_text("theirs\n", encoding="utf-8")
    _relink(linked, outside / "old")

    _refused(lambda: upgrade.main(["--repo-root", str(repo), "--prune"]), capsys, linked, repo, outside)
    assert (outside / "old" / Path(OLD_STUB).name).is_file()


def _archived(tmp_path: Path, deep: bool = False) -> tuple[Path, Path, dict]:
    repo = tmp_path / "repo"
    shutil.copytree(DOGFOOD, repo)
    outside = _outside(tmp_path)
    rec = archive_node(repo, "M0.1")
    if deep:
        deepen_archive(repo, rec["archive_id"])
    return repo, outside, rec


def _set_record(repo: Path, **fields: object) -> None:
    doc = load_archive_index(repo)
    doc["records"][0].update(fields)
    write_archive_index(repo, doc)


def _chunk_out(repo: Path, outside: Path, rec: dict) -> Path:
    shutil.copy(repo / rec["chunk"], outside / "outside.json")
    _set_record(repo, chunk="../outside/outside.json")
    return repo / "../outside/outside.json"


def _phases_linked(repo: Path, outside: Path, rec: dict) -> Path:
    shutil.move(repo / "roadmap" / "phases", outside / "phases")
    (repo / "roadmap" / "phases").symlink_to(outside / "phases")
    return repo / "roadmap" / "phases"


def _origin_linked(repo: Path, outside: Path, rec: dict) -> Path:
    shutil.move(repo / "planning", outside / "planning")
    (repo / "planning").symlink_to(outside / "planning")
    return repo / "planning"


def _stored_linked(repo: Path, outside: Path, rec: dict) -> Path:
    stored_dir = repo / Path(rec["planning"][0]["stored"]).parent
    shutil.move(stored_dir, outside / "stored")
    stored_dir.symlink_to(outside / "stored")
    return stored_dir


def _second_move_unsafe(repo: Path, outside: Path, rec: dict) -> Path:
    (outside / "sheet.md").write_text("theirs\n", encoding="utf-8")
    (repo / "planning" / "linked.md").symlink_to(outside / "sheet.md")
    moves = rec["planning"] + [{"stored": rec["planning"][0]["stored"], "origin": "planning/linked.md"}]
    _set_record(repo, planning=moves)
    return repo / "planning" / "linked.md"


def _unpack_linked(repo: Path, outside: Path, rec: dict) -> Path:
    """A deep record unpacks its chunk into ``roadmap/archive/chunks/``: here a link out."""
    chunks = repo / "roadmap" / "archive" / "chunks"
    if chunks.exists():
        shutil.move(chunks, outside / "chunks")
    else:
        (outside / "chunks").mkdir()
    chunks.symlink_to(outside / "chunks")
    return chunks


RESTORE_LAYOUTS = {"chunk-out": _chunk_out, "phases-linked": _phases_linked, "origin-linked": _origin_linked,
                   "stored-linked": _stored_linked, "second-move-unsafe": _second_move_unsafe,
                   "unpack-linked": _unpack_linked}
RESTORE_ROWS = [*((layout, False) for layout in RESTORE_LAYOUTS if layout != "unpack-linked"),
                *((layout, True) for layout in ("phases-linked", "origin-linked", "unpack-linked"))]


@pytest.mark.parametrize(("layout", "deep"), RESTORE_ROWS)
def test_archive_restore_refuses_before_the_first_change(tmp_path: Path, layout: str, deep: bool) -> None:
    """A deep record is checked whole, its unpacking included, before ``undeepen_archive`` changes anything."""
    repo, outside, rec = _archived(tmp_path, deep)
    path = RESTORE_LAYOUTS[layout](repo, outside, rec)
    before = _tree(repo, outside)

    with pytest.raises(ValueError, match="restore refused, nothing was changed") as e:
        restore_archive(repo, rec["archive_id"])
    assert str(path) in str(e.value) or str(os.path.normpath(path)) in str(e.value)
    assert _tree(repo, outside) == before
    assert json.loads((repo / "roadmap" / "archive" / "index.json").read_text(encoding="utf-8"))["records"]


def test_restoring_the_last_record_keeps_an_unrelated_linked_directory(tmp_path: Path) -> None:
    """The empty-archive cleanup never lists or removes a symlinked directory: the archive directory stays."""
    repo, outside, rec = _archived(tmp_path)
    (outside / "empty").mkdir()
    link = repo / "roadmap" / "archive" / "linked"
    link.symlink_to(outside / "empty")

    restore_archive(repo, rec["archive_id"])

    assert link.is_symlink() and (outside / "empty").is_dir()
    assert load_archive_index(repo)["records"] == []
