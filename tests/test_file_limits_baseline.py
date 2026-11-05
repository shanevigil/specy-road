"""file-limits --write-baseline, failure hint, and upgrade failure counts (M15.7)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

from specy_road.file_limits_baseline import (
    append_baseline_yaml_text,
    bucket_failing_files,
    collect_failing_file_metrics,
    failure_hint,
    format_baseline_entries,
    literal_path_glob,
    plan_baseline_append,
    round_up_to_step,
    write_baseline,
)
from specy_road.file_limits_engine import run_file_limits_scan
from specy_road.bundled_scripts.upgrade import run_upgrade
from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env
from tests.upgrade_repo_helpers import old_repo


def _write_layout(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _cfg_yaml(**extra: object) -> str:
    base = {
        "max_lines_per_file": 10,
        "max_lines_per_function": 5,
        "applies_to_globs": ["**/*.py"],
    }
    base.update(extra)
    return yaml.safe_dump(base, sort_keys=False)


def test_round_up_to_step_pins_bucket_caps() -> None:
    assert round_up_to_step(11, 50) == 50
    assert round_up_to_step(50, 50) == 50
    assert round_up_to_step(51, 50) == 100
    assert round_up_to_step(6, 20) == 20
    assert round_up_to_step(0, 20) == 0


def test_bucket_failing_files_groups_by_rounded_caps() -> None:
    from specy_road.file_limits_baseline import FailingFileMetrics

    metrics = [
        FailingFileMetrics("a.py", 11, 6),
        FailingFileMetrics("b.py", 12, 7),
        FailingFileMetrics("c.py", 60, 0),
    ]
    buckets = bucket_failing_files(metrics)
    assert buckets[(50, 20)] == ["a.py", "b.py"]
    assert buckets[(100, 0)] == ["c.py"]


def test_format_baseline_entries_uses_date_and_index() -> None:
    text = format_baseline_entries({(50, 20): ["x.py"]}, today="2026-11-05", start_index=2)
    assert "name: baseline-2026-11-05-2" in text
    assert '      - "x.py"' in text
    assert "max_lines_per_file: 50" in text
    assert "max_lines_per_function: 20" in text


def test_append_keeps_existing_comments(tmp_path: Path) -> None:
    raw = "# keep me\nmax_lines_per_file: 5\napplies_to_globs:\n  - \"**/*.py\"\n"
    block = '  - name: baseline-2026-11-05-1\n    file_globs:\n      - "a.py"\n    max_lines_per_file: 50\n'
    out = append_baseline_yaml_text(raw, block)
    assert "# keep me" in out
    assert "override_limits:" in out
    assert yaml.safe_load(out)["override_limits"][0]["name"] == "baseline-2026-11-05-1"


def test_write_baseline_inserts_inside_override_limits_before_roadmap_keys(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(
        "max_lines_per_file: 10\n"
        "max_lines_per_function: 5\n"
        "applies_to_globs:\n  - \"**/*.py\"\n"
        "override_limits:\n"
        "  - name: existing\n"
        "    file_globs:\n      - \"keep.py\"\n"
        "    max_lines_per_file: 100\n"
        "roadmap_manifest_max_lines: 500\n"
        "roadmap_json_chunk_max_lines: 500\n",
        encoding="utf-8",
    )
    _write_layout(tmp_path, {"wide.py": "x\n" * 11})
    assert write_baseline(tmp_path) == 0
    text = cfg_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert cfg["roadmap_manifest_max_lines"] == 500
    assert cfg["roadmap_json_chunk_max_lines"] == 500
    names = [entry["name"] for entry in cfg["override_limits"]]
    baseline_names = [n for n in names if str(n).startswith("baseline-")]
    assert "existing" in names
    assert len(baseline_names) == 1
    assert names.index("existing") < names.index(baseline_names[0])
    assert text.index("baseline-") < text.index("roadmap_manifest_max_lines")
    assert run_file_limits_scan(tmp_path, cfg) is False


def test_write_baseline_with_override_limits_empty_flow_list(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(
        "max_lines_per_file: 2\napplies_to_globs:\n  - \"**/*.py\"\noverride_limits: []\n",
        encoding="utf-8",
    )
    _write_layout(tmp_path, {"wide.py": "x\n" * 3})
    assert write_baseline(tmp_path) == 0
    text = cfg_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert isinstance(cfg["override_limits"], list)
    assert any(str(e.get("name", "")).startswith("baseline-") for e in cfg["override_limits"])
    assert run_file_limits_scan(tmp_path, cfg) is False


def test_write_baseline_with_double_quote_in_filename(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(_cfg_yaml(max_lines_per_file=2), encoding="utf-8")
    quoted = 'a"b.py'
    _write_layout(tmp_path, {quoted: "x\n" * 3})
    assert write_baseline(tmp_path) == 0
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    globs = [
        g
        for entry in cfg["override_limits"]
        if str(entry.get("name", "")).startswith("baseline-")
        for g in entry.get("file_globs") or []
    ]
    assert quoted in globs or literal_path_glob(quoted) in globs
    assert run_file_limits_scan(tmp_path, cfg) is False


def test_write_baseline_literal_glob_does_not_widen_to_similar_names(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(_cfg_yaml(max_lines_per_file=2), encoding="utf-8")
    bracket_name = "a[1].py"
    _write_layout(tmp_path, {bracket_name: "x\n" * 3})
    assert write_baseline(tmp_path) == 0
    text = cfg_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert literal_path_glob(bracket_name) in text
    assert run_file_limits_scan(tmp_path, cfg) is False
    before = text
    assert write_baseline(tmp_path) == 0
    assert cfg_path.read_text(encoding="utf-8") == before
    _write_layout(tmp_path, {"a1.py": "x\n" * 3})
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert run_file_limits_scan(tmp_path, cfg) is True


def test_write_baseline_buckets_pass_and_rerun_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(_cfg_yaml(), encoding="utf-8")
    _write_layout(
        tmp_path,
        {
            "wide.py": "x\n" * 11,
            "chunky.py": "def big():\n" + "    pass\n" * 6,
        },
    )
    assert write_baseline(tmp_path) == 0
    text = cfg_path.read_text(encoding="utf-8")
    assert re.search(r"baseline-\d{4}-\d{2}-\d{2}-1", text)
    assert "wide.py" in text
    assert "chunky.py" in text
    cfg = yaml.safe_load(text)
    assert run_file_limits_scan(tmp_path, cfg) is False
    before = text
    assert write_baseline(tmp_path) == 0
    assert cfg_path.read_text(encoding="utf-8") == before


def test_write_baseline_dry_run_prints_without_writing(tmp_path: Path, capsys) -> None:
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "file-limits.yaml").write_text(_cfg_yaml(), encoding="utf-8")
    _write_layout(tmp_path, {"wide.py": "x\n" * 11})
    raw = (tmp_path / "constraints" / "file-limits.yaml").read_text(encoding="utf-8")
    assert write_baseline(tmp_path, dry_run=True) == 0
    assert (tmp_path / "constraints" / "file-limits.yaml").read_text(encoding="utf-8") == raw
    assert "max_lines_per_file:" in capsys.readouterr().out


def test_failing_cli_prints_hint_passing_does_not(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "file-limits.yaml").write_text(_cfg_yaml(), encoding="utf-8")
    _write_layout(tmp_path, {"wide.py": "x\n" * 11})
    fail = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_file_limits.py"),
            "--repo-root",
            str(tmp_path),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert fail.returncode == 1
    hint = failure_hint("constraints/file-limits.yaml")
    assert hint in fail.stderr
    _write_layout(tmp_path, {"wide.py": "x\n"})
    ok = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_file_limits.py"),
            "--repo-root",
            str(tmp_path),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0
    assert hint not in ok.stdout
    assert hint not in ok.stderr


def test_plan_baseline_append_empty_when_nothing_fails(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    cfg_path = tmp_path / "constraints" / "file-limits.yaml"
    cfg_path.write_text(_cfg_yaml(), encoding="utf-8")
    _write_layout(tmp_path, {"ok.py": "x\n"})
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert plan_baseline_append(cfg_path, cfg, tmp_path) == ""
    assert collect_failing_file_metrics(tmp_path, cfg) == []


def test_upgrade_reports_file_limits_counts_without_failing(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "over_cap.py").write_text("x\n" * 450, encoding="utf-8")
    capsys.readouterr()
    code = run_upgrade(root)
    out = capsys.readouterr().out
    assert "== file-limits" in out
    assert "failures:" in out
    assert "failures before upgrade:" not in out
    assert "failures after upgrade:" not in out
    assert "Measurement rules may have changed" in out
    assert "--write-baseline" in out
    assert code == 0
