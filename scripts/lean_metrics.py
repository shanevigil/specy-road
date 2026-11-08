#!/usr/bin/env python3
"""Measure the M16 lean-core metrics against constraints/lean-baseline.json.

Every number is a measurement, never a gate: the CI coverage floor
([tool.coverage.report] fail_under in pyproject.toml) is the only check M16.1.7
adds. Files are the ones git tracks at HEAD, read from the working tree, so the
recorded commit is the one measured when ``clean`` is true. Subprocesses use the
interpreter running this script; run it from an environment with every extra
installed (``pip install -r requirements-ci.txt`` plus ``-e '.[review,gui]'``).

Usage:
    python scripts/lean_metrics.py             # measure and write the baseline
    python scripts/lean_metrics.py --check     # measure and print deltas against it
    python scripts/lean_metrics.py --contexts  # covered arcs per test -> work/lean/contexts.json

The baseline is rewritten only by M16.8.1 and by maintainers; M16 leaves report
``--check`` deltas in READY. ``--contexts`` is opt-in and never runs in CI.
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
    ":(exclude,glob)docs/design-notes/**",
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


def commands() -> dict:
    """The canonical command count as M16.4.4 defines it.

    Distinct registered top-level ``specy-road`` names, minus the names whose
    command_map.yaml row retires them as top-level aliases (``old`` is a bare
    ``specy-road <name>`` and ``new`` differs); subcommand and flag rows do not count.
    """
    code = (
        "import json; from specy_road.cli import registered_agent_command_names as r; "
        "print(json.dumps(sorted(r()['specy-road'])))"
    )
    names = set(json.loads(run([sys.executable, "-c", code]).stdout))
    rows = (yaml.safe_load(COMMAND_MAP.read_text(encoding="utf-8")) or {}).get("rows") or []
    aliases = sorted(
        old.split()[1]
        for old, new in ((str(r.get("old") or ""), str(r.get("new") or "")) for r in rows)
        if len(old.split()) == 2 and old.startswith("specy-road ") and new != old
        and old.split()[1] in names
    )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="print deltas against the baseline")
    mode.add_argument("--contexts", action="store_true", help="write per-test arcs (opt-in)")
    args = parser.parse_args(argv)

    if args.contexts:
        print(f"wrote {capture_contexts().relative_to(REPO)}")
        return 0
    current = measure()
    if args.check:
        print_deltas(json.loads(BASELINE.read_text(encoding="utf-8")), current)
        return 0
    BASELINE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {BASELINE.relative_to(REPO)} at {current['commit'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
