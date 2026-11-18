#!/usr/bin/env python3
"""Write the M16.7.1 dedupe worklists from ``lean_metrics --contexts`` output.

Reads ``work/lean/contexts.json`` (or the path given) and writes one row per
candidate to ``tests/support/dedupe/review-gate.csv``, ``worker.csv``,
``pickup-finish.csv`` and ``rest.csv``. A candidate is a member of an
identical arc-set group, or one side of an unordered pair whose arc-set
Jaccard is at least 19/20 (0.95). The contexts file's commit is recorded on
every row. ``tests/support/dedupe/modules.json`` lists each subsystem's
modules; a pair or group is filed under the subsystem that holds the most of
its arcs, ties breaking in the order review-gate, worker, pickup-finish, rest.

A test with no attributed ``specy_road`` arc is not a candidate. Re-running
on the same contexts file at the recorded commit rewrites the same bytes.
``--check`` compares the tree to that rewrite and exits non-zero on a difference
or a broken invariant.

Ids written into a worklist are repo-relative. A path inside this checkout
drops the checkout prefix. Any other absolute path, a home path, a hostname
or an ``sr/`` path is the placeholder ``<path>``.

Each row records an action. A delete or fold names the surviving test, the
assertion in it that covers the removed one, and, for a fold, the table that
receives the case. A keep that was read names what differs. A keep left to
the classifier is labelled ``keep (classifier)``. An empty ``decision`` is
an undecided keep. Parametrized rows of one test share one reason.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXTS = REPO / "work" / "lean" / "contexts.json"
DEDUPE = REPO / "tests" / "support" / "dedupe"
SUBSYSTEMS = ("review-gate", "worker", "pickup-finish", "rest")
FILES = {name: DEDUPE / f"{name}.csv" for name in SUBSYSTEMS}
MANIFEST = DEDUPE / "modules.json"
JACCARD_NUM, JACCARD_DEN = 19, 20
COLUMNS = (
    "contexts_commit", "kind", "candidate_key", "test_id", "counterparts",
    "jaccard", "arc_count", "action", "survivor", "assertion", "fold_destination",
    "decision",
)
REVIEW_MARKERS = (
    "review", "rework", "red_green", "steering_gate", "human_acceptance",
    "llm_throughput", "ready_",
)
WORKER_DIRS = (
    "specy_road/orchestration/workers/",
    "specy_road/orchestration/harness/",
    "specy_road/orchestration/guard/",
)
WORKER_NAMES = (
    "worker", "worktree", "roster", "orchestrate", "orchestration_",
    "model_", "models_", "harness_", "session_cli", "session_presence",
)
PICKUP_DIRS = ("specy_road/orchestration/grind/",)
PICKUP_NAMES = (
    "do_next", "finish", "abort_task", "registration_pickup", "on_complete",
    "milestone", "nested_repos", "git_milestone", "grind", "sibling_repos",
    "start_milestone", "reconcile_milestone", "open_milestone",
)
PATH_PLACEHOLDER = "<path>"
_FS_ROOT = r"home|Users|tmp|private|var|usr|opt|etc|dev|abs(?:-[A-Za-z0-9]+)?|bin|proc|sys|run|root"
_QUOTED_PATH = re.compile(
    rf"""(?P<q>["'])/(?:{_FS_ROOT})(?![A-Za-z0-9._-])[^"'\\]*(?P=q)"""
)
_ABS_PATH = re.compile(
    rf"(?<![.\w:/])/(?:{_FS_ROOT})(?![A-Za-z0-9._-])(?:/[^/\s\]\"';,]*)*"
)
_WIN_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\(?:[^\\\s\]\"']+\\)*[^\\\s\]\"']*")
_TILDE_PATH = re.compile(r"(?<![\w])~/[^\s\]\"']*")
_HOSTNAME = re.compile(r"\b[A-Za-z0-9.-]*MacBook(?:-(?:Pro|Air))?(?:-\d+)?\.local\b")
_SR_PATH = re.compile(
    r"(?<![\w.-])sr/(?:work|planning|roadmap|tools)(?:/[^/\s\]\"']+)*"
)
DECISION_RULE = (
    "A delete or fold names the surviving test and the assertion that covers "
    "the removed case. A keep that was read names the behaviour, input class "
    "or state that differs. A keep (classifier) row was not in that pool. "
    "No removal is the only test of an escalation rule, a forced RCA, a "
    "next-step state or a deferral."
)
PARAM_REASON = (
    "keep (classifier): one parametrized table; each row checks a different input"
)
DIFFERENT_ASSERTIONS = "keep (classifier): different assertions"
# function id -> (action, survivor, assertion, fold destination, decision)
REMOVALS = {
    "tests/unit/test_roadmap_crud.py::test_edit_node_cli": (
        "delete",
        "tests/unit/test_roadmap_crud_edit_node_chunks.py::test_edit_node_in_place_lists_read_and_written_chunk",
        "assert r.returncode == 0, r.stderr",
        "",
        "same edit-node M99.1 status=Complete; the chunk test asserts "
        "that return code and the written status",
    ),
    "tests/flows/pickup/test_verify_cmd.py::test_schema_accepts_verify_cmd": (
        "fold",
        "tests/unit/test_baseline_gate.py::test_schema_accepts_baseline_cmd",
        "assert validate_git_workflow_dict(data) is None",
        "tests/unit/test_baseline_gate.py::test_schema_accepts_baseline_cmd",
        "same schema acceptance of one optional command; verify_cmd joins the baseline_cmd table",
    ),
    "tests/flows/worker/test_worker_state.py::test_reclaim_keeps_the_prompt_verbatim": (
        "fold",
        "tests/flows/worker/test_worker_state.py::test_hook_prompts_are_stored_whole",
        'assert detail["prompts"] == [long]',
        "tests/flows/worker/test_worker_state.py::test_hook_prompts_are_stored_whole",
        "same stored hook prompt, two lengths; 600 joins the 2501 table",
    ),
    "tests/cli/test_doctor_version_skew.py::test_silent_when_running_is_newer_than_every_recorded_source": (
        "fold",
        "tests/cli/test_doctor_version_skew.py::test_silent_when_running_matches_the_recorded_version",
        'assert "older install earlier on PATH" not in proc.stderr',
        "tests/cli/test_doctor_version_skew.py::test_silent_when_running_matches_the_recorded_version",
        "recorded 0.0.1 and the running version are two non-stale inputs of one silence check",
    ),
    "tests/flows/worker/test_claude_config_dir.py::test_an_empty_variable_means_the_default": (
        "fold",
        "tests/flows/worker/test_claude_config_dir.py::test_the_default_is_the_home_directory",
        'assert claude_projects_dir() == tmp_path / ".claude" / "projects"',
        "tests/flows/worker/test_claude_config_dir.py::test_the_default_is_the_home_directory",
        "an empty CLAUDE_CONFIG_DIR joins the unset-variable default",
    ),
    "tests/unit/test_orchestrate_plan.py::test_unavailable_model_is_skipped_until_its_date": (
        "fold",
        "tests/flows/worker/test_roster_availability.py::test_paused_until_date_in_future_and_past",
        'assert only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 5))[0]).executor == "sol"',
        "tests/flows/worker/test_roster_availability.py::test_paused_until_date_in_future_and_past",
        "unavailable_until joins the paused_until date table; both dates pick sol then flash",
    ),
    "tests/flows/worker/test_worker_max_workers_global.py::test_a_missing_checkout_id_is_created_and_the_count_still_holds": (
        "fold",
        "tests/flows/worker/test_worker_max_workers_global.py::test_an_empty_or_unusable_checkout_id_is_rewritten_and_the_limit_holds",
        'assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1',
        "tests/flows/worker/test_worker_max_workers_global.py::test_an_empty_or_unusable_checkout_id_is_rewritten_and_the_limit_holds",
        "a missing checkout-id file joins the unusable-contents table; both hold the limit",
    ),
    "tests/flows/roadmap/test_history_cache.py::test_a_truncated_cache_document_rebuilds": (
        "fold",
        "tests/flows/roadmap/test_history_cache.py::test_a_corrupt_cache_rebuilds_without_raising",
        "assert load_cache(repo) is None",
        "tests/flows/roadmap/test_history_cache.py::test_a_corrupt_cache_rebuilds_without_raising",
        "a truncated document joins the non-json cache; both rebuild",
    ),
    "tests/gui/test_gui_workspace_file.py::test_api_workspace_file_get_rejects_work_prefix": (
        "fold",
        "tests/gui/test_gui_workspace_file.py::test_api_workspace_file_get_rejects_non_shared",
        "assert r.status_code == 400",
        "tests/gui/test_gui_workspace_file.py::test_api_workspace_file_get_rejects_non_shared",
        "work/ joins planning/ as a second disallowed workspace path",
    ),
    "tests/gui/test_gui_app_milestone_lock.py::test_delete_inside_locked_subtree_returns_409": (
        "fold",
        "tests/gui/test_gui_app_milestone_lock.py::test_outline_move_into_locked_subtree_returns_409",
        "assert r.status_code == 409, r.text",
        "tests/gui/test_gui_app_milestone_lock.py::test_outline_move_into_locked_subtree_returns_409",
        "delete joins the locked-subtree mutation table",
    ),
    "tests/gui/test_gui_app_milestone_lock.py::test_indent_inside_locked_subtree_returns_409": (
        "fold",
        "tests/gui/test_gui_app_milestone_lock.py::test_outline_move_into_locked_subtree_returns_409",
        "assert r.status_code == 409, r.text",
        "tests/gui/test_gui_app_milestone_lock.py::test_outline_move_into_locked_subtree_returns_409",
        "indent joins the locked-subtree mutation table",
    ),
    "tests/gui/test_gui_app_mutations.py::test_api_outline_move_rejects_unknown_node_key": (
        "delete",
        "tests/gui/test_gui_app_routes_nodes_errors.py::test_outline_move_unknown_node_key_is_400_not_404",
        "assert r.status_code == 400",
        "",
        "same unknown node_key; the routes test also checks the detail names node_key",
    ),
    "tests/unit/test_roadmap_crud_atomicity.py::test_rejected_edit_changes_nothing_on_disk": (
        "delete",
        "tests/unit/test_roadmap_crud_atomicity.py::test_rejected_edit_does_not_rename_the_planning_sheet",
        "assert _snapshot(repo) == before",
        "",
        "same rejected title; the sheet test also asserts the snapshot is unchanged",
    ),
    "tests/flows/review/test_review_record_write.py::test_a_custom_reviewer_command_under_review_delegate_is_checked_and_filed": (
        "delete",
        "tests/unit/test_run_record_no_false_failure.py::test_delegate_run_whose_verdict_was_filed_has_no_error_in_the_run_file",
        'assert delegate(repo, "M1.1", "gem", sleep=lambda s: None)["outcome"] == "recorded"',
        "",
        "same plain verdict; the run-file test asserts recorded and that the run has no error",
    ),
    "tests/cli/test_session_guard.py::test_explicit_pathspecs_pass": (
        "fold",
        "tests/unit/test_tool_call_guard.py::test_ordinary_commands_pass",
        "assert g.classify(command) is None, command",
        "tests/unit/test_tool_call_guard.py::test_ordinary_commands_pass",
        "explicit pathspecs join the ordinary-commands table",
    ),
    "tests/cli/test_session_guard.py::test_env_config_check_leaves_ordinary_commands_alone": (
        "fold",
        "tests/unit/test_tool_call_guard.py::test_ordinary_commands_pass",
        "assert g.classify(command) is None, command",
        "tests/unit/test_tool_call_guard.py::test_ordinary_commands_pass",
        "env-config ordinary commands join the ordinary-commands table",
    ),
    "tests/cli/test_session_guard.py::test_dynamic_shell_forms_fail_closed": (
        "fold",
        "tests/unit/test_tool_call_guard.py::test_destructive_commands_are_classified",
        "assert reason and fragment in reason, (command, reason)",
        "tests/unit/test_tool_call_guard.py::test_destructive_commands_are_classified",
        "dynamic shell forms join the destructive-command table",
    ),
    "tests/cli/test_session_guard.py::test_eval_is_judged_by_what_it_runs": (
        "fold",
        "tests/unit/test_tool_call_guard.py::test_destructive_commands_are_classified",
        "assert reason and fragment in reason, (command, reason)",
        "tests/unit/test_tool_call_guard.py::test_destructive_commands_are_classified",
        "eval is judged by the command it runs; it joins the destructive-command table",
    ),
    "tests/unit/test_tool_call_guard.py::test_more_wrapper_shapes_are_classified": (
        "fold",
        "tests/unit/test_tool_call_guard.py::test_more_destructive_shapes_are_classified",
        "assert tg.classify(command), command",
        "tests/unit/test_tool_call_guard.py::test_more_destructive_shapes_are_classified",
        "wrapper shapes join the destructive-shapes table",
    ),
}
REMOVED_SURVIVOR = {removed: spec[1] for removed, spec in REMOVALS.items()}
KEEP_PAIRS = {
    frozenset({
        "tests/flows/registry/test_registry_prune.py::test_report_lists_the_orphan_and_exits_1",
        "tests/flows/registry/test_registry_prune.py::test_report_warns_that_another_clone_looks_the_same",
    }): "exit 1 and the claim id, versus the warning not to auto-prune",
    frozenset({
        "tests/unit/test_grind_session_implement.py::test_a_reset_beyond_the_wait_ceiling_stops",
        "tests/unit/test_grind_session_implement_resilience.py::test_the_default_ceiling_still_refuses_that_reset",
    }): (
        "9h reset forbids sleep and checks 'beyond the'; "
        "7h reset checks the 6h message and the flag"
    ),
    frozenset({
        "tests/flows/registry/test_integrity.py::test_config_change_pyproject_pytest_table",
        "tests/flows/registry/test_integrity.py::test_config_change_indented_pyproject_pytest_table",
    }): "same config-change line; one file is a plain pytest table and the other is indented",
    frozenset({
        "tests/flows/review/test_review_next_step.py::test_budget_unset",
        "tests/flows/review/test_review_defer.py::test_budget_unset_reports_nothing_new",
    }): "budget_unset is the next-step state row; the defer test checks handoff text",
    frozenset({
        "tests/unit/test_specyrd_skills.py::test_init_without_force_keeps_a_users_skill_directory",
        "tests/flows/init/test_skill_mirrors.py::test_a_users_own_skill_directory_is_reported_skipped",
    }): "one keeps the user's file bytes; the other checks the skipped-list message",
}


def _load_hand_keeps() -> dict[frozenset[str], str]:
    payload = json.loads((DEDUPE / "hand_keeps.json").read_text(encoding="utf-8"))
    return {frozenset((row["a"], row["b"])): row["reason"] for row in payload}


KEEP_PAIRS.update(_load_hand_keeps())
_MISSING: set[tuple[str, str]] = set()
_ASSERT_CACHE: dict[str, tuple[str, ...]] = {}
_FILES_READ: set[str] = set()


def classify(path: str) -> str:
    """The subsystem whose module list contains ``path``.

    Directory rules cover the orchestration packages. Name rules cover the same
    modules' CLI entry points under ``bundled_scripts``, which keep the old stems.
    """
    name = path.rsplit("/", 1)[-1]
    if name.startswith("role_prompt") or "/role_prompt" in path:
        return "review-gate"
    if any(marker in name for marker in REVIEW_MARKERS):
        return "review-gate"
    if _named(path, name, WORKER_DIRS, WORKER_NAMES):
        return "worker"
    if _named(path, name, PICKUP_DIRS, PICKUP_NAMES):
        return "pickup-finish"
    return "rest"


def _named(path: str, name: str, dirs: tuple[str, ...], stems: tuple[str, ...]) -> bool:
    return any(path.startswith(prefix) for prefix in dirs) or any(
        name.startswith(stem) for stem in stems
    )


def tracked_modules() -> list[str]:
    """Tracked ``specy_road`` Python files, in path order."""
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", "specy_road"],
        cwd=REPO, capture_output=True, check=True,
    )
    return sorted(path for path in proc.stdout.decode().split("\0") if path.endswith(".py"))


