#!/usr/bin/env python3
"""Measure the M16 lean-core metrics against constraints/lean-baseline.json.

Every number is a measurement, never a gate: the CI coverage floor
([tool.coverage.report] fail_under in pyproject.toml) is the only check M16.1.7
adds. Files are the ones git tracks at HEAD, read from the working tree, so the
recorded commit is the one measured when ``clean`` is true. Subprocesses use the
interpreter running this script; run it from an environment with every extra
installed (``pip install -r requirements-ci.txt`` plus ``-e '.[review,gui]'``).

Usage:
    python scripts/lean_metrics.py --check     # measure and print deltas against the
                                               # M16.1.7 baseline, then the line-width
                                               # report (scripts/line_width_baseline.py)
                                               # and the ruff quality-family report
                                               # (scripts/ruff_quality_baseline.py).
                                               # Line counts and suite time never fail it.
    python scripts/lean_metrics.py --record-end-state
                                               # measure rc5 and write it as the
                                               # rc5_end_state section, leaving the
                                               # M16.1.7 baseline numbers in place
    python scripts/lean_metrics.py --contexts  # covered arcs per test -> work/lean/contexts.json

The M16.1.7 baseline stays as committed. M16.8.1 writes rc5 beside it;
``--check`` prints deltas and the gates in its docstring. ``--contexts`` is
opt-in and never runs in CI. With no mode, the script exits 2 and writes nothing.
"""

from __future__ import annotations

import argparse
import ast
import importlib.metadata
import itertools
import json
import os
import platform
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "constraints" / "lean-baseline.json"
LEAN_WORK = REPO / "work" / "lean"
COMMAND_MAP = REPO / "tests" / "parity" / "command_map.yaml"
SCHEMAS = REPO / "specy_road" / "templates" / "project" / "schemas"
WORKERS = 4
SUITE_RUNS = 3
HELP_RUNS = 5
# M16.4.4's bound: 74 top-level names at claim, plus milestone and planning, minus the 15
# retired names. It records that the planning figure of 56 no longer holds, because five
# commands were registered after that figure was written and were not retired.
CANONICAL_BOUND = 61
PLANNING_COMMAND_FIGURE = 56
PYTEST = ["-m", "pytest", "-n", str(WORKERS), "-p", "no:cacheprovider", "-q"]
VALIDATE_ARGS = ["validate", "--repo-root", "tests/fixtures/specy_road_dogfood"]
# What the `specy-road` console script runs; cwd=REPO puts this checkout's package first.
CLI_BOOT = "import sys; from specy_road.cli import main; sys.argv[0] = 'specy-road'; main()"
CONTEXT_ENV = "SPECY_ROAD_LEAN_CONTEXT"
AREAS = ("specy_road", "scripts", "tests")
DOCS_PATHSPECS = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    ":(glob)docs/**/*.md",
    ":(glob)constitution/*.md",
    ":(glob)suggested_prompts/*.md",
)
NOQA_C901 = re.compile(r"#\s*noqa:[^#\n]*\bC901\b")
COLLECTED = re.compile(r"(\d+) tests? collected")

