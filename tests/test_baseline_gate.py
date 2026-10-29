"""Baseline gate configuration: ``baseline_cmd`` resolution and grind-session pass-through.

The gate's behaviour is tested end to end in ``test_baseline_gate_cli.py``.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.grind_session_args import (
    parse_grind_session_args,
    pickup_args,
)
from specy_road.git_workflow_config import resolve_baseline_cmd, validate_git_workflow_dict

_GW = "version: 1\nintegration_branch: main\nremote: origin\n"


def _write_gw(root: Path, extra: str = "") -> None:
    (root / "roadmap").mkdir(exist_ok=True)
    (root / "roadmap" / "git-workflow.yaml").write_text(_GW + extra, encoding="utf-8")


# ---------------------------------------------------------------------------
# Resolution: CLI > git-workflow.yaml > none
# ---------------------------------------------------------------------------


def test_schema_accepts_baseline_cmd() -> None:
    data = {"version": 1, "integration_branch": "main", "remote": "origin",
            "baseline_cmd": "make test"}
    assert validate_git_workflow_dict(data) is None


def test_yaml_sets_the_default(tmp_path) -> None:
    _write_gw(tmp_path, "baseline_cmd: make test\n")
    assert resolve_baseline_cmd(tmp_path, cli=None) == "make test"


def test_cli_wins_over_yaml(tmp_path) -> None:
    _write_gw(tmp_path, "baseline_cmd: make test\n")
    assert resolve_baseline_cmd(tmp_path, cli="pytest -q") == "pytest -q"


def test_empty_cli_turns_the_yaml_default_off(tmp_path) -> None:
    _write_gw(tmp_path, "baseline_cmd: make test\n")
    assert resolve_baseline_cmd(tmp_path, cli="") is None


def test_no_config_means_no_baseline(tmp_path) -> None:
    assert resolve_baseline_cmd(tmp_path, cli=None) is None


# ---------------------------------------------------------------------------
# grind-session: forwarded to every pickup
# ---------------------------------------------------------------------------


def test_grind_passes_baseline_flags_to_pickup() -> None:
    args = parse_grind_session_args(
        ["--baseline-cmd", "make test", "--baseline-warn", "--repo-root", "/tmp/x"]
    )
    out = pickup_args(args, Path("/tmp/x"))
    assert out[out.index("--baseline-cmd") + 1] == "make test"
    assert "--baseline-warn" in out


def test_grind_forwards_an_empty_baseline_to_turn_the_default_off() -> None:
    args = parse_grind_session_args(["--baseline-cmd", "", "--repo-root", "/tmp/x"])
    out = pickup_args(args, Path("/tmp/x"))
    assert out[out.index("--baseline-cmd") + 1] == ""


def test_grind_without_baseline_flags_forwards_none() -> None:
    out = pickup_args(parse_grind_session_args(["--repo-root", "/tmp/x"]), Path("/tmp/x"))
    assert "--baseline-cmd" not in out and "--baseline-warn" not in out
