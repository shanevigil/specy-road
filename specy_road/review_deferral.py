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
from specy_road.review_files import HUMAN, PACKET_NAME, RCA_PREFIX, ReviewFile, latest_ready, reviews_dir
from specy_road.review_target import same_commit

if TYPE_CHECKING:   # review_gate imports this module
    from specy_road.review_gate import GateResult
    from specy_road.review_rca import LoopState, Round

DEFERRAL_PREFIX = "DEFERRAL-"


def normalise_input_class(text: str) -> str:
    """Two input classes match when equal after lower-casing and collapsing whitespace (no fuzzy match)."""
    return " ".join(str(text).lower().split())


def round_of(rounds: list[Round], commit: str) -> int | None:
    """The 0-based index of the round whose commit ``commit`` names (short or full SHA), else ``None``."""
    commit = str(commit)
    return next((i for i, rnd in enumerate(rounds)
                 if rnd.commit.startswith(commit) or commit.startswith(rnd.commit)), None)


def _evidence(rcas: list[ReviewFile], applied: list[tuple[str, dict[str, Any]]], before: int) -> list[tuple[str, str]]:
    """``(file, input class)`` named before round ``before``: RCA records with an earlier trigger round, and
    applied deferrals of findings from earlier rounds (a marker item without a round takes its marker's)."""
    named = [(r.path.name, x.get("input_class")) for r in rcas if r.ok and int(r.data["trigger"]["round"]) < before
             for x in (r.data.get("deferred_findings") or [])
             + ((r.data.get("criterion_rewrite") or {}).get("finding_disposition") or [])]
    return named + [(name, x.get("input_class")) for name, m in applied for x in m.get("deferred") or []
                    if int(x.get("round") or m.get("round") or 0) < before]


def deferral_problems(rounds: list[Round], rcas: list[ReviewFile], applied: list[tuple[str, dict[str, Any]]],
                      item: dict[str, Any], covers: int) -> list[str]:
    """Why one ``deferred_findings`` item may never be deferred; empty when it may.

    The item's round is the round of its blocking commit, which must be one the RCA ``covers`` (its trigger
    round or earlier). ``rcas`` are the leaf's other RCA records and ``applied`` its applied deferrals as
    ``(file name, marker)``; only what they named before the item's own round is evidence. Each problem
    names the record or round it collides with. Whole-block coverage is :func:`block_problems`.
    """
    who = f"{item['reviewer']} @ {str(item['commit'])[:12]}"
    idx = round_of(rounds, item["commit"])
    if idx is None or not any(r.data["model"] == item["reviewer"] and r.data["verdict"] == "block"
                              for r in rounds[idx].records):
        return [f"{who}: no blocking record from {item['reviewer']} at that commit in the review history"]
    if idx + 1 > covers:
        return [f"{who}: that commit is round {idx + 1}, later than round {covers} the RCA covers"]
    out: list[str] = []
    cls = normalise_input_class(item["input_class"])
    hit = next((name for name, other in _evidence(rcas, applied, idx + 1)
                if other and normalise_input_class(other) == cls), None)
    if hit:
        out.append(f"{who}: input class {item['input_class']!r} was already named in {hit}; it is not new")
    return out


def _passed_before(rounds: list[Round], idx: int) -> dict[str, int]:
    """Acceptance id -> the first round before ``idx`` (1-based) where a record marked it ``pass``."""
    out: dict[str, int] = {}
    for i, rnd in enumerate(rounds[:idx], 1):
        for r in rnd.records:
            for a, v in (r.data.get("acceptance") or {}).items():
                if v == "pass":
                    out.setdefault(a, i)
    return out


def _binds(item_finding: str, original: str) -> bool:
    """An item cites an original finding by its text, optionally after a ``<round>/<reviewer>: `` prefix."""
    cited, text = " ".join(str(item_finding).split()), " ".join(str(original).split())
    return bool(text) and (cited == text or cited.endswith(": " + text))


