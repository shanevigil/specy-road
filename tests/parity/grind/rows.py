"""The grind table: one fixture repo per row, ``grind-session`` run on it, and what it did.

Rows run the real command (``python -m specy_road.cli grind-session``) on the offline project of
:mod:`tests.parity.grind.fixture`; pickup and finish are the real child commands, and the
implement hook is a shell command (or the fake ``claude`` on PATH). ``golden/<row>.txt`` holds,
for each step, its exit code, its events (``--json`` lines with ``ts`` masked, or the human
``[grind-session]`` lines), the stderr lines the loop and its children print as errors or
refusals, and then the project's state: the checked-out branch, the local branches, the registry
rows and each leaf's status on ``main``. The plan rows record ``grind-session --plan`` (JSON and
text) on the dogfood fixture, on the readiness cases, on a project with an open claim and on four
rows of the orchestration state table. Every golden was recorded before the grind modules moved.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tests.parity.grind.fixture import (
    IMPLEMENT,
    LEAVES,
    cli,
    copy_project,
    git,
    nodes_by_id,
    offline_env,
)
from tests.parity.orchestration_state import rows as state_rows
from tests.parity.support import normalise, repo_copy

GOLDEN = Path(__file__).resolve().parent / "golden"
DOGFOOD = Path(__file__).resolve().parents[2] / "fixtures" / "specy_road_dogfood"
HOOK = ("--implement-mode", "hook", "--implement-cmd")
CLAUDE_HOOK = (*HOOK, "claude -p task")
#: The fake ``claude`` prints a timed limit (reset stated in UTC, session id given) and fails.
TIMED_LIMIT = (
    "echo 'Claude usage limit reached — resets at 11pm (UTC)'\n"
    "echo 'session_id: 3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50'\nexit 1\n"
)
#: The fake ``claude`` exits as a killed process does (137) without printing anything.
VANISHES = "exit 137\n"
#: Steps whose first word is this run :data:`IMPLEMENT` in the project, as an agent would.
SHELL_IMPLEMENT = "(implement)"

_TS = re.compile(r'"ts": "[^"]*"')
_HOURS_AWAY = re.compile(r"is \d+\.\d hours away")
_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")


@dataclass(frozen=True)
class Row:
    """``build(tmp, templates)`` returns the repo to run in and its labelled paths."""

    name: str
    build: Callable[[Path, dict[str, Path]], tuple[Path, dict[str, Path]]]
    steps: tuple[tuple[str, ...], ...]
    claude: str = "exit 0\n"
    state: bool = True
    env_extra: dict[str, str] = field(default_factory=dict)


def _project(template: str, *prepare: tuple[str, ...]) -> Callable:
    """A copy of the named template, after ``prepare`` CLI steps (each must exit 0)."""

    def build(tmp: Path, templates: dict[str, Path]) -> tuple[Path, dict[str, Path]]:
        root = copy_project(templates[template], tmp)
        env = offline_env(tmp)
        for argv in prepare:
            result = cli(root, env, *argv)
            assert result.returncode == 0, f"{argv}\n{result.stdout}\n{result.stderr}"
        return root, {"repo": root.resolve(), "tmp": tmp.resolve()}

    return build


def _dogfood(tmp: Path, _templates: dict[str, Path]) -> tuple[Path, dict[str, Path]]:
    root = repo_copy(DOGFOOD, tmp / "dogfood")
    return root, {"repo": root.resolve(), "tmp": tmp.resolve()}


def _state_row(name: str) -> Callable:
    """A row of the orchestration state table (its fixture repo, claim on ``M1.1``)."""
    row = next(r for r in state_rows.ROWS if r.name == name)

    def build(tmp: Path, _templates: dict[str, Path]) -> tuple[Path, dict[str, Path]]:
        return state_rows.build(row, tmp)

    return build


_PICKUP_ALPHA = ("do-next-available-task", "--under", "M1.2", "--on-complete", "merge")
PLAN = (("--plan", "--json"), ("--plan",))
#: The readiness plans also run with pickup's ``--prefer-agentic`` order.
PLAN_READINESS = (*PLAN, ("--plan", "--json", "--prefer-agentic"))

ROWS: tuple[Row, ...] = (
    Row("max_leaves", _project("base"),
        (("--json", *HOOK, IMPLEMENT, "--max-leaves", "1"),)),
    Row("event_log_lines", _project("base"), ((*HOOK, IMPLEMENT),)),
    Row("resume_in_flight", _project("base", _PICKUP_ALPHA),
        (("--json", "--under", "M1.2", "--resume-in-flight", *HOOK, IMPLEMENT),)),
    Row("in_flight_exit_6", _project("base", _PICKUP_ALPHA),
        (("--json", "--under", "M1.2", *HOOK, IMPLEMENT), ("--under", "M1.2", *HOOK, IMPLEMENT))),
    Row("blocked_on_dependency_exit_3", _project("readiness"),
        (("--json", "--under", "M1.8", *HOOK, IMPLEMENT), ("--under", "M1.8", *HOOK, IMPLEMENT))),
    Row("blocked_on_gate_exit_3", _project("readiness"),
        (("--json", "--under", "M1.6", *HOOK, IMPLEMENT),)),
    Row("limit_waits", _project("base"),
        (("--json", *CLAUDE_HOOK, "--max-limit-waits", "0"),), claude=TIMED_LIMIT),
    Row("limit_wait_hours", _project("base"),
        (("--json", *CLAUDE_HOOK, "--max-limit-wait-hours", "0"),), claude=TIMED_LIMIT),
    Row("empty_retries", _project("base"),
        (("--json", *CLAUDE_HOOK, "--max-empty-retries", "0"),), claude=VANISHES),
    Row("step_pickup_then_finish", _project("base"),
        (("--step", "pickup", "--json"), (SHELL_IMPLEMENT,), ("--step", "finish", "--json"),
         ("--step", "pickup", "--json"))),
    Row("step_pickup_resumes_own_claim", _project("base", _PICKUP_ALPHA),
        (("--step", "pickup", "--json"),)),
    Row("step_finish_without_claim", _project("base"), (("--step", "finish", "--json"),)),
    Row("plan_dogfood", _dogfood, PLAN, state=False),
    Row("plan_readiness", _project("readiness"), PLAN_READINESS),
    Row("plan_open_claim", _project("readiness", _PICKUP_ALPHA), PLAN_READINESS),
    *(
        Row(f"plan_state_{name}", _state_row(name), PLAN, state=False)
        for name in ("fresh_manual_claim", "live_worker", "abandoned", "unreadable_worker_state")
    ),
)


def _events(stdout: str, *, plan: bool) -> str:
    """JSON events one per block (``ts`` masked), else the human ``[grind-session]`` lines.

    A ``--plan`` step keeps every line: its text report is the event.
    """
    out = []
    for line in stdout.splitlines():
        try:
            event = json.loads(_TS.sub('"ts": "<TS>"', line))
        except ValueError:
            if plan or line.startswith("[grind-session]"):
                out.append(line)
            continue
        out.append(json.dumps(event, indent=2))
    return "\n".join(out) + "\n"


def _refusals(stderr: str) -> str:
    keep = [
        line for line in stderr.splitlines()
        if line.startswith(("grind-session", "error:"))
    ]
    return "".join(f"{line}\n" for line in keep)


def _registry(root: Path, ref: str | None) -> list[str]:
    if ref is None:
        path = root / "roadmap" / "registry.yaml"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    else:
        text = subprocess.run(
            ["git", "show", f"{ref}:roadmap/registry.yaml"], cwd=root,
            capture_output=True, text=True,
        ).stdout
    doc = yaml.safe_load(text) or {}
    return [f"{e.get('node_id')} {e.get('branch')}" for e in doc.get("entries") or []]


def _state(root: Path) -> str:
    branches = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
    git(root, "show", "main:roadmap/phases/M1.json")  # main exists in every project row
    statuses = {}
    for chunk in git(root, "ls-tree", "--name-only", "main", "roadmap/phases/").splitlines():
        for node in json.loads(git(root, "show", f"main:{chunk}"))["nodes"]:
            statuses[node["id"]] = node.get("status")
    state = {
        "branch": git(root, "branch", "--show-current"),
        "branches": sorted(branches),
        "registry": {"checkout": _registry(root, None), "main": _registry(root, "main")},
        "status_on_main": statuses,
    }
    return json.dumps(state, indent=2) + "\n"


def record(row: Row, tmp: Path, templates: dict[str, Path]) -> str:
    """The golden text for ``row``: each step, then the project's state."""
    root, dirs = row.build(tmp, templates)
    env = {**offline_env(tmp / "env", row.claude), **row.env_extra}
    parts = []
    for argv in row.steps:
        if argv[0] == SHELL_IMPLEMENT:
            result = subprocess.run(
                IMPLEMENT, shell=True, cwd=root, capture_output=True, text=True,
                env={**env, "SPECY_ROAD_NODE_ID": nodes_by_id(root)[LEAVES[0][0]]["id"]},
            )
        else:
            result = cli(root, env, "grind-session", *argv)
        parts.append(
            f"$ grind-session {' '.join(argv)}\nexit: {result.returncode}\n"
            f"--- events ---\n{_events(result.stdout, plan='--plan' in argv)}"
            f"--- errors ---\n{_refusals(result.stderr)}"
        )
    if row.state:
        parts.append(f"--- state ---\n{_state(root)}")
    paths = {path: f"<{label.upper()}>" for label, path in dirs.items()}
    text = normalise("\n".join(parts), paths)
    return _SHA.sub("<SHA>", _HOURS_AWAY.sub("is <N> hours away", text))


def golden_path(row: Row) -> Path:
    """Where ``row``'s recorded output lives."""
    return GOLDEN / f"{row.name}.txt"