def module_lists(paths: list[str]) -> dict[str, list[str]]:
    """Each subsystem's module list. Every tracked module is in exactly one."""
    lists: dict[str, list[str]] = {name: [] for name in SUBSYSTEMS}
    for path in paths:
        lists[classify(path)].append(path)
    return lists


def normalize_test_id(test_id: str) -> str:
    """Drop this checkout's prefix and replace any other machine path with ``<path>``."""
    prefix = str(REPO) + "/"
    if prefix in test_id:
        test_id = test_id.replace(prefix, "")
    test_id = _QUOTED_PATH.sub(
        lambda m: m.group("q") + PATH_PLACEHOLDER + m.group("q"), test_id,
    )
    test_id = _ABS_PATH.sub(PATH_PLACEHOLDER, test_id)
    test_id = _WIN_PATH.sub(PATH_PLACEHOLDER, test_id)
    test_id = _TILDE_PATH.sub(PATH_PLACEHOLDER, test_id)
    test_id = _HOSTNAME.sub(PATH_PLACEHOLDER, test_id)
    return _SR_PATH.sub(PATH_PLACEHOLDER, test_id)


def _public_ids(compiled: dict[str, tuple[int, ...]]) -> dict[str, tuple[int, ...]]:
    """The arc map keyed by :func:`normalize_test_id`. Two raw ids must not collapse."""
    public: dict[str, tuple[int, ...]] = {}
    for test_id, arcs in compiled.items():
        key = normalize_test_id(test_id)
        if key in public:
            raise SystemExit("two tests normalise to one id")
        public[key] = arcs
    return public


