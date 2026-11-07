"""M13.2 fix round 3: `upgrade` and `upgrade --dry-run` apply one write plan.

Each layout is upgraded twice on the same checkout: dry, then real, under one
injected validator that records the tree it validates (every file and link,
read through the link, ``.specyrd/manifest.json`` included). The dry run's copy
and the real checkout must be byte-identical, the exits equal, and the
checkout untouched by the dry run. Sol's two round-3 probes are kept as they
were reported: each must fail the dry run as it fails the real one.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from specy_road.bundled_scripts import upgrade
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.init_project import run_init_project
from specy_road.managed_block import HTML_COMMENT, render_block
from tests.upgrade_repo_helpers import old_repo

SKILL = ".agents/skills/specyrd-validate/SKILL.md"


def _top(at: Path) -> Path:
    """The checkout (or copy) holding project ``at``: the nearest directory with a ``.git``."""
    return next(p for p in (at, *at.parents) if (p / ".git").exists())


def _tree(top: Path) -> dict[str, tuple]:
    """``{path: (kind, bytes)}`` for every file and link under ``top`` but ``.git`` and ``work/``.

    A link's kind carries its text when it is relative; an absolute one points into
    the copy in a dry run, so only its content is compared.
    """
    out: dict[str, tuple] = {}
    for dirpath, dirs, names in os.walk(top):
        dirs[:] = [d for d in dirs if d not in (".git", "work")]
        for name in dirs + names:
            path = Path(dirpath) / name
            if name == ".git" or (path.is_dir() and not path.is_symlink()):
                continue
            text = os.readlink(path) if path.is_symlink() else None
            kind = ("file",) if text is None else ("link", "absolute" if os.path.isabs(text) else text)
            try:
                data = path.read_bytes() if path.is_file() else b"<not a file>"
            except OSError:
                data = b"<unreadable>"
            out[path.relative_to(top).as_posix()] = (*kind, data)
    return out


def _alias(tmp: Path) -> Path:
    root = old_repo(tmp)
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    return root


def _hardlink_alias(tmp: Path) -> Path:
    root = old_repo(tmp)
    os.link(root / "AGENTS.md", root / "CLAUDE.md")
    return root


def _skill_outside(tmp: Path) -> Path:
    root = old_repo(tmp / "repo")
    (tmp / "outside.md").write_text("old skill\n", encoding="utf-8")
    (root / SKILL).parent.mkdir(parents=True)
    (root / SKILL).symlink_to(tmp / "outside.md")
    manifest = root / ".specyrd" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["agents"]["cursor"].append(SKILL)
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return root


def _agents_outside(tmp: Path) -> Path:
    root = old_repo(tmp / "repo")
    (tmp / "AGENTS.md").write_text("# Theirs\n\nShared rules, no block.\n", encoding="utf-8")
    (root / "AGENTS.md").unlink()
    (root / "AGENTS.md").symlink_to(tmp / "AGENTS.md")
    return root


def _ignored_claude(tmp: Path) -> Path:
    root = old_repo(tmp)
    (root / "CLAUDE.md").write_text("# Claude\n\nOur own Claude notes.\n", encoding="utf-8")
    with (root / ".gitignore").open("a", encoding="utf-8") as f:
        f.write("CLAUDE.md\n")
    return root


def _stale_block(tmp: Path) -> Path:
    root = old_repo(tmp)
    stale = render_block(["- an old rule"], style=HTML_COMMENT)
    (root / "AGENTS.md").write_text(f"# Ours\n\n{stale}\nOur text.\n", encoding="utf-8")
    return root


def _nested(tmp: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    assert run_init_project(tmp / "sr") == 0
    (tmp / "sr" / "schemas" / "orchestration.schema.json").unlink()
    (tmp / "sr" / "AGENTS.md").write_text("# Ours\n\nOur rules.\n", encoding="utf-8")
    return tmp / "sr"


LAYOUTS: dict[str, Callable[[Path], Path]] = {
    "claude-md-aliases-agents-md": _alias,
    "agents-md-and-claude-md-hard-linked": _hardlink_alias,
    "canonical-skill-linked-outside": _skill_outside,
    "agents-md-linked-outside": _agents_outside,
    "ignored-claude-md": _ignored_claude,
    "stale-managed-block": _stale_block,
    "nested-project-root": _nested,
}


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_dry_run_copy_and_real_checkout_end_byte_identical(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    project = LAYOUTS[layout](tmp_path)
    checkout = _top(project)
    dry_trees: list[dict[str, tuple]] = []
    real_trees: list[dict[str, tuple]] = []
    untouched = _tree(checkout)

    monkeypatch.setattr(upgrade, "validate_at", lambda at: dry_trees.append(_tree(_top(at))))
    dry = run_upgrade(project, dry_run=True)
    assert "dry run modified" not in capsys.readouterr().err
    assert _tree(checkout) == untouched

    monkeypatch.setattr(upgrade, "validate_at", lambda at: real_trees.append(_tree(_top(at))))
    real = run_upgrade(project)

    # M21.37: a canonical skill refused for a link exits 1, real and dry alike; the rest of the plan applies.
    assert dry == real == (1 if layout == "canonical-skill-linked-outside" else 0)
    assert dry_trees and real_trees
    assert dry_trees[-1] == real_trees[-1]
    assert real_trees[-1] != untouched   # the upgrade wrote something, so the comparison is not vacuous


def _exits(root: Path, validate: Callable[[Path], None], capsys, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    monkeypatch.setattr(upgrade, "validate_at", validate)
    capsys.readouterr()
    outcomes = []
    for dry_run in (True, False):
        before = _tree(root)
        code = run_upgrade(root, dry_run=dry_run)
        err = capsys.readouterr().err
        assert "dry run modified" not in err
        if dry_run:
            assert _tree(root) == before
        outcomes.append((code, [line for line in err.splitlines() if line.startswith("error:")]))
    return outcomes


def test_sol_low_f1_hard_linked_agents_and_claude_see_the_same_bytes_in_both(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``os.link(AGENTS.md, CLAUDE.md)``: both names must stay byte-identical after refresh in dry and real."""
    root = _hardlink_alias(tmp_path)

    def validate(at: Path) -> None:
        if (at / "AGENTS.md").read_bytes() != (at / "CLAUDE.md").read_bytes():
            print("error: hard-linked AGENTS.md and CLAUDE.md differ", file=sys.stderr)
            raise SystemExit(1)

    dry, real = _exits(root, validate, capsys, monkeypatch)

    assert dry == real == (0, [])


