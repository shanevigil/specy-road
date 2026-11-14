"""scripts/ruff_quality_baseline.py: per-file ruff family counts, a report only."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "ruff_quality_baseline", ROOT / "scripts" / "ruff_quality_baseline.py"
)
quality = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(quality)

# Ten `if`s is McCabe 11, over ruff's default of 10. The waived copy still counts
# for C901 (`--ignore-noqa`) and does not count for the other families.
_BRANCHES = "".join("    if x:\n        x = x[1:]\n" for _ in range(10))
QUALITY_PY = (
    "def complex_counted(x):\n"
    f"{_BRANCHES}"
    "    return x\n"
    "\n"
    "def complex_waived(x):  # noqa: C901\n"
    f"{_BRANCHES}"
    "    return x\n"
    "\n"
    "count = 0\n"
    "\n"
    "def bump():\n"
    '    """Documented, so D103 stays quiet."""\n'
    "    global count\n"
    "    count += 1\n"
    "    return count\n"
    "\n"
    "def BadName():\n"
    '    """Documented."""\n'
    "    return 1\n"
    "\n"
    "def public_missing_doc():\n"
    "    return 1\n"
    "\n"
    "def mutable(items=[]):\n"
    '    """Documented."""\n'
    "    return items\n"
    "\n"
    "def mutable_waived(items=[]):  # noqa: B006\n"
    '    """Documented."""\n'
    "    return items\n"
    "\n"
    "class Box:\n"
    "    def method(self):\n"
    "        return 1\n"
    "\n"
    "def branched(flag):\n"
    '    """Documented."""\n'
    "    if flag:\n"
    "        return 1\n"
    "    else:\n"
    "        return 2\n"
    "\n"
    "def assigned(value):\n"
    '    """Documented."""\n'
    "    if value:\n"
    "        result = 1\n"
    "    else:\n"
    "        result = 2\n"
    "    return result\n"
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_counts_findings_per_file_and_family_under_the_areas(tmp_path: Path) -> None:
    _write(tmp_path, "specy_road/quality.py", QUALITY_PY)
    _write(tmp_path, "specy_road/clean.py", 'def ok():\n    """Documented."""\n    return 1\n')
    _write(
        tmp_path, "scripts/also.py",
        'def also(items=[]):\n    """Documented."""\n    return items\n',
    )
    _write(tmp_path, "tests/t.py", "def test_ok():\n    assert True\n")
    _write(tmp_path, "elsewhere/wide.py", "def also(items=[]):\n    return items\n")

    assert quality.counts(tmp_path) == {
        "scripts/also.py": {"B": 1},
        "specy_road/quality.py": {
            "C901": 2,
            "PL": 1,
            "B": 1,
            "SIM": 1,
            "RET": 1,
            "N": 1,
            "D102/D103": 4,
        },
        "tests/t.py": {"D102/D103": 1},
    }


@pytest.mark.parametrize(("files", "expected"), [
    ({"a.py": {"C901": 2, "PL": 1}}, {"b.py": {"C901": 2, "PL": 1}}),
    (
        {"a.py": {"C901": 2, "PL": 1}, "b.py": {"B": 4, "C901": 3}},
        {"b.py": {"C901": 5, "PL": 1, "B": 4}},
    ),
    ({"c.py": {"B": 1}}, {"c.py": {"B": 1}}),
])
def test_transfer_sums_old_families_onto_new(tmp_path: Path, monkeypatch, files, expected) -> None:
    baseline = tmp_path / "ruff_quality_baseline.json"
    baseline.write_text(json.dumps({"commit": "abc", "files": files}), encoding="utf-8")
    monkeypatch.setattr(quality, "BASELINE", baseline)

    assert quality.main(["--transfer", "a.py", "b.py"]) == 0

    written = json.loads(baseline.read_text(encoding="utf-8"))
    assert written["commit"] == "abc"
    assert written["files"] == expected


@pytest.mark.parametrize(("files", "current", "expected"), [
    (
        {"a.py": {"C901": 3, "PL": 2}},
        {"a.py": {"C901": 1, "PL": 2}},
        {"a.py": {"C901": 1, "PL": 2}},
    ),
    (
        {"a.py": {"C901": 1}},
        {"a.py": {"C901": 4}},
        {"a.py": {"C901": 1}},
    ),
    (
        {"a.py": {"PL": 1}},
        {"a.py": {"PL": 1}, "b.py": {"PL": 2}},
        {"a.py": {"PL": 1}},
    ),
    (
        {"a.py": {"C901": 1}},
        {"a.py": {"C901": 1, "B": 2}},
        {"a.py": {"C901": 1}},
    ),
    ({"a.py": {"C901": 2}}, {}, {}),
    (
        {"a.py": {"C901": 2, "PL": 1}},
        {"a.py": {"PL": 1}},
        {"a.py": {"PL": 1}},
    ),
])
def test_shrink_lowers_entries_and_never_raises(
    tmp_path: Path, monkeypatch, files, current, expected,
) -> None:
    baseline = tmp_path / "ruff_quality_baseline.json"
    original = json.dumps({"commit": "abc", "files": files}, indent=2) + "\n"
    baseline.write_text(original, encoding="utf-8")
    monkeypatch.setattr(quality, "BASELINE", baseline)
    monkeypatch.setattr(quality, "counts", lambda *args, **kwargs: current)

    assert quality.main(["--shrink"]) == 0

    written = json.loads(baseline.read_text(encoding="utf-8"))
    assert written["commit"] == "abc"
    assert written["files"] == expected
    if expected == files:
        assert baseline.read_text(encoding="utf-8") == original


PICKUP = "542aa46c29cf4765c20b6879d322cc53422b1da3"
# Same filename, from bundled_scripts into the package. This is the move list the
# pickup-tree check reads: promotion removes the planning tree, and this file stays.
_MOVED_FROM = {
    f"specy_road/{name}": f"specy_road/bundled_scripts/{name}"
    for name in (
        "brainstorm_chat.py",
        "brainstorm_promote.py",
        "brainstorm_prompt.py",
        "brainstorm_research.py",
        "brainstorm_session.py",
        "brief_acceptance.py",
        "grind_session_cleanup.py",
        "planning_artifacts.py",
        "planning_sheet_bootstrap.py",
        "pm_gui_git_remote_verify.py",
        "registration_pickup_commit.py",
        "repo_ops.py",
        "review_defer.py",
        "roadmap_chunk_router_pick.py",
        "roadmap_chunk_utils.py",
        "roadmap_crud_ops.py",
        "roadmap_gui_lib.py",
        "roadmap_gui_remote.py",
        "roadmap_gui_settings.py",
        "roadmap_gui_tree.py",
        "roadmap_index.py",
        "roadmap_layout.py",
        "roadmap_load.py",
        "roadmap_load_at_ref.py",
        "roadmap_node_keys.py",
        "roadmap_outline_ops.py",
        "roadmap_outline_renumber.py",
        "role_prompt_cli.py",
        "role_prompt_rework.py",
        "session_plan_git.py",
        "validate_stale_commands.py",
        "worker_cli_render.py",
        "worker_cli_sync.py",
    )
}
# Same filename, from the package into specy_road/orchestration/workers/ (the worker runtime move);
# a module that came from bundled_scripts maps to its path there.
_MOVED_FROM.update({
    f"specy_road/orchestration/workers/{path.name}": _MOVED_FROM.get(
        f"specy_road/{path.name}", f"specy_road/{path.name}"
    )
    for path in (ROOT / "specy_road" / "orchestration" / "workers").glob("worker_*.py")
})


def _in_pickup_tree(path: str, present: set[str], moved_from: dict[str, str]) -> bool:
    """In the pickup tree, or moved_from maps it to a path that is."""
    old = moved_from.get(path)
    return path in present or (old is not None and old in present)


def test_baseline_records_the_pickup_commit_and_only_its_files() -> None:
    data = json.loads((ROOT / "scripts" / "ruff_quality_baseline.json").read_text(encoding="utf-8"))
    assert data["commit"] == PICKUP
    # One rule: the tree check needs the commit object. A depth-1 checkout does not have it.
    if subprocess.run(
        ["git", "cat-file", "-e", f"{data['commit']}^{{commit}}"],
        cwd=ROOT, capture_output=True,
    ).returncode != 0:
        pytest.skip("recorded commit is not in this checkout")
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", data["commit"]],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    present = set(listed.splitlines())
    outside = sorted(
        path for path in data["files"] if not _in_pickup_tree(path, present, _MOVED_FROM)
    )
    assert outside == []
    assert _in_pickup_tree("specy_road/not_a_pickup_file.py", present, _MOVED_FROM) is False


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_rewrite_counts_the_commit_tree_not_the_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "specy_road").mkdir(parents=True)
    kept = repo / "specy_road" / "kept.py"
    kept.write_text(
        'def kept(items=[]):\n    """Documented."""\n    return items\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "specy_road/kept.py"], cwd=repo, check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Baseline Test",
        "GIT_AUTHOR_EMAIL": "baseline-test@example.com",
        "GIT_COMMITTER_NAME": "Baseline Test",
        "GIT_COMMITTER_EMAIL": "baseline-test@example.com",
    }
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "pickup"],
        cwd=repo, check=True, env=env,
    )
    kept.write_text(
        'def kept(items=[]):\n    """Documented."""\n    return items\n\n'
        'def also(items=[]):\n    """Documented."""\n    return items\n',
        encoding="utf-8",
    )
    (repo / "specy_road" / "extra.py").write_text(
        'def extra(items=[]):\n    """Documented."""\n    return items\n',
        encoding="utf-8",
    )
    baseline = repo / "out.json"
    monkeypatch.setattr(quality, "REPO", repo)
    monkeypatch.setattr(quality, "BASELINE", baseline)

    assert quality.main([]) == 0

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    written = json.loads(baseline.read_text(encoding="utf-8"))
    assert written["commit"] == head
    assert written["files"] == {"specy_road/kept.py": {"B": 1}}


def test_report_names_rises_new_files_and_family_totals() -> None:
    baseline = {"rose.py": {"C901": 1, "PL": 2}, "fell.py": {"B": 4}, "same.py": {"N": 1}}
    current = {
        "rose.py": {"C901": 3, "PL": 2, "SIM": 1},
        "fell.py": {"B": 1},
        "same.py": {"N": 1},
        "new.py": {"RET": 2},
    }

    assert quality.report(baseline, current) == [
        "  new.py: RET 2 (not in the baseline)",
        "  rose.py C901: 1 -> 3 (+2)",
        "  rose.py SIM: 0 -> 1 (+1)",
        "  C901: 1 -> 3 (+2)",
        "  PL: 2 -> 2 (+0)",
        "  B: 4 -> 1 (-3)",
        "  SIM: 0 -> 1 (+1)",
        "  RET: 0 -> 2 (+2)",
        "  N: 1 -> 1 (+0)",
        "  D102/D103: 0 -> 0 (+0)",
    ]