def collected_ids() -> list[str]:
    """Pytest node ids. Tests absent from the contexts file covered no arc."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"pytest --collect-only exited {proc.returncode}\n{proc.stderr[-2000:]}")
    return [line.strip() for line in proc.stdout.splitlines() if "::" in line]


def compile_arcs(contexts: dict) -> tuple[dict[str, tuple[int, ...]], list[tuple]]:
    """``{test id: sorted arc ids}`` and the arc each id names. Empty sets stay."""
    vocabulary: dict[tuple, int] = {}
    meta: list[tuple] = []
    compiled: dict[str, tuple[int, ...]] = {}
    for test_id in sorted(contexts):
        files = contexts[test_id]
        raw = []
        if isinstance(files, dict):
            raw = _arcs_of(files)
        compiled[test_id] = tuple(sorted(_intern(arc, vocabulary, meta) for arc in raw))
    return _public_ids(compiled), meta


def _arcs_of(files: dict) -> list[tuple]:
    raw = []
    for path, pairs in files.items():
        for pair in pairs:
            raw.append((str(path), int(pair[0]), int(pair[1])))
    return sorted(set(raw))


def _intern(arc: tuple, vocabulary: dict, meta: list) -> int:
    if arc not in vocabulary:
        vocabulary[arc] = len(meta)
        meta.append(arc)
    return vocabulary[arc]


def identical_groups(compiled: dict[str, tuple[int, ...]]) -> list[tuple[str, ...]]:
    """Members that share a non-empty arc set, each group sorted."""
    buckets: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for test_id, arcs in compiled.items():
        if arcs:
            buckets[arcs].append(test_id)
    groups = [tuple(sorted(members)) for members in buckets.values() if len(members) > 1]
    groups.sort()
    return groups


def jaccard_pairs(ordered: list[tuple[str, tuple[int, ...]]]) -> list[tuple[str, str, float]]:
    """Unordered pairs at or above 19/20, excluding identical arc sets."""
    freq = _frequencies(ordered)
    inverted, rare_of = _rare_index(ordered, freq)
    seen: set[tuple[str, str]] = set()
    found = []
    for index, (test_id, arcs) in enumerate(ordered):
        found.extend(_pairs_from(index, test_id, arcs, ordered, inverted, rare_of, seen))
    found.sort()
    return found


def _frequencies(ordered: list[tuple[str, tuple[int, ...]]]) -> dict[int, int]:
    freq: dict[int, int] = defaultdict(int)
    for _, arcs in ordered:
        for arc in arcs:
            freq[arc] += 1
    return freq


def _rare_index(ordered, freq):
    """Arc -> tests, limited to each test's rarest arcs.

    A pair at or above 19/20 can drop at most ``len/20`` arcs of the smaller
    side, so it shares one of that side's ``len/20 + 1`` rarest arcs.
    """
    inverted: dict[int, list[int]] = defaultdict(list)
    rare_of = []
    for index, (_, arcs) in enumerate(ordered):
        rare = sorted(arcs, key=lambda arc: (freq[arc], arc))[: len(arcs) // JACCARD_DEN + 1]
        rare_of.append(rare)
        for arc in rare:
            inverted[arc].append(index)
    return inverted, rare_of


def _pairs_from(index, test_id, arcs, ordered, inverted, rare_of, seen):
    found = []
    for arc in rare_of[index]:
        for other in inverted[arc]:
            found.extend(_one_pair(test_id, arcs, other, ordered, seen))
    return found


def _one_pair(test_id, arcs, other, ordered, seen):
    other_id, other_arcs = ordered[other]
    if other_id == test_id:
        return []
    pair = (test_id, other_id) if test_id < other_id else (other_id, test_id)
    if pair in seen:
        return []
    seen.add(pair)
    score = _jaccard(arcs, other_arcs)
    if score is None:
        return []
    return [(pair[0], pair[1], score)]


def _jaccard(left: tuple[int, ...], right: tuple[int, ...]) -> float | None:
    """Jaccard when it is at least 19/20 and the sets differ; otherwise None."""
    if left == right:
        return None
    na, nb = len(left), len(right)
    if na == 0 or nb == 0 or min(na, nb) * JACCARD_DEN < max(na, nb) * JACCARD_NUM:
        return None
    parts = JACCARD_NUM + JACCARD_DEN
    need = (JACCARD_NUM * (na + nb) + parts - 1) // parts
    inter = _intersection(left, right, need)
    if inter < need:
        return None
    return inter / (na + nb - inter)


def _intersection(left: tuple[int, ...], right: tuple[int, ...], need: int) -> int:
    """Exact intersection size, or a value below ``need`` once that is impossible."""
    i = j = found = 0
    na, nb = len(left), len(right)
    while i < na and j < nb:
        if left[i] == right[j]:
            found += 1
            i += 1
            j += 1
        elif left[i] < right[j]:
            i += 1
        else:
            j += 1
        remain = na - i
        if remain > nb - j:
            remain = nb - j
        if found + remain < need:
            return found
    return found


def choose_subsystem(arc_ids, meta, path_index) -> str:
    """Subsystem with the most arcs; ties follow ``SUBSYSTEMS`` order."""
    counts = [0, 0, 0, 0]
    for arc_id in arc_ids:
        counts[path_index.get(meta[arc_id][0], 3)] += 1
    best = 0
    for index in range(1, len(SUBSYSTEMS)):
        if counts[index] > counts[best]:
            best = index
    return SUBSYSTEMS[best]


def _function_id(node_id: str) -> str:
    return node_id.split("[", 1)[0]


def _short_name(function_id: str) -> str:
    return function_id.rsplit("::", 1)[-1]


def _own_asserts(fn: ast.AST) -> tuple[str, ...]:
    found = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Assert):
                found.append(ast.unparse(child.test))
            walk(child)

    walk(fn)
    return tuple(found)


def _index_asserts(file: str) -> None:
    if file in _FILES_READ:
        return
    _FILES_READ.add(file)
    try:
        tree = ast.parse((REPO / file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return

    class Index(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            qual = "::".join([*self.stack, node.name])
            _ASSERT_CACHE[f"{file}::{qual}"] = _own_asserts(node)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

    Index().visit(tree)


def _asserts(function_id: str) -> tuple[str, ...]:
    file, _, _rest = function_id.partition("::")
    _index_asserts(file)
    return _ASSERT_CACHE.get(function_id, ())


def _pair_keep(function_id: str, others: list[str]) -> str | None:
    for other in others:
        reason = KEEP_PAIRS.get(frozenset((function_id, _function_id(other))))
        if reason:
            return reason
    return None


def _class_reason(function_id: str, others: list[str]) -> str:
    other_ids = {_function_id(item) for item in others}
    if other_ids <= {function_id}:
        return PARAM_REASON
    paired = _pair_keep(function_id, others)
    if paired:
        return paired
    if any(REMOVED_SURVIVOR.get(_function_id(item)) == function_id for item in others):
        return "survives; this assertion covers the removed test"
    mine = _asserts(function_id)
    partners = sorted(fid for fid in other_ids if fid != function_id)
    partner = partners[0] if partners else ""
    theirs = _asserts(partner) if partner else ()
    if mine and theirs and (mine == theirs or set(mine) < set(theirs)):
        _MISSING.add((function_id, partner))
        return f"hand decision missing: {_short_name(function_id)} ~ {_short_name(partner)}"
    return DIFFERENT_ASSERTIONS


def _public_reason(text: str) -> str:
    text = text.replace(str(REPO) + "/", "")
    text = _ABS_PATH.sub(PATH_PLACEHOLDER, text)
    text = _WIN_PATH.sub(PATH_PLACEHOLDER, text)
    text = _TILDE_PATH.sub(PATH_PLACEHOLDER, text)
    text = _HOSTNAME.sub(PATH_PLACEHOLDER, text)
    return _SR_PATH.sub(PATH_PLACEHOLDER, text)


def decide(test_id: str, others: list[str]) -> tuple[str, str, str, str, str]:
    """Action, survivor, assertion, fold destination and the examined reason."""
    removal = REMOVALS.get(_function_id(test_id))
    if removal:
        action, survivor, assertion, fold, decision = removal
        return action, survivor, assertion, fold, _public_reason(decision)
    return ("keep", "", "", "", _public_reason(_class_reason(_function_id(test_id), others)))


def build_rows(header, compiled, meta, groups, pairs, lists) -> dict[str, list[dict]]:
    path_index = {path: SUBSYSTEMS.index(name) for name, paths in lists.items() for path in paths}
    rows = {name: [] for name in SUBSYSTEMS}
    commit = header["commit"]
    for members in groups:
        _add_group(rows, commit, members, compiled, meta, path_index)
    for left, right, score in pairs:
        _add_pair(rows, commit, left, right, score, compiled, meta, path_index)
    for name in rows:
        rows[name].sort(key=lambda row: (row["kind"], row["candidate_key"], row["test_id"]))
    return rows


def _add_group(rows, commit, members, compiled, meta, path_index) -> None:
    digest = hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
    subsystem = choose_subsystem(compiled[members[0]], meta, path_index)
    arcs = compiled[members[0]]
    for member in members:
        key = f"identical:{digest}:{member}"
        others = [item for item in members if item != member]
        action, survivor, assertion, fold, decision = decide(member, others)
        rows[subsystem].append(_row(
            commit, "identical", key, member, others, "1.000000", len(arcs),
            action, survivor, assertion, fold, decision,
        ))


def _add_pair(rows, commit, left, right, score, compiled, meta, path_index) -> None:
    smaller, larger = left, right
    key = "jaccard:" + json.dumps([smaller, larger])
    subject, other = smaller, larger
    chosen = decide(subject, [other])
    other_choice = decide(other, [subject])
    if chosen[0] == "keep" and other_choice[0] != "keep":
        subject, other = other, subject
        chosen = other_choice
    action, survivor, assertion, fold, decision = chosen
    subsystem = choose_subsystem(set(compiled[left]) | set(compiled[right]), meta, path_index)
    arc_count = len(compiled[subject])
    rows[subsystem].append(_row(
        commit, "jaccard", key, subject, [other], f"{score:.6f}", arc_count,
        action, survivor, assertion, fold, decision,
    ))


def _row(commit, kind, key, test_id, counterparts, jaccard, arc_count,
         action, survivor, assertion, fold, decision):
    return {
        "contexts_commit": commit,
        "kind": kind,
        "candidate_key": key,
        "test_id": test_id,
        "counterparts": json.dumps(counterparts),
        "jaccard": jaccard,
        "arc_count": str(arc_count),
        "action": action,
        "survivor": survivor,
        "assertion": assertion,
        "fold_destination": fold,
        "decision": decision,
    }


def invariant_problems(rows: list[dict], compiled) -> list[str]:
    """Empty arc sets, a removal of another row's survivor, and unnamed removals."""
    problems = []
    removed, survivors = [], []
    keys = []
    for row in rows:
        keys.append(row["candidate_key"])
        problems.extend(_row_problems(row, compiled))
        if row["action"] in ("delete", "fold"):
            removed.append(row["test_id"])
            survivors.append(row["survivor"])
    overlap = sorted(set(removed) & set(survivors))
    if overlap:
        problems.append(f"removal targets a surviving test: {overlap[:5]}")
    if len(keys) != len(set(keys)):
        problems.append("duplicate candidate key")
    return problems


