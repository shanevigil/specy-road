"""The `CLAUDE.md` managed block: what `specyrd init --force` may and may not touch.

`--force` is documented as overwriting the stubs this tool installed. It used to
rewrite the whole of a consumer's `CLAUDE.md` as well — a file it never listed in
`.specyrd/manifest.json`. These tests pin the replacement contract: the guide is
one marked block inside a file that stays the consumer's.
"""

from __future__ import annotations

import json
from pathlib import Path

from specy_road.agent_guide_block import render_guide_lines
from specy_road.managed_block import MARKER_START
from specy_road.specyrd_init import InitResult, run_init

HAND_AUTHORED_CLAUDE_MD = """# My Project

## Tech stack

- React 19, TypeScript 5.9, Vite

## Project structure

- `src/` app code, `e2e/` Playwright specs

## Code quality rules

- No `any`. No default exports.

## Workflow rules

- Never push to `main` directly.
"""


def _init_claude(
    tmp_path: Path, *, force: bool = False, dry_run: bool = False
) -> InitResult:
    return run_init(
        target=tmp_path,
        agent="claude-code",
        dry_run=dry_run,
        force=force,
        ai_commands_dir=None,
        write_claude_md=True,
    )


def test_specyrd_init_creates_claude_md_when_absent(tmp_path: Path) -> None:
    _init_claude(tmp_path)
    p = tmp_path / "CLAUDE.md"
    assert p.is_file()
    assert "AGENTS.md" in p.read_text(encoding="utf-8")


def test_force_never_replaces_a_hand_authored_claude_md(tmp_path: Path) -> None:
    """The v0.2.1rc1 data-loss repro: --force must not touch what it does not own."""
    p = tmp_path / "CLAUDE.md"
    p.write_text(HAND_AUTHORED_CLAUDE_MD, encoding="utf-8")

    _init_claude(tmp_path, force=True)
    text = p.read_text(encoding="utf-8")

    # Every consumer heading survives, and the block was added, not substituted.
    for heading in ("## Tech stack", "## Project structure", "## Code quality rules"):
        assert heading in text
    assert text.startswith(HAND_AUTHORED_CLAUDE_MD)
    assert "specy-road managed block" in text
    assert MARKER_START not in text  # markdown gets HTML comments, not '#'


def test_the_claude_md_block_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(HAND_AUTHORED_CLAUDE_MD, encoding="utf-8")
    _init_claude(tmp_path, force=True)
    first = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    r = _init_claude(tmp_path, force=True)

    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == first
    assert not [w for w in r.written if w.startswith("CLAUDE.md")]


def test_claude_md_is_recorded_as_managed(tmp_path: Path) -> None:
    """--force is only answerable if the manifest lists what it may rewrite."""
    _init_claude(tmp_path)
    manifest = json.loads(
        (tmp_path / ".specyrd" / "manifest.json").read_text(encoding="utf-8")
    )
    assert "CLAUDE.md" in manifest["agents"]["claude-code"]


def test_cursor_gets_no_claude_md(tmp_path: Path) -> None:
    run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
        write_claude_md=True,
    )
    assert not (tmp_path / "CLAUDE.md").exists()


def test_a_dry_run_previews_the_managed_blocks_and_writes_nothing(
    tmp_path: Path,
) -> None:
    (tmp_path / "CLAUDE.md").write_text(HAND_AUTHORED_CLAUDE_MD, encoding="utf-8")

    r = _init_claude(tmp_path, dry_run=True)

    assert any(w.startswith("CLAUDE.md (") for w in r.written)
    assert any(w.startswith(".gitignore (") for w in r.written)
    assert any(w.startswith(".cursorindexingignore (") for w in r.written)
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == HAND_AUTHORED_CLAUDE_MD
    assert not (tmp_path / ".gitignore").exists()


def test_the_guide_block_is_prefixed_in_a_nested_layout(tmp_path: Path) -> None:
    """CLAUDE.md sits at the git root; its pointers name the project root."""
    (tmp_path / "sr" / "roadmap").mkdir(parents=True)
    (tmp_path / "sr" / "roadmap" / "manifest.json").write_text("{}", encoding="utf-8")

    lines = render_guide_lines("sr/")

    assert any("sr/roadmap/manifest.json" in ln for ln in lines)
    assert any("sr/roadmap-context.md" in ln for ln in lines)
    assert not any("{{PROJECT_PREFIX}}" in ln for ln in lines)
    assert not any("{{SPECYRD_VERSION}}" in ln for ln in lines)