def test_sol_f1_an_alias_fails_the_claude_import_check_in_both(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLAUDE.md -> AGENTS.md: the AGENTS.md refresh overwrites the shared block, so the CLAUDE import is gone."""
    root = _alias(tmp_path)

    def validate(at: Path) -> None:
        if "@.specyrd/AGENTS.md" not in (at / "CLAUDE.md").read_text(encoding="utf-8").splitlines():
            print("error: CLAUDE.md has no current import", file=sys.stderr)
            raise SystemExit(1)

    dry, real = _exits(root, validate, capsys, monkeypatch)

    assert dry == real == (1, ["error: CLAUDE.md has no current import"])


def test_sol_f2_a_refused_canonical_skill_is_unowned_in_both_manifests(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recorded canonical skill linked outside is refused (an error, M21.37), so the refreshed manifest drops it."""
    root = _skill_outside(tmp_path)
    owned_seen: list[bool] = []

    def validate(at: Path) -> None:
        data = json.loads((at / ".specyrd" / "manifest.json").read_text(encoding="utf-8"))
        owned_seen.append(SKILL in {p for paths in data["agents"].values() for p in paths})
        if not owned_seen[-1]:
            print("error: required skill was refused", file=sys.stderr)
            raise SystemExit(1)

    dry, real = _exits(root, validate, capsys, monkeypatch)

    refusal = f"error: {root / SKILL} is a symlink (to {tmp_path / 'outside.md'}), not a regular file"
    assert dry == real == (1, [refusal, "error: required skill was refused"])
    assert owned_seen and not any(owned_seen)
    assert (tmp_path / "outside.md").read_text(encoding="utf-8") == "old skill\n"


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_link_climbing_past_the_root_creates_nothing_outside_the_copy(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    """``notes -> ../../(past /)/<target>``: ``..`` stops at ``/`` in the checkout, so the mirror must not climb out."""
    root = old_repo(tmp_path / "repo")
    target = tmp_path / "target"
    target.mkdir()
    (target / "kept.md").write_text("theirs\n", encoding="utf-8")
    (root / "notes").symlink_to("../" * (len(root.parts) + 1) + target.relative_to("/").as_posix())
    assert (root / "notes" / "kept.md").read_text(encoding="utf-8") == "theirs\n"
    scratch = tmp_path / "scratch"   # the mirror lives two levels under it, where that text's excess ``..`` lands
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    assert run_upgrade(root, dry_run=dry_run) == 0

    assert "Traceback" not in capsys.readouterr().err
    assert list(scratch.iterdir()) == []
    assert sorted(p.name for p in target.iterdir()) == ["kept.md"]
    assert os.readlink(root / "notes").endswith(target.relative_to("/").as_posix())