# Subsystems ported from the slimming analysis's module map (01-code.md section 1).
# Path rules come first; then the first stem rule that matches a module's file
# name (a test file's without its test_ prefix or _test suffix) wins.
PATH_RULES = (
    ("parity harness", re.compile(r"^tests/parity/")),
    ("fixtures", re.compile(r"^tests/fixtures/")),
    ("worker/orchestration", re.compile(r"^specy_road/orchestration/")),
)
STEM_RULES = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("PM UI server", r"^(gui|roadmap_gui|pm_)"),
        (
            "worker/orchestration",
            r"^(worker|roster|model|effective_model|orchestrat|harness_(binary|facts|launch)"
            r"|headless|hook_adapters|tool_call_guard|session_(cli|overlap|presence|end)"
            r"|shared_checkout|sandbox|chore|decision|lessons|role_prompt|prompt_channel"
            r"|claude_|cursor_|context_meter|orphaned_claims)",
        ),
        (
            "review/handoff/gate",
            r"^(review|handoff|rework|red_green|mark_implementation_reviewed|ready"
            r"|steering_gate|llm_throughput|delta_review|resumed_delta|strong_review"
            r"|human_acceptance|sibling_repo_approvals|sheet_edits_keep_approvals|fix_round"
            r"|dynamic_routing|gate_config|run_record)",
        ),
        (
            "pickup/grind",
            r"^(do_next|grind_session|session_plan|abort_task_pickup|registration_pickup"
            r"|on_complete|pick|claim|unauthored|baseline_gate)",
        ),
        (
            "upgrade/init/agent files",
            r"^(upgrade|init|cli_init|refresh_|specyrd|agents?_|managed_block|skill"
            r"|harness_instruction|validate_stale_commands|version_|behaviour_changes"
            r"|constitution|update_specy_road|toolkit_version|running_toolkit_version"
            r"|generated_files|ignore_report|changelog_check|schema_revision|docs_"
            r"|package_data|prerelease|release|check_release|post_release|verify_wheel"
            r"|project_layouts|enforced_rules|m13_(7|12)_)",
        ),
        (
            "finish/land",
            r"^(finish|milestone|nested|start_milestone|reconcile_milestone|open_milestone"
            r"|sibling_repos|git_milestone|rollup|dependency_rollup|branch_cleanup)",
        ),
        ("brainstorm", r"^brainstorm"),
        ("archive/history/search", r"^(archive|deepen_archive|history|search|impact)"),
        (
            "brief/digest/export/planning",
            r"^(brief|generate_brief|digest|export|planning|scaffold_planning"
            r"|author_approach|sync_planning|text_sections|contract_citations|context_notice)",
        ),
        ("validate/file-limits", r"^(validate|file_limits|lean_)"),
        (
            "registry/git/worktree/doctor",
            r"^(registry|git_|worktree|linked_worktrees|doctor|reconcile_branch|branches"
            r"|integrity|feature_rm_registry|repo_|touch_zone|shared_zones|safe_write"
            r"|runtime_|(ops_|setup_)?writers_refuse_links)",
        ),
        (
            "roadmap graph/CRUD",
            r"^(roadmap|node_|effective_dependency|move_node|remove_node|outline|rename_refs"
            r"|written_entry|workflow_prefs|governance|doc_links|why_blocked|set_gate_status"
            r"|phase_root_chunk|one_readiness_rule|planned_test_changes)",
        ),
        # cli_init matched the rule above; every other cli_* module and test is dispatch.
        ("cli dispatch", r"^(cli|__main__)(_|$)"),
    )
)


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, check=False, **kwargs)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout


def tracked(*pathspecs: str) -> list[str]:
    return sorted(filter(None, git("ls-files", "-z", "--", *pathspecs).split("\0")))


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


def subsystem(rel: str) -> str:
    for name, rule in PATH_RULES:
        if rule.search(rel):
            return name
    stem = Path(rel).stem.removeprefix("test_").removesuffix("_test")
    return next((name for name, rule in STEM_RULES if rule.search(stem)), "other")


def lines_and_files(paths: Iterable[str], group: Callable[[str], str]) -> dict:
    """``{group: {files, lines}}`` plus a ``total`` entry."""
    out: dict[str, dict[str, int]] = {}
    for rel in paths:
        entry = out.setdefault(group(rel), {"files": 0, "lines": 0})
        entry["files"] += 1
        entry["lines"] += len(read(rel).splitlines())
    groups = dict(sorted(out.items()))
    groups["total"] = {k: sum(e[k] for e in out.values()) for k in ("files", "lines")}
    return groups


def docs_group(rel: str) -> str:
    return rel.split("/", 1)[0] if "/" in rel else "root files"


def is_test_file(rel: str) -> bool:
    name = Path(rel).name
    return name.startswith("test_") or name.endswith("_test.py")


def test_functions(paths: Iterable[str]) -> int:
    """``test*`` functions at module level or in ``Test*`` classes (pytest's defaults)."""
    count = 0
    for rel in filter(is_test_file, paths):
        for node in ast.parse(read(rel)).body:
            is_test_class = isinstance(node, ast.ClassDef) and node.name.startswith("Test")
            body = node.body if is_test_class else [node]
            count += sum(
                isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef) and f.name.startswith("test")
                for f in body
            )
    return count


def collected_items() -> int:
    proc = run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"])
    return int(COLLECTED.findall(proc.stdout)[-1])


def ruff_counts(*options: str) -> dict[str, int]:
    """Ruff findings per area; ruff exits 1 when it finds any, so the exit is not checked."""
    proc = run(["ruff", "check", "--no-cache", "--output-format", "json", *options, *AREAS])
    findings = json.loads(proc.stdout)
    return per_area([Path(f["filename"]).resolve().relative_to(REPO).parts[0] for f in findings])


