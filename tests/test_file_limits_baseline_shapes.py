"""YAML shape regressions for file-limits --write-baseline (M15.7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from specy_road.file_limits_baseline import write_baseline
from specy_road.file_limits_engine import run_file_limits_scan
from tests.test_file_limits_baseline import (
    _assert_only_inserted,
    _policy_prefix,
    _write_layout,
)


@pytest.mark.parametrize(
    "override_suffix",
    [
        "override_limits: []\n",
        "override_limits: [] # existing comment\n",
        "override_limits: [{name: keep, file_globs: [keep.py], max_lines_per_file: 100}]\n",
        (
            "override_limits: [{name: keep, file_globs: [keep.py], max_lines_per_file: 100},\n"
            "  {name: tail, file_globs: [tail.py], max_lines_per_file: 90}]\n"
        ),
        (
            "override_limits:\n  - name: keep\n    file_globs:\n      - \"keep.py\"\n"
            "    max_lines_per_file: 100\n"
        ),
        "override_limits: [ # head\n {name: keep, note: extra}]\n",
    ],
)
def test_write_baseline_preserves_existing_yaml_bytes(tmp_path: Path, override_suffix: str) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    before = _policy_prefix() + override_suffix
    cfg_path.write_text(before, encoding="utf-8")
    _write_layout(tmp_path, {"wide.py": "x\n" * 3, "keep.py": "y\n", "tail.py": "z\n"})
    assert write_baseline(tmp_path) == 0
    after = cfg_path.read_text(encoding="utf-8")
    _assert_only_inserted(before, after)
    if "# existing comment" in override_suffix:
        assert "# existing comment" in after
    if "# head" in override_suffix:
        assert "# head" in after
    if "note: extra" in override_suffix:
        cfg = yaml.safe_load(after)
        assert cfg["override_limits"][0].get("note") == "extra"
    assert run_file_limits_scan(tmp_path, yaml.safe_load(after)) is False
    assert write_baseline(tmp_path) == 0
    assert cfg_path.read_text(encoding="utf-8") == after


def test_write_baseline_leading_space_filename_resolves_and_is_idempotent(tmp_path: Path) -> None:
    from tests.test_file_limits_baseline import _cfg_yaml

    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(_cfg_yaml(max_lines_per_file=2, max_lines_per_function=2), encoding="utf-8")
    spaced = " a.py"
    body = "def f():\n x=1\n return x\n"
    _write_layout(tmp_path, {spaced: body})
    assert write_baseline(tmp_path) == 0
    after = cfg_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(after)
    assert run_file_limits_scan(tmp_path, cfg) is False
    assert write_baseline(tmp_path) == 0
    assert cfg_path.read_text(encoding="utf-8") == after


@pytest.mark.parametrize(
    "override_suffix",
    [
        "override_limits:\n",
        "override_limits: null\n",
        "override_limits: {}\n",
        "override_limits: null # keep comment\n",
    ],
)
def test_write_baseline_populates_empty_override_limits_value(
    tmp_path: Path, override_suffix: str
) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    before = _policy_prefix() + override_suffix
    cfg_path.write_text(before, encoding="utf-8")
    _write_layout(tmp_path, {"wide.py": "x\n" * 3})
    assert write_baseline(tmp_path) == 0
    after = cfg_path.read_text(encoding="utf-8")
    if "# keep comment" in override_suffix:
        assert "# keep comment" in after
    cfg = yaml.safe_load(after)
    assert any(str(e.get("name", "")).startswith("baseline-") for e in cfg["override_limits"])
    assert run_file_limits_scan(tmp_path, cfg) is False


def test_write_baseline_inserts_override_limits_before_document_end(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    before = _policy_prefix() + "...\n"
    cfg_path.write_text(before, encoding="utf-8")
    _write_layout(tmp_path, {"wide.py": "x\n" * 3})
    assert write_baseline(tmp_path) == 0
    after = cfg_path.read_text(encoding="utf-8")
    prefix_end = before.index("...")
    assert after[:prefix_end] == before[:prefix_end]
    assert after.index("override_limits:") < after.index("...")
    assert "..." in after
    assert run_file_limits_scan(tmp_path, yaml.safe_load(after)) is False


@pytest.mark.parametrize(
    "style,glob_literal",
    [
        ("flow", "a].py"),
        ("flow", "a[1].py"),
        ("flow", 'a"b.py'),
        ("flow", "a:#.py"),
        ("flow", " a.py"),
        ("flow", "a.py "),
        ("block", "a].py"),
        ("block", "a[1].py"),
        ("block", 'a"b.py'),
        ("block", "a:#.py"),
    ],
)
def test_write_baseline_appends_with_special_chars_in_quoted_globs(
    tmp_path: Path, style: str, glob_literal: str
) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    quoted = yaml.dump(glob_literal, default_style='"', width=2**16).strip()
    if style == "flow":
        override = (
            f"override_limits: [{{name: keep, file_globs: [{quoted}], max_lines_per_file: 100}}]\n"
        )
    else:
        override = (
            "override_limits:\n"
            "  - name: keep\n"
            "    file_globs:\n"
            f"      - {quoted}\n"
            "    max_lines_per_file: 100\n"
        )
    before = _policy_prefix() + override
    cfg_path.write_text(before, encoding="utf-8")
    _write_layout(tmp_path, {"wide.py": "x\n" * 3, glob_literal: "y\n"})
    assert write_baseline(tmp_path) == 0
    after = cfg_path.read_text(encoding="utf-8")
    _assert_only_inserted(before, after)
    assert quoted in after
    cfg = yaml.safe_load(after)
    assert cfg["override_limits"][0]["file_globs"] == [glob_literal]
    assert run_file_limits_scan(tmp_path, cfg) is False
