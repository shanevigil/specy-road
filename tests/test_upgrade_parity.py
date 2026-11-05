"""M13.2 fix round 2: `upgrade --dry-run` decides each path as the real run does.

The preview copy holds no links, so its refresh would write a managed file the
real refresh refuses (Sol, round 2: an AGENTS.md linked out of the repository
got a block in the copy, so a validate error the real run raised never showed
in the dry run). Each case runs the dry run, then the real run, on the same
repo, under one injected validator, and needs the same exit and error from both.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from specy_road.agents_md_block import agents_md_block_state
from specy_road.bundled_scripts import upgrade
from specy_road.bundled_scripts.upgrade import run_upgrade
from tests.upgrade_repo_helpers import old_repo

ERROR = "error: AGENTS.md has no current specy-road block"


def _block_required(at: Path) -> None:
    if agents_md_block_state(at) != "current":
        print(ERROR, file=sys.stderr)
        raise SystemExit(1)


def _dry_then_real(root: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> tuple[tuple[int, bool], tuple[int, bool]]:
    monkeypatch.setattr(upgrade, "validate_at", _block_required)
    capsys.readouterr()
    dry = run_upgrade(root, dry_run=True)
    dry_err = capsys.readouterr().err
    assert "dry run modified" not in dry_err
    real = run_upgrade(root)
    return (dry, ERROR in dry_err), (real, ERROR in capsys.readouterr().err)


def test_agents_md_linked_out_of_the_repo_is_refused_in_the_preview_too(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = old_repo(tmp_path / "repo")
    outside = tmp_path / "outside" / "AGENTS.md"
    outside.parent.mkdir()
    outside.write_text("# Theirs\n\nShared rules, no block.\n", encoding="utf-8")
    (root / "AGENTS.md").unlink()
    (root / "AGENTS.md").symlink_to(outside)

    dry, real = _dry_then_real(root, capsys, monkeypatch)

    assert dry == real == (1, True)
    assert outside.read_text(encoding="utf-8") == "# Theirs\n\nShared rules, no block.\n"


def test_agents_md_linked_inside_the_repo_is_refreshed_in_both(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = old_repo(tmp_path)
    (root / "agents").mkdir()
    (root / "agents" / "AGENTS.md").write_text("# Ours\n\nOur rules.\n", encoding="utf-8")
    (root / "AGENTS.md").unlink()
    (root / "AGENTS.md").symlink_to(Path("agents") / "AGENTS.md")

    dry, real = _dry_then_real(root, capsys, monkeypatch)

    assert dry == real == (0, False)
    assert (root / "AGENTS.md").is_symlink() and agents_md_block_state(root) == "current"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root reads any file")
def test_an_unreadable_agents_md_fails_alike_in_both(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = old_repo(tmp_path)
    (root / "AGENTS.md").chmod(0)
    try:
        monkeypatch.setattr(upgrade, "validate_at", _block_required)
        capsys.readouterr()
        outcomes, outs = [], []
        for dry_run in (True, False):
            try:
                outcomes.append(run_upgrade(root, dry_run=dry_run))
            except OSError as e:
                outcomes.append(type(e).__name__)
            outs.append(capsys.readouterr())
    finally:
        (root / "AGENTS.md").chmod(0o644)

    assert outcomes[0] == outcomes[1]
    assert "would write AGENTS.md (failed)" in outs[0].out and "wrote AGENTS.md (failed)" in outs[1].out
    assert "dry run modified" not in outs[0].err