def block_problems(rounds: list[Round], idx: int, reviewer: str, items: list[dict[str, Any]]) -> list[str]:
    """The one coverage check, for ``reviewer``'s blocking record in round ``idx`` (0-based), used by
    ``review defer`` and the gate alike; empty when ``items`` may resolve that block.

    Each item binds to one original finding of that record, the same category and text, one to one, and
    every original finding is bound. Every failed acceptance id is named by an item. No correctness item names
    an id an earlier round passed. A record does not say
    which finding is on which criterion, so a block with any correctness finding that also fails an id an
    earlier round passed is never resolved.
    """
    rec = next((r.data for r in rounds[idx].records if r.data["model"] == reviewer), None)
    who = f"{reviewer} @ round {idx + 1}"
    if rec is None or rec["verdict"] != "block":
        return [f"{who}: no blocking record to defer"]
    free = [(cat, text) for cat, texts in (rec.get("findings") or {}).items() for text in texts or []]
    out = []
    for x in items:
        hit = next((o for o in free if o[0] == x.get("category") and _binds(x.get("finding", ""), o[1])), None)
        if hit is None:
            out.append(f"{who}: {x.get('finding')!r} is no unlisted {x.get('category')} finding of that record")
        else:
            free.remove(hit)
    out += [f"{who}: {cat} finding {text!r} is not deferred" for cat, text in free]
    failed = sorted(a for a, v in (rec.get("acceptance") or {}).items() if v == "fail")
    out += [f"{who}: {a} fails and no item names it" for a in failed if a not in {x.get("acceptance_id") for x in items}]
    passed = _passed_before(rounds, idx)
    out += [f"{who}: a correctness finding on {x.get('acceptance_id')}, which round {passed[x.get('acceptance_id')]} "
            "marked pass" for x in items if x.get("category") == "correctness" and x.get("acceptance_id") in passed]
    if (rec.get("findings") or {}).get("correctness") and (prot := [a for a in failed if a in passed]):
        out.append(f"{who}: the block has a correctness finding and fails {', '.join(prot)}, which round "
                   f"{passed[prot[0]]} marked pass; the record does not tie findings to criteria, so it is "
                   "never deferred")
    return out