def _row_problems(row: dict, compiled) -> list[str]:
    problems = []
    if not compiled.get(row["test_id"]):
        problems.append(f"empty arc set: {row['test_id']}")
    if row["action"] not in ("keep", "delete", "fold"):
        problems.append(f"unknown action: {row['candidate_key']}")
    filled = row["survivor"] or row["assertion"] or row["fold_destination"]
    if row["action"] == "keep" and filled:
        problems.append(f"keep row records a removal: {row['candidate_key']}")
    if row["action"] in ("delete", "fold") and not (row["survivor"] and row["assertion"]):
        problems.append(f"removal names no assertion: {row['test_id']}")
    if row["action"] == "fold" and not row["fold_destination"]:
        problems.append(f"fold names no destination: {row['test_id']}")
    if row["survivor"] and row["survivor"] == row["test_id"]:
        problems.append(f"survivor is the removed test: {row['test_id']}")
    return problems


def render(contexts_path: Path) -> dict[Path, str]:
    """The four worklists and the module manifest, as text."""
    header, contexts = _load(contexts_path)
    if int(header.get("pytest_exit", 1)) != 0:
        raise SystemExit(
            f"contexts pytest_exit is {header.get('pytest_exit')}; arcs are incomplete"
        )
    compiled, meta = compile_arcs(contexts)
    ordered = sorted(
        ((test_id, arcs) for test_id, arcs in compiled.items() if arcs),
        key=lambda item: item[0],
    )
    groups = identical_groups(compiled)
    pairs = jaccard_pairs(ordered)
    collected = collected_ids()
    lists = module_lists(tracked_modules())
    rows = build_rows(header, compiled, meta, groups, pairs, lists)
    flat = [row for name in SUBSYSTEMS for row in rows[name]]
    problems = invariant_problems(flat, compiled)
    if problems:
        raise SystemExit("worklist invariants failed:\n" + "\n".join(problems[:30]))
    texts = {FILES[name]: _csv(rows[name]) for name in SUBSYSTEMS}
    texts[MANIFEST] = _manifest(header, contexts, collected, lists, rows)
    if any(_machine_path(text) for text in texts.values()):
        raise SystemExit("a worklist still contains a machine path")
    if _MISSING:
        lines = [f"{_short_name(a)} ~ {_short_name(b)}" for a, b in sorted(_MISSING)]
        raise SystemExit("hand decision missing:\n" + "\n".join(lines))
    return texts