def per_area(first_parts: list[str]) -> dict[str, int]:
    counts = {area: first_parts.count(area) for area in AREAS}
    return {**counts, "total": sum(counts.values())}


def noqa_c901(py_files: list[str]) -> dict[str, int]:
    return per_area(
        [rel.split("/", 1)[0] for rel in py_files for _ in NOQA_C901.finditer(read(rel))]
    )


def command_words(text: str) -> tuple[str, bool]:
    """``"specy-road doctor --prune"`` -> ``("specy-road doctor", True)``.

    Words before the first option are the command. A word after that option is its value.
    """
    words = str(text).split()
    command: list[str] = []
    for word in words:
        if word.startswith("-"):
            return " ".join(command), True
        command.append(word)
    return " ".join(command), False


def retired_top_level_names(rows: list) -> set[str]:
    """Top-level names a command_map.yaml row retires, as M16.4.4 defines it.

    A row counts only when ``old`` is ``specy-road NAME`` with no options and ``new`` is
    neither that command nor under it. A subcommand row or a flag row retires nothing.
    """
    retired: set[str] = set()
    for row in rows:
        old, options = command_words(str(row.get("old") or ""))
        new = command_words(str(row.get("new") or ""))[0]
        words = old.split()
        moved_under_itself = bool(new) and (new == old or new.startswith(old + " "))
        if len(words) == 2 and words[0] == "specy-road" and not options and not moved_under_itself:
            retired.add(words[1])
    return retired


def commands() -> dict:
    """The canonical command count as M16.4.4 defines it.

    Distinct registered top-level ``specy-road`` names, except ``version``, minus the names
    ``retired_top_level_names`` finds. Those retired names that are still registered are the
    alias count.
    """
    code = (
        "import json; from specy_road.cli import registered_agent_command_names as r; "
        "print(json.dumps(sorted(r()['specy-road'])))"
    )
    names = set(json.loads(run([sys.executable, "-c", code]).stdout)) - {"version"}
    rows = (yaml.safe_load(COMMAND_MAP.read_text(encoding="utf-8")) or {}).get("rows") or []
    aliases = sorted(retired_top_level_names(rows) & names)
    return {
        "canonical": len(names) - len(aliases),
        "aliases": len(aliases),
        "alias_names": aliases,
        "canonical_names": sorted(names - set(aliases)),
    }


def config_keys() -> dict[str, int]:
    """Top-level git-workflow.yaml keys and orchestration.yaml policy keys, from their schemas."""
    workflow = json.loads((SCHEMAS / "git-workflow.schema.json").read_text(encoding="utf-8"))
    orchestration = json.loads((SCHEMAS / "orchestration.schema.json").read_text(encoding="utf-8"))
    counts = {
        "git_workflow": len(workflow["properties"]),
        "orchestration_policy": len(orchestration["$defs"]["policy"]["properties"]),
    }
    return {**counts, "total": sum(counts.values())}


def validate_imports() -> dict:
    """Distinct modules imported over every Python process `specy-road validate` starts."""
    env = {**os.environ, "PYTHONPROFILEIMPORTTIME": "1"}
    stderr = run([sys.executable, "-c", CLI_BOOT, *VALIDATE_ARGS], env=env).stderr
    rows = [
        line.split("|")[-1].strip()
        for line in stderr.splitlines()
        if line.startswith("import time:")
    ]
    modules = {name for name in rows if name != "imported package"}
    return {
        "command": "specy-road " + " ".join(VALIDATE_ARGS),
        "method": "PYTHONPROFILEIMPORTTIME=1; distinct module names over every Python process",
        "processes": rows.count("imported package"),
        "specy_road_modules": sum(m.split(".")[0] == "specy_road" for m in modules),
        "all_modules": len(modules),
    }


def timed(args: list[str], env: dict[str, str] | None = None) -> tuple[float, int]:
    start = time.perf_counter()
    proc = run(args, env=env)
    return round(time.perf_counter() - start, 2), proc.returncode


def coverage_off_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}


def validate_help_seconds() -> float:
    help_args = [sys.executable, "-c", CLI_BOOT, "validate", "--help"]
    return statistics.median(timed(help_args)[0] for _ in range(HELP_RUNS))


def suite_seconds() -> dict:
    runs = [timed([sys.executable, *PYTEST], coverage_off_env()) for _ in range(SUITE_RUNS)]
    return {
        "median": statistics.median(seconds for seconds, _ in runs),
        "runs": [seconds for seconds, _ in runs],
        "exit_codes": [code for _, code in runs],
    }


