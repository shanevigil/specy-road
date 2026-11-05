"""M13.12 A5: the context-warning hash is disposable, and only the ``validate`` CLI folds.

Any hash file that cannot be read or matched (invalid UTF-8, truncated, a
directory, no permission) is a cache miss: the warnings print in full and the
command goes on. ``validate_at`` on its own (as ``upgrade`` calls it) never folds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from specy_road.context_notice_cache import HASH_FILENAME, fold_next_report, report_context_warnings

WARNINGS = ["context: warning — CLAUDE.md is 250 lines; …", "context: warning — AGENTS.md total …"]
FULL = "".join(ln + "\n" for ln in WARNINGS)
FOLDED = "context: 2 warnings unchanged (validate --context shows them)\n"


def warn(_root: Path) -> None:
    for ln in WARNINGS:
        print(ln, file=sys.stderr)


def hash_path(root: Path) -> Path:
    return root / ".specyrd" / "cache" / HASH_FILENAME


def recorded(root: Path, capsys) -> bytes:
    """Run once so the hash is recorded; its bytes."""
    report_context_warnings(root, warn, cached=True)
    capsys.readouterr()
    return hash_path(root).read_bytes()


def test_a_non_utf8_hash_file_is_a_miss_and_is_rewritten(tmp_path: Path, capsys) -> None:
    good = recorded(tmp_path, capsys)
    hash_path(tmp_path).write_bytes(b"\xff\xfe" + good[2:])
    report_context_warnings(tmp_path, warn, cached=True)
    assert capsys.readouterr().err == FULL
    assert hash_path(tmp_path).read_bytes() == good
    report_context_warnings(tmp_path, warn, cached=True)
    assert capsys.readouterr().err == FOLDED


def test_a_truncated_hash_file_is_a_miss(tmp_path: Path, capsys) -> None:
    good = recorded(tmp_path, capsys)
    hash_path(tmp_path).write_bytes(good[:10])
    report_context_warnings(tmp_path, warn, cached=True)
    assert capsys.readouterr().err == FULL
    assert hash_path(tmp_path).read_bytes() == good


def test_a_directory_in_place_of_the_hash_file_is_a_miss_every_time(tmp_path: Path, capsys) -> None:
    hash_path(tmp_path).mkdir(parents=True)
    for _ in range(2):
        report_context_warnings(tmp_path, warn, cached=True)
        assert capsys.readouterr().err == FULL
    report_context_warnings(tmp_path, lambda _r: None, cached=True)   # no warnings: the unlink fails quietly
    assert capsys.readouterr().err == ""
    assert hash_path(tmp_path).is_dir()


def test_a_file_in_place_of_the_cache_dir_is_a_miss(tmp_path: Path, capsys) -> None:
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "cache").write_text("not a dir\n", encoding="utf-8")
    for _ in range(2):
        report_context_warnings(tmp_path, warn, cached=True)
        assert capsys.readouterr().err == FULL


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX permissions and a non-root user")
def test_an_unreadable_hash_file_is_a_miss(tmp_path: Path, capsys) -> None:
    recorded(tmp_path, capsys)
    hash_path(tmp_path).chmod(0)
    try:
        for _ in range(2):
            report_context_warnings(tmp_path, warn, cached=True)
            assert capsys.readouterr().err == FULL
    finally:
        hash_path(tmp_path).chmod(0o644)


def test_without_the_validate_cli_flag_reports_never_fold(tmp_path: Path, capsys) -> None:
    recorded(tmp_path, capsys)
    for _ in range(2):
        report_context_warnings(tmp_path, warn)   # how validate_at calls it, so how upgrade runs it
        assert capsys.readouterr().err == FULL


def test_the_cli_flag_folds_one_report_only(tmp_path: Path, capsys) -> None:
    recorded(tmp_path, capsys)
    fold_next_report(True)
    report_context_warnings(tmp_path, warn)
    assert capsys.readouterr().err == FOLDED
    report_context_warnings(tmp_path, warn)
    assert capsys.readouterr().err == FULL