def _machine_path(text: str) -> bool:
    """True when ``text`` still carries an absolute path, a home, a hostname or ``sr/``."""
    return bool(
        _QUOTED_PATH.search(text) or _ABS_PATH.search(text) or _WIN_PATH.search(text)
        or _TILDE_PATH.search(text) or _HOSTNAME.search(text) or _SR_PATH.search(text)
    )


def _load(path: Path) -> tuple[dict, dict]:
    if not path.is_file():
        raise SystemExit(
            f"no contexts file at {path}; run python scripts/lean_metrics.py --contexts"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    header_keys = ("generated", "commit", "pytest", "pytest_exit", "coverage")
    header = {key: payload[key] for key in header_keys}
    return header, payload["contexts"]


def _csv(rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _manifest(header, contexts, collected, lists, rows) -> str:
    nonempty = {
        test_id for test_id, files in contexts.items()
        if isinstance(files, dict) and _arcs_of(files)
    }
    unattributed = sorted(set(collected) - nonempty)
    counts = {
        name: Counter(row["action"] for row in rows[name]) for name in SUBSYSTEMS
    }
    payload = {
        "contexts_commit": header["commit"],
        "contexts_pytest": header["pytest"],
        "contexts_pytest_exit": header["pytest_exit"],
        "coverage": header["coverage"],
        "jaccard_at_least": f"{JACCARD_NUM}/{JACCARD_DEN}",
        "assignment": (
            "A candidate is filed under the subsystem with the most of its covered "
            "arcs (the group's set, or the pair's union). Ties break toward the "
            "earlier of review-gate, worker, pickup-finish, rest."
        ),
        "decision_rule": DECISION_RULE,
        "unattributed_tests": len(unattributed),
        "unattributed_id_sha256": hashlib.sha256("\n".join(unattributed).encode()).hexdigest(),
        "unattributed_note": (
            "These collected tests have no specy_road arc in the contexts file, so "
            "they are not candidates. Subprocesses started without the coverage "
            "context are the usual cause."
        ),
        "rows": {
            name: {"keep": counts[name]["keep"], "delete": counts[name]["delete"],
                   "fold": counts[name]["fold"]}
            for name in SUBSYSTEMS
        },
        "subsystems": lists,
    }
    return json.dumps(payload, indent=2) + "\n"


def _compare(texts: dict[Path, str]) -> int:
    mismatched = [str(path.relative_to(REPO)) for path, text in texts.items()
                  if not path.is_file() or path.read_text(encoding="utf-8") != text]
    if mismatched:
        print("worklists differ from a rewrite:\n" + "\n".join(mismatched), file=sys.stderr)
        return 1
    print(f"worklists match a rewrite of {DEFAULT_CONTEXTS.relative_to(REPO)}")
    return 0


def _write(texts: dict[Path, str]) -> None:
    DEDUPE.mkdir(parents=True, exist_ok=True)
    for path, text in texts.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("contexts", nargs="?", default=str(DEFAULT_CONTEXTS))
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero unless the worklists match a fresh rewrite")
    args = parser.parse_args(argv)
    texts = render(Path(args.contexts))
    if args.check:
        return _compare(texts)
    _write(texts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