def extras_installed() -> dict[str, bool]:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return {
        extra: all(distribution_installed(req) for req in reqs)
        for extra, reqs in project["optional-dependencies"].items()
    }


def distribution_installed(requirement: str) -> bool:
    try:
        importlib.metadata.version(re.match(r"[A-Za-z0-9_.-]+", requirement).group())
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor()


def machine() -> dict:
    return {
        "system": f"{platform.system()} {platform.release()} {platform.machine()}",
        "cpu": cpu_model(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }


def settings() -> dict:
    return {
        "pytest": "python " + " ".join(PYTEST),
        "workers": WORKERS,
        "suite_runs": SUITE_RUNS,
        "validate_help_runs": HELP_RUNS,
        "coverage": "off (COVERAGE_* variables removed)",
        "extras_installed": extras_installed(),
        "ruff": run(["ruff", "--version"]).stdout.strip(),
        "c901_over_max_complexity": "ruff check --select C901 --ignore-noqa (waivers ignored)",
        "lines_over_100": "ruff check --select E501 --line-length 100",
    }


def measure() -> dict:
    py_files = tracked(*(f":(glob){area}/**/*.py" for area in AREAS))
    package = [rel for rel in py_files if rel.startswith("specy_road/")]
    tests = [rel for rel in py_files if rel.startswith("tests/")]
    print("measuring sizes, ruff counts, commands and imports ...", flush=True)
    metrics = {
        "package": lines_and_files(package, subsystem),
        "tests": lines_and_files(tests, subsystem),
        "docs": lines_and_files(tracked(*DOCS_PATHSPECS), docs_group),
        "test_functions": test_functions(tests),
        "collected_items": collected_items(),
        "c901_over_max_complexity": ruff_counts("--select", "C901", "--ignore-noqa"),
        "noqa_c901": noqa_c901(py_files),
        "lines_over_100": ruff_counts("--select", "E501", "--line-length", "100"),
        "commands": commands(),
        "config_and_policy_keys": config_keys(),
        "validate_imports": validate_imports(),
        "validate_help_seconds": validate_help_seconds(),
    }
    print(f"timing the full suite {SUITE_RUNS} times ...", flush=True)
    metrics["suite_seconds"] = suite_seconds()
    return {
        "generated": date.today().isoformat(),
        "commit": git("rev-parse", "HEAD").strip(),
        "clean": not git("status", "--porcelain", "--", *AREAS, *DOCS_PATHSPECS, "pyproject.toml"),
        "machine": machine(),
        "settings": settings(),
        "metrics": metrics,
    }


def numbers(value, prefix: str = "") -> dict[str, float]:
    """Flatten nested metrics to ``dotted.key: number`` (lists of names are skipped)."""
    if isinstance(value, dict):
        flat = (numbers(sub, f"{prefix}{key}.") for key, sub in value.items())
        return {k: v for sub in flat for k, v in sub.items()}
    if isinstance(value, int | float) and not isinstance(value, bool):
        return {prefix.rstrip("."): value}
    return {}


def print_deltas(baseline: dict, current: dict) -> None:
    print(f"baseline {baseline['commit'][:12]} ({baseline['generated']}) -> "
          f"current {current['commit'][:12]} (clean: {current['clean']})")
    before, after = numbers(baseline["metrics"]), numbers(current["metrics"])
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        delta = "" if old is None or new is None else f"  ({new - old:+g})"
        print(f"  {key}: {old} -> {new}{delta}")


def print_width_report() -> None:
    """Lines over 100 characters per file against scripts/line_width_baseline.json; never fails."""
    # Imported here: under ``-p scripts.lean_metrics`` the scripts directory is not on sys.path.
    import line_width_baseline as width

    print(f"lines over 100 characters against {width.BASELINE.relative_to(REPO)}"
          " (a report, never a gate):")
    for line in width.report(width.load()["files"], width.counts()):
        print(line)


def print_quality_report() -> None:
    """Per-file ruff family counts against scripts/ruff_quality_baseline.json; never fails."""
    # Imported here: under ``-p scripts.lean_metrics`` the scripts directory is not on sys.path.
    import ruff_quality_baseline as quality

    data = quality.load()
    print(f"ruff quality families against {quality.BASELINE.relative_to(REPO)}"
          f" (a report, never a gate; baseline {data['commit'][:12]}):")
    for line in quality.report(data["files"], quality.counts()):
        print(line)


def contexts_rcfile(data_dir: Path) -> Path:
    """A coverage config from pyproject's scope with a per-test static context.

    Each Python process reads it at start-up (COVERAGE_PROCESS_START), so a CLI
    child takes the test id from SPECY_ROAD_LEAN_CONTEXT; pytest's own workers
    switch context per test in ``pytest_runtest_logstart`` below.
    """
    run_cfg = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    run_cfg = run_cfg["tool"]["coverage"]["run"]
    rcfile = LEAN_WORK / "contexts.coveragerc"
    rcfile.write_text(
        "[run]\n"
        f"source = {', '.join(str(REPO / s) for s in run_cfg['source'])}\n"
        f"branch = {run_cfg['branch']}\n"
        "parallel = True\n"
        f"data_file = {data_dir / '.coverage'}\n"
        f"context = ${{{CONTEXT_ENV}-}}\n",
        encoding="utf-8",
    )
    return rcfile


def pytest_runtest_logstart(nodeid: str, location) -> None:
    """Plugin hook, loaded with ``-p scripts.lean_metrics`` by ``--contexts`` only."""
    import coverage

    os.environ[CONTEXT_ENV] = nodeid
    coverage.Coverage.current().switch_context(nodeid)


def capture_contexts() -> Path:
    data_dir = LEAN_WORK / "contexts-data"
    shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True)
    rcfile = contexts_rcfile(data_dir)
    env = {**coverage_off_env(), "COVERAGE_PROCESS_START": str(rcfile)}
    proc = run([sys.executable, *PYTEST, "-p", "scripts.lean_metrics"], env=env)
    print(proc.stdout.splitlines()[-1] if proc.stdout else proc.stderr, flush=True)
    run([sys.executable, "-m", "coverage", "combine", "-q", "--rcfile", str(rcfile)], env=env)
    out = LEAN_WORK / "contexts.json"
    write_contexts(data_dir / ".coverage", out, pytest_exit=proc.returncode)
    return out