def coverage_problems(rounds: list[Round], items: list[dict[str, Any]]) -> list[str]:
    """:func:`block_problems` for each block the items name, grouped by reviewer and round."""
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for x in items:
        if (idx := round_of(rounds, x["commit"])) is not None:
            groups.setdefault((x["reviewer"], idx), []).append(x)
    return [p for (reviewer, idx), group in groups.items() for p in block_problems(rounds, idx, reviewer, group)]


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
    :func:`block_problems` finds nothing against the history. Without a marker naming the block, neither the
    ledger nor the history is read."""
    from specy_road.review_rca import review_rounds   # review_rca -> review_files; keep this module light

    applied = list_applied(repo_root, result.node_id) if result.blocks else []
    closed: set[str] | None = None
    rounds: list[Round] | None = None
    for b in list(result.blocks):
        named = [(m.get("decision"), x) for _n, m in applied for x in m.get("deferred") or []
                 if x.get("reviewer") == b.model and same_commit(repo_root, str(x.get("commit")), b.review.data["commit"])]
        if not named:
            continue
        closed = _closed_decisions(repo_root, result.node_id) if closed is None else closed
        rounds = review_rounds(repo_root, result.node_id) if rounds is None else rounds
        items = [x for d, x in named if d in closed]
        idx = round_of(rounds, str(b.review.data["commit"]))
        if items and idx is not None and not block_problems(rounds, idx, b.model, items):
            result.blocks.remove(b)
            result.ineligible.append((b.review, "deferred by " + ", ".join(dict.fromkeys(
                str(d) for d, _x in named if d in closed))))


_EXECUTOR_ACTIONS = ("continue_with_class_fix", "restart_executor_fresh", "fix_tests", "fix_environment")


def _next_for(repo_root: Path, node_id: str, rca: ReviewFile, loop: LoopState,
              executor: str | None) -> tuple[str | None, str]:
    """``(command, why)`` that advances a covering RCA's recommended action; the command is runnable as printed.
    An applied deferral leaves no budget step (``None``): its remaining blocks are fixed in this leaf, and a
    forced RCA would be refused until another review round. A deferral ``review defer`` would refuse goes to
    a human decision instead."""
    from specy_road.bundled_scripts.review_defer import applicable_record   # it imports this module

    action, name = rca.data["recommended_action"], rca.path.name
    why = f"{name} recommends {action['type']}: {action['instructions']}"
    if action["type"] == "defer_findings":
        marker = marker_path(repo_root, node_id, name)
        if marker.exists():
            return None, (f"{name} is applied ({marker.name}); the blocks it did not defer are fixed in this "
                          "leaf, and the budget is checked again after the next review round")
        refused = applicable_record(repo_root, node_id, str(rca.path))[1]
        if refused is None:
            return f"specy-road review defer {node_id} --rca {shlex.quote(str(rca.path))}", why
        why = f"{why}; `review defer` would refuse it: {' '.join(refused.split())}"
    blockers = [r.data["model"] for r in loop.rounds[-1].records if r.data["verdict"] == "block"] if loop.rounds else []
    if action["type"] in _EXECUTOR_ACTIONS and executor:
        return f"specy-road prompt {node_id} --role executor --model {shlex.quote(executor)}", why
    if action["type"] == "change_or_reprompt_reviewer" and blockers:
        if not (reviews_dir(repo_root, node_id) / PACKET_NAME).is_file():   # the reviewer prompt needs it
            return f"specy-road review-packet {node_id}", why + "; then re-prompt " + blockers[0]
        return f"specy-road prompt {node_id} --role reviewer --model {shlex.quote(blockers[0])}", why
    return _human_decision(node_id, f"{name}: {action['type']}", why, action["instructions"],
                           f"root-cause analysis {name}"), why + " (a human applies it)"


def _human_decision(node_id: str, summary: str, why: str, effect: str, reason: str) -> str:
    """A complete ``decisions add`` asking a human to act: the step when nothing an agent runs would succeed."""
    return " ".join(["specy-road decisions add", node_id, "--kind decision", "--summary", shlex.quote(summary),
                     "--why", shlex.quote(why), "--option", shlex.quote(f"apply|{effect}"),
                     "--option", shlex.quote("decline|keep the current review loop"),
                     "--recommendation apply --recommendation-reason", shlex.quote(reason), "--default decline"])


def fix_round_budget(repo_root: Path, config: dict[str, Any], loop: LoopState,
                     node_id: str) -> dict[str, Any] | None:
    """``None`` when ``policy.max_fix_rounds`` is unset; else the blocking rounds, whether the budget is spent,
    and the next step: the RCA when none covers the latest round, else what advances that RCA's action.
    ``next`` is a command only (``None`` when no budget step is left); ``next_why`` explains it."""
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
    if not covering and analyst:
        nxt = (f"specy-road prompt {node_id} --role rca --force --reason 'fix-round budget spent' "
               f"--model {shlex.quote(analyst)}")
        why = "no root-cause analysis covers the latest round"
    elif not covering:   # prompt --role rca refuses every party, so no analyst command would run
        why = ("no root-cause analysis covers the latest round, and no rostered reviewer that neither "
               "implemented nor reviewed the leaf can write one")
        nxt = _human_decision(node_id, "fix-round budget spent: no independent analyst", why,
                              "add an independent reviewer to the roster, or stop the loop by hand",
                              "the budget is spent and no agent may analyse the loop")
    else:
        executors = {e.get("id") for e in config.get("roster") or [] if "executor" in (e.get("roles") or [])}
        agent = ready.data.get("agent") if ready else None   # prompt refuses a model without the executor role
        nxt, why = _next_for(repo_root, node_id, covering[-1], loop, agent if agent in executors else None)
    return {"max_fix_rounds": int(budget), "blocking_rounds": blocking, "spent": blocking >= int(budget),
            "next": nxt, "next_why": why}
