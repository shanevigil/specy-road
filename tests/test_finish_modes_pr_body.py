"""F-015: finish_modes.print_finish_tail surfaces --body-file when given a path."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from specy_road.finish_modes import print_finish_tail


def _args(push: bool = True) -> argparse.Namespace:
    return argparse.Namespace(push=push, remote="origin")


def _capture(fn) -> str:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = saved
    return buf.getvalue()


def test_print_finish_tail_no_body_when_no_path() -> None:
    out = _capture(lambda: print_finish_tail(
        _args(),
        node_id="M1.1",
        node={"title": "Hello"},
        branch="feature/rm-x",
        integration_branch="main",
        mr_manual=False,
    ))
    assert "gh pr create" in out
    assert "--body-file" not in out
    assert "--description-file" not in out


def test_print_finish_tail_emits_body_file_when_path_supplied(tmp_path: Path) -> None:
    body = tmp_path / "work" / "pr-body-M1.1.md"
    body.parent.mkdir()
    body.write_text("# body\n", encoding="utf-8")
    out = _capture(lambda: print_finish_tail(
        _args(),
        node_id="M1.1",
        node={"title": "Hello"},
        branch="feature/rm-x",
        integration_branch="main",
        mr_manual=False,
        pr_body_path=body,
    ))
    assert "gh pr create" in out
    assert f'--body-file "{body}"' in out
    # GitLab equivalent should also reference the same file.
    assert f'--description-file "{body}"' in out
    # Pointer line tells the dev where the snapshot lives.
    assert "Body snapshot:" in out
    assert "F-015" in out