def write_contexts(db: Path, out: Path, pytest_exit: int) -> None:
    """Stream ``{test id: {file: [[from, to], ...]}}`` from the combined coverage database.

    Reads coverage.py's SQLite tables directly (the pinned version's schema): its
    public API has no per-context arc query. Arcs under the empty context
    (collection and import time) belong to no test and are left out.
    """
    header = {
        "generated": date.today().isoformat(),
        "commit": git("rev-parse", "HEAD").strip(),
        "pytest": "python " + " ".join(PYTEST),
        "pytest_exit": pytest_exit,
        "coverage": importlib.metadata.version("coverage"),
    }
    query = (
        "SELECT context.context, file.path, arc.fromno, arc.tono FROM arc"
        " JOIN context ON context.id = arc.context_id JOIN file ON file.id = arc.file_id"
        " WHERE context.context != '' ORDER BY context.context, file.path"
    )
    with sqlite3.connect(db) as conn, out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(header)[:-1] + ', "contexts": {')
        by_context = itertools.groupby(conn.execute(query), key=lambda row: row[0])
        for index, (context, rows) in enumerate(by_context):
            files: dict[str, list[list[int]]] = {}
            for _, path, start, end in rows:
                files.setdefault(Path(path).relative_to(REPO).as_posix(), []).append([start, end])
            fh.write(("," if index else "") + json.dumps(context) + ":" + json.dumps(files))
        fh.write("}}\n")


_ESTIMATE_LINE = re.compile(
    r"Estimated net line change \(informational, not a gate\):\s*(.+)"
)
_ESTIMATE_PART = re.compile(r"\b(package|tests|docs)\b\s+(?:about\s+)?([+-]?\d+)")


def line_estimates() -> dict[str, int]:
    """Sum of M16 leaves' informational line estimates, by package, tests and docs.

    A leaf that names a kind twice is counted once. Leaves that name no kind of that
    sort add nothing. The sums are printed beside the measured line counts and never gate.
    """
    from specy_road.roadmap_load import load_roadmap
    from specy_road.runtime_paths import project_root

    sums = {kind: 0 for kind in ("package", "tests", "docs")}
    leaves = {kind: 0 for kind in sums}
    seen_ids: set[str] = set()
    for node in load_roadmap(project_root())["nodes"]:
        node_id = str(node.get("id") or "")
        if not node_id.startswith("M16.") or node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        for raw in node.get("acceptance") or []:
            found = _ESTIMATE_LINE.search(str(raw))
            if not found:
                continue
            named: set[str] = set()
            for kind, number in _ESTIMATE_PART.findall(found.group(1)):
                if kind in named:
                    continue
                named.add(kind)
                sums[kind] += int(number)
                leaves[kind] += 1
    return {**sums, **{f"{kind}_leaves": count for kind, count in leaves.items()}}


