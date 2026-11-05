"""The fix-round budget and the deferral of new-input-class findings to a follow-up leaf.

``policy.max_fix_rounds`` (unset: no budget) caps the blocking review rounds one
leaf may spend; once spent, ``handoff status`` reports ``fix_round_budget_spent``
and names the next command (:func:`fix_round_budget`). An RCA record of type
``defer_findings`` proposes moving findings whose **input class** is new to a
follow-up leaf; :func:`deferral_problems` is the rule that refuses one, and a
human applies the rest with ``specy-road review defer``, which leaves a
``DEFERRAL-<round>.yaml`` marker beside the RCA record. The gate then treats the
deferring reviewer's block at that commit as resolved, and nothing else
(:func:`apply_deferrals`). Design: ``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from specy_road.decisions import decisions_path, read_decisions
from specy_road.review_files import HUMAN, RCA_PREFIX, ReviewFile, latest_ready, reviews_dir
from specy_road.review_target import same_commit

if TYPE_CHECKING:   # review_gate imports this module
    from specy_road.review_gate import GateResult
    from specy_road.review_rca import LoopState, Round

DEFERRAL_PREFIX = "DEFERRAL-"


def normalise_input_class(text: str) -> str:
    """Two input classes match when equal after lower-casing and collapsing whitespace (no fuzzy match)."""
    return " ".join(str(text).lower().split())


def _round_of(rounds: list[Round], commit: str) -> int | None:
    commit = str(commit)
    return next((i for i, rnd in enumerate(rounds)
                 if rnd.commit.startswith(commit) or commit.startswith(rnd.commit)), None)


def deferral_problems(rounds: list[Round], rcas: list[ReviewFile], applied: list[tuple[str, dict[str, Any]]],
                      item: dict[str, Any]) -> list[str]:
    """Why one ``deferred_findings`` item may never be deferred; empty when it may.

    ``rcas`` are the leaf's other RCA records and ``applied`` its applied deferrals as ``(file name, marker)``.
    Each problem names the record or round it collides with.
    """
    who = f"{item['reviewer']} @ {str(item['commit'])[:12]}"
    out: list[str] = []
    cls = normalise_input_class(item["input_class"])
    named = [(r.path.name, x.get("input_class")) for r in rcas if r.ok
             for x in (r.data.get("deferred_findings") or [])
             + ((r.data.get("criterion_rewrite") or {}).get("finding_disposition") or [])]
    named += [(name, x.get("input_class")) for name, m in applied for x in m.get("deferred") or []]
    hit = next((name for name, other in named if other and normalise_input_class(other) == cls), None)
    if hit:
        out.append(f"{who}: input class {item['input_class']!r} was already named in {hit}; it is not new")
    idx = _round_of(rounds, item["commit"])
    if idx is None or not any(r.data["model"] == item["reviewer"] and r.data["verdict"] == "block"
                              for r in rounds[idx].records):
        return out + [f"{who}: no blocking record from {item['reviewer']} at that commit in the review history"]
    if item["category"] == "correctness":
        for i, rnd in enumerate(rounds[:idx], 1):
            passed = [r.data["model"] for r in rnd.records
                      if (r.data.get("acceptance") or {}).get(item["acceptance_id"]) == "pass"]
            if passed:
                out.append(f"{who}: a correctness finding on {item['acceptance_id']}, which round {i} "
                           f"({', '.join(passed)}) marked pass")
                break
    return out


def uncovered(record: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    """What a blocking record names that ``items`` (its reviewer's deferred findings at its commit) leave open:
    each failed acceptance id no item names, and each findings category with more findings than items."""
    ids = {x.get("acceptance_id") for x in items}
    out = [f"{a}: fail" for a, v in sorted((record.get("acceptance") or {}).items()) if v == "fail" and a not in ids]
    for cat, found in (record.get("findings") or {}).items():
        if len(found or []) > (n := sum(1 for x in items if x.get("category") == cat)):
            out.append(f"{len(found) - n} {cat} finding(s)")
    return out


def coverage_problems(rounds: list[Round], items: list[dict[str, Any]]) -> list[str]:
    """Per (reviewer, commit) the items name: the findings of that block the items leave undeferred."""
    out = []
    for reviewer, commit in dict.fromkeys((x["reviewer"], str(x["commit"])) for x in items):
        idx = _round_of(rounds, commit)
        rec = next((r for r in rounds[idx].records if r.data["model"] == reviewer), None) if idx is not None else None
        group = [x for x in items if x["reviewer"] == reviewer and str(x["commit"]) == commit]
        if rec is not None and (left := uncovered(rec.data, group)):
            out.append(f"{reviewer} @ {commit[:12]}: deferring would leave {', '.join(left)} of that block "
                       "undeferred; list every finding of the block, or fix it in this leaf")
    return out


def marker_path(repo_root: Path, node_id: str, rca_name: str) -> Path:
    """``DEFERRAL-<round>.yaml`` beside ``RCA-<round>.md`` (gitignored, like the records it qualifies)."""
    return reviews_dir(repo_root, node_id) / f"{DEFERRAL_PREFIX}{Path(rca_name).stem.removeprefix(RCA_PREFIX)}.yaml"


def list_applied(repo_root: Path, node_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Every applied deferral marker of the leaf as ``(file name, data)``; an unreadable one is skipped."""
    d = reviews_dir(repo_root, node_id)
    out = []
    for p in sorted(d.glob(f"{DEFERRAL_PREFIX}*.yaml")) if d.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("node_id") == node_id:
            out.append((p.name, data))
    return out


def write_marker(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _closed_decisions(repo_root: Path, node_id: str) -> set[str]:
    """Closed decision ids of the node; an unreadable ledger closes nothing, so every block keeps counting."""
    try:
        doc = read_decisions(decisions_path(repo_root))
    except (OSError, yaml.YAMLError):
        return set()
    entries = doc.get("entries") if isinstance(doc, dict) else None
    return {e.get("id") for e in entries or [] if isinstance(e, dict) and e.get("status") == "closed"
            and e.get("node") == node_id}


def apply_deferrals(repo_root: Path, result: GateResult) -> None:
    """Move a counted block to ``ineligible`` when closed, applied deferrals name its reviewer and commit and
    cover every finding it names (:func:`uncovered`). Without a marker naming the block, the ledger is not read."""
    applied = list_applied(repo_root, result.node_id) if result.blocks else []
    closed: set[str] | None = None
    for b in list(result.blocks):
        named = [(m.get("decision"), x) for _n, m in applied for x in m.get("deferred") or []
                 if x.get("reviewer") == b.model and same_commit(repo_root, str(x.get("commit")), b.review.data["commit"])]
        if not named:
            continue
        closed = _closed_decisions(repo_root, result.node_id) if closed is None else closed
        items = [x for d, x in named if d in closed]
        if items and not uncovered(b.review.data, items):
            result.blocks.remove(b)
            result.ineligible.append((b.review, "deferred by " + ", ".join(dict.fromkeys(
                str(d) for d, _x in named if d in closed))))


_EXECUTOR_ACTIONS = ("continue_with_class_fix", "restart_executor_fresh", "fix_tests", "fix_environment")


def _next_for(node_id: str, rca: ReviewFile, loop: LoopState, executor: str | None) -> tuple[str, str]:
    """``(command, why)`` that advances a covering RCA's recommended action; the command is runnable as printed."""
    action, name = rca.data["recommended_action"], rca.path.name
    why = f"{name} recommends {action['type']}: {action['instructions']}"
    if action["type"] == "defer_findings":
        return f"specy-road review defer {node_id} --rca {shlex.quote(str(rca.path))}", why
    blockers = [r.data["model"] for r in loop.rounds[-1].records if r.data["verdict"] == "block"] if loop.rounds else []
    if action["type"] in _EXECUTOR_ACTIONS and executor:
        return f"specy-road prompt {node_id} --role executor --model {shlex.quote(executor)}", why
    if action["type"] == "change_or_reprompt_reviewer" and blockers:
        return f"specy-road prompt {node_id} --role reviewer --model {shlex.quote(blockers[0])}", why
    return " ".join(["specy-road decisions add", node_id, "--kind decision", "--summary",
                     shlex.quote(f"{name}: {action['type']}"), "--why", shlex.quote(why),
                     "--option", shlex.quote(f"apply|{action['instructions']}"),
                     "--option", shlex.quote("decline|keep the current review loop"),
                     "--recommendation apply --recommendation-reason", shlex.quote(f"root-cause analysis {name}"),
                     "--default decline"]), why + " (a human applies it)"


def fix_round_budget(repo_root: Path, config: dict[str, Any], loop: LoopState,
                     node_id: str) -> dict[str, Any] | None:
    """``None`` when ``policy.max_fix_rounds`` is unset; else the blocking rounds, whether the budget is spent,
    and the next step: the RCA when none covers the latest round, else what advances that RCA's action.
    ``next`` is a command only; ``next_why`` explains it."""
    from specy_road.review_rca import rca_parties   # review_rca -> review_files; keep this module light

    budget = (config.get("policy") or {}).get("max_fix_rounds")
    if budget is None:
        return None
    parties = rca_parties(repo_root, node_id, loop)
    analyst = next((e["id"] for e in config.get("roster") or [] if "reviewer" in (e.get("roles") or [])
                    and e.get("id") not in parties and e.get("id") != HUMAN), None)
    ready = latest_ready(repo_root, node_id)
    blocking = sum(1 for rnd in loop.rounds if any(r.data["verdict"] == "block" for r in rnd.records))
    covering = [r for r in loop.rcas if r.ok and int(r.data["trigger"]["round"]) >= len(loop.rounds)]
    if not covering:
        nxt = (f"specy-road prompt {node_id} --role rca --force --reason 'fix-round budget spent' "
               f"--model {shlex.quote(analyst) if analyst else 'MODEL'}")
        why = "no root-cause analysis covers the latest round" + (
            "" if analyst else "; MODEL: a rostered reviewer that neither implemented nor reviewed the leaf")
    else:
        nxt, why = _next_for(node_id, covering[-1], loop, ready.data.get("agent") if ready else None)
    return {"max_fix_rounds": int(budget), "blocking_rounds": blocking, "spent": blocking >= int(budget),
            "next": nxt, "next_why": why}