def print_estimates(baseline: dict, current: dict, estimates: dict[str, int]) -> None:
    """Measured line totals beside the summed informational estimates. Never a gate."""
    before, after = numbers(baseline["metrics"]), numbers(current["metrics"])
    print("line counts beside the sum of M16 leaves' informational estimates (not a gate):")
    for kind, key in (
        ("package", "package.total.lines"),
        ("tests", "tests.total.lines"),
        ("docs", "docs.total.lines"),
    ):
        old, new = before.get(key), after.get(key)
        delta = "" if old is None or new is None else f" ({new - old:+g})"
        print(
            f"  {kind} lines: {old} -> {new}{delta} beside estimate sum "
            f"{estimates[kind]:+g} ({estimates[f'{kind}_leaves']} leaves named {kind})"
        )


def print_command_bound(current: dict) -> None:
    counted = current["metrics"]["commands"]
    print(
        f"canonical commands {counted['canonical']} (bound {CANONICAL_BOUND}, M16.4.4; "
        f"planning figure {PLANNING_COMMAND_FIGURE} is not a gate: M16.4.4 records that "
        "the earlier bound of 56 no longer holds)"
    )
    print(f"aliases {counted['aliases']}: {' '.join(counted['alias_names'])}")


def print_suite(current: dict) -> None:
    suite = current["metrics"]["suite_seconds"]
    print(
        f"suite time median {suite['median']}s runs {suite['runs']} "
        f"exits {suite['exit_codes']} (informational, not a gate)"
    )


def fail_under() -> int:
    report = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return int(report["tool"]["coverage"]["report"]["fail_under"])


def end_state() -> dict | None:
    found = json.loads(BASELINE.read_text(encoding="utf-8")).get("rc5_end_state")
    return found if isinstance(found, dict) else None


def changed_since(commit: str, *pathspecs: str) -> list[str]:
    out = git("diff", "--name-only", commit, "HEAD", "--", *pathspecs)
    return [line for line in out.splitlines() if line]


def coverage_percent(data_file: Path) -> float:
    """``totals.percent_covered`` of a combined coverage data file (branch coverage)."""
    dest = LEAN_WORK / "coverage-total.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = run([
        sys.executable, "-m", "coverage", "json", "-q", "-o", str(dest),
        "--data-file", str(data_file),
    ])
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(detail[-2000:] or f"coverage json exited {proc.returncode}")
    return float(json.loads(dest.read_text(encoding="utf-8"))["totals"]["percent_covered"])


def live_coverage_total() -> float:
    """One full suite under the pyproject coverage settings, then its TOTAL."""
    env = coverage_off_env()
    proc = run([sys.executable, "-m", "coverage", "run", *PYTEST], env=env)
    print(proc.stdout.splitlines()[-1] if proc.stdout else proc.stderr, flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"coverage suite exited {proc.returncode}")
    combined = run([sys.executable, "-m", "coverage", "combine", "-q"], env=env)
    if combined.returncode != 0:
        detail = (combined.stderr or combined.stdout).strip()
        raise RuntimeError(detail[-2000:] or "coverage combine failed")
    data_file = REPO / "work" / ".coverage"
    return coverage_percent(data_file)


def coverage_for_check(recorded: dict | None) -> tuple[float, str]:
    """The recorded TOTAL when this tree's package and tests are still that commit."""
    if recorded and recorded.get("coverage") and not changed_since(
        str(recorded["commit"]), "specy_road", "tests"
    ):
        total = float(recorded["coverage"]["total"])
        return total, f"recorded at {str(recorded['commit'])[:12]} (specy_road and tests unchanged)"
    print("measuring coverage ...", flush=True)
    return live_coverage_total(), "measured now"


def write_end_state(section: dict) -> None:
    """Add ``rc5_end_state`` without changing the M16.1.7 baseline object."""
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    data["rc5_end_state"] = {"baseline_commit": data["commit"], **section}
    BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def arc_union(path: Path) -> dict[str, set[tuple[int, int]]]:
    """Union of covered branch arcs per ``specy_road`` module, across every test."""
    contexts = json.loads(path.read_text(encoding="utf-8"))["contexts"]
    union: dict[str, set[tuple[int, int]]] = {}
    for files in contexts.values():
        for rel, arcs in files.items():
            if rel.startswith("specy_road/") and rel.endswith(".py"):
                union.setdefault(rel, set()).update((arc[0], arc[1]) for arc in arcs)
    return union


def contexts_pytest_exit(path: Path) -> int:
    head = path.read_text(encoding="utf-8")[:1000]
    match = re.search(r'"pytest_exit":\s*(-?\d+)', head)
    return int(match.group(1)) if match else 1


def package_py_files(rev: str) -> set[str]:
    out = git("ls-tree", "-r", "--name-only", rev, "--", "specy_road")
    return {line for line in out.splitlines() if line.endswith(".py")}


def identical_package_files(base: str, head: str) -> list[str]:
    """``specy_road`` modules present at both commits whose blob did not change."""
    changed = set(git("diff", "--name-only", base, head, "--", "specy_road").splitlines())
    return sorted((package_py_files(base) & package_py_files(head)) - changed)


def only_before(
    identical: list[str],
    base_arcs: dict[str, set[tuple[int, int]]],
    head_arcs: dict[str, set[tuple[int, int]]],
) -> list[str]:
    """Identical modules whose covered arcs at the merge base are not all covered at head."""
    return [
        rel for rel in identical
        if base_arcs.get(rel, set()) - head_arcs.get(rel, set())
    ]


def run_contexts(root: Path) -> tuple[Path, Path]:
    """``--contexts`` in ``root``. Returns the contexts file and the combined data file."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    previous = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) if not previous else str(root) + os.pathsep + previous
    proc = subprocess.run(
        [sys.executable, "scripts/lean_metrics.py", "--contexts"],
        cwd=root, capture_output=True, text=True, check=False, env=env,
    )
    print(proc.stdout.strip() or (proc.stderr or "")[-500:], flush=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "contexts failed")[-2000:])
    lean = root / "work" / "lean"
    return lean / "contexts.json", lean / "contexts-data" / ".coverage"


def measured_tree(root: Path) -> dict:
    contexts, data_file = run_contexts(root)
    return {
        "arcs": arc_union(contexts),
        "total": coverage_percent(data_file),
        "pytest_exit": contexts_pytest_exit(contexts),
    }


def with_merge_base(sha: str, measure):
    """Detach a temporary worktree at ``sha``, measure it, and remove the worktree."""
    path = Path(tempfile.mkdtemp(prefix="m1681-base-"))
    path.rmdir()
    added = run(["git", "worktree", "add", "--detach", str(path), sha])
    if added.returncode != 0:
        raise RuntimeError((added.stderr or "worktree add failed")[-2000:])
    try:
        return measure(path)
    finally:
        run(["git", "worktree", "remove", "--force", str(path)])


def integration_branch() -> str:
    from specy_road.git_workflow_config import load_git_workflow_config
    from specy_road.runtime_paths import project_root

    data, err = load_git_workflow_config(project_root())
    if err or not isinstance(data, dict) or not data.get("integration_branch"):
        raise RuntimeError(err or "git-workflow.yaml has no integration_branch")
    return str(data["integration_branch"])


def merge_base_commit() -> str:
    branch = integration_branch()
    for name in (branch, f"origin/{branch}"):
        if run(["git", "rev-parse", "--verify", "--quiet", name]).returncode == 0:
            return git("merge-base", "HEAD", name).strip()
    raise RuntimeError(f"{branch} is not in this clone")


def measure_effectiveness() -> dict:
    """M16.7.8's two measures: coverage against fail_under and the merge base, and arcs.

    Mutation score is not a measure for 0.3.1. Suite time is not part of this.
    """
    base = merge_base_commit()
    head = git("rev-parse", "HEAD").strip()
    print(f"effectiveness: contexts at {head[:12]} ...", flush=True)
    head_m = measured_tree(REPO)
    print(f"effectiveness: contexts at merge base {base[:12]} ...", flush=True)
    base_m = with_merge_base(base, measured_tree)
    identical = identical_package_files(base, head)
    problems = only_before(identical, base_m["arcs"], head_m["arcs"])
    floor = fail_under()
    effect = {
        "coverage_at_least_fail_under": head_m["total"] >= floor,
        "coverage_not_below_merge_base": head_m["total"] + 1e-9 >= base_m["total"],
        "identical_modules": len(identical),
        "identical_module_only_before_arcs_empty": not problems,
        "only_before_modules": problems,
        "head_pytest_exit": head_m["pytest_exit"],
        "merge_base_pytest_exit": base_m["pytest_exit"],
        "mutation_score": "not a measure for 0.3.1",
    }
    passed = (
        effect["coverage_at_least_fail_under"]
        and effect["coverage_not_below_merge_base"]
        and effect["identical_module_only_before_arcs_empty"]
        and effect["head_pytest_exit"] == 0
        and effect["merge_base_pytest_exit"] == 0
    )
    return {
        "ok": passed,
        "coverage": {
            "fail_under": floor,
            "total": round(head_m["total"], 2),
            "merge_base": base,
            "merge_base_total": round(base_m["total"], 2),
            "method": "coverage json totals.percent_covered after lean_metrics --contexts",
        },
        "effectiveness": effect,
    }


def gate_failures(current: dict, total: float, recorded: dict | None) -> list[str]:
    """Hard gates. Line counts and suite time are never among them."""
    failures: list[str] = []
    canonical = current["metrics"]["commands"]["canonical"]
    if canonical > CANONICAL_BOUND:
        failures.append(f"canonical command count {canonical} is above {CANONICAL_BOUND}")
    if total < fail_under():
        failures.append(f"coverage TOTAL {total} is below fail_under {fail_under()}")
    if not recorded or "effectiveness" not in recorded:
        failures.append("rc5 effectiveness is not recorded; run --record-end-state")
        return failures
    effect = recorded["effectiveness"]
    stale = changed_since(str(recorded["commit"]), "specy_road", "tests")
    if stale:
        shown = ", ".join(stale[:8])
        failures.append(f"effectiveness was recorded before specy_road or tests changed: {shown}")
    if not effect.get("coverage_at_least_fail_under"):
        failures.append("recorded coverage is below fail_under")
    if not effect.get("coverage_not_below_merge_base"):
        failures.append("recorded coverage is below the merge base TOTAL")
    if not effect.get("identical_module_only_before_arcs_empty"):
        modules = ", ".join(effect.get("only_before_modules") or [])
        failures.append(f"covered arcs shrank on unchanged modules: {modules}")
    exits = (effect.get("head_pytest_exit"), effect.get("merge_base_pytest_exit"))
    if any(exits):
        failures.append(f"a pytest run in the effectiveness measurement exited {exits}")
    return failures


def check() -> int:
    current = measure()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    print_deltas(baseline, current)
    print_width_report()
    print_quality_report()
    print_estimates(baseline, current, line_estimates())
    print_command_bound(current)
    print_suite(current)
    recorded = end_state()
    total, how = coverage_for_check(recorded)
    print(f"coverage TOTAL {total}% against fail_under {fail_under()} ({how})")
    if recorded and "effectiveness" in recorded:
        effect = recorded["effectiveness"]
        print(
            f"effectiveness at {str(recorded['commit'])[:12]}: "
            f"coverage >= fail_under {effect['coverage_at_least_fail_under']}; "
            f"not below merge base {effect['coverage_not_below_merge_base']}; "
            f"unchanged-module arcs kept {effect['identical_module_only_before_arcs_empty']} "
            f"({effect['identical_modules']} identical modules)"
        )
    failures = gate_failures(current, total, recorded)
    for item in failures:
        print(f"FAIL: {item}")
    if failures:
        return 1
    print("gates passed; line counts and suite time are not gates")
    return 0


def record_end_state() -> int:
    current = measure()
    effect = measure_effectiveness()
    write_end_state({
        "generated": current["generated"],
        "commit": current["commit"],
        "clean": current["clean"],
        "machine": current["machine"],
        "settings": current["settings"],
        "metrics": current["metrics"],
        "estimates": line_estimates(),
        "coverage": effect["coverage"],
        "effectiveness": effect["effectiveness"],
    })
    print(f"wrote rc5_end_state of {BASELINE.relative_to(REPO)} at {current['commit'][:12]}")
    if not current["clean"]:
        print("FAIL: measured paths were not a clean tree", flush=True)
        return 1
    return 0 if effect["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="print deltas and the rc5 gates")
    mode.add_argument("--contexts", action="store_true", help="write per-test arcs (opt-in)")
    mode.add_argument(
        "--record-end-state",
        action="store_true",
        help="write rc5 measurements beside the M16.1.7 baseline",
    )
    args = parser.parse_args(argv)

    if args.contexts:
        print(f"wrote {capture_contexts().relative_to(REPO)}")
        return 0
    if args.record_end_state:
        return record_end_state()
    if args.check:
        return check()
    print(
        "The M16.1.7 baseline stays as committed. "
        "Use --check to measure against it, or --record-end-state to write rc5 beside it.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
