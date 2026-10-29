"""Escalate a review loop that is not converging, and build its root-cause prompt.

A **round** is one reviewed commit in the order ``review record`` filed it
(``work/reviews/<ID>/history/``); it **blocks on** ``A<n>`` when a blocking
record at that commit (the latest per model) marks ``A<n>: fail``. A leaf is
escalated when the last ``escalate_same_acceptance_blocks`` rounds all block on
one acceptance id, or after ``escalate_review_rounds`` rounds. An ``RCA-*.md``
record resolves every round up to its ``trigger.round``, so counting restarts
after each analysis. Thresholds come from the gate's policy (the integration
branch). Design: ``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_stdout
from specy_road.orchestration_config import (
    effective_config,
    is_rostered_reviewer,
    substitute_for,
)
from specy_road.review_files import (
    RCA_PREFIX,
    ReviewFile,
    list_rcas,
    list_ready,
    list_review_history,
    reviews_dir,
)
from specy_road.review_policy_ref import policy_source
from specy_road.review_target import ReviewTarget, full_sha

CLASSES = ("specification", "implementation", "test", "reviewer", "environment", "hard_problem")
ACTIONS = ("amend_criterion", "split_leaf", "continue_with_class_fix", "restart_executor_fresh",
           "fix_tests", "change_or_reprompt_reviewer", "fix_environment", "escalate_human")


@dataclass
class Round:
    commit: str
    records: list[ReviewFile]

    @property
    def failed(self) -> set[str]:
        return {a for r in self.records if r.data["verdict"] == "block"
                for a, v in (r.data.get("acceptance") or {}).items() if v == "fail"}


@dataclass
class Escalation:
    rule: str
    round: int
    acceptance_ids: list[str]
    threshold: int

    def describe(self) -> str:
        if self.rule == "same_acceptance":
            return (f"the last {self.threshold} review rounds all block on {', '.join(self.acceptance_ids)} "
                    f"(same_acceptance, round {self.round})")
        return f"{self.threshold} review rounds without converging (review_rounds, round {self.round})"

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "round": self.round, "acceptance_ids": self.acceptance_ids,
                "threshold": self.threshold, "describe": self.describe()}


@dataclass
class LoopState:
    rounds: list[Round]
    rcas: list[ReviewFile]
    escalation: Escalation | None

    def problems(self) -> list[str]:
        return [f"{r.path.name}: invalid — {'; '.join(r.errors)}" for r in self.rcas if not r.ok]


def review_rounds(repo_root: Path, node_id: str) -> list[Round]:
    """One round per commit object; the latest record per model at it counts.

    Records may quote a short SHA or the full id (the schema allows 7–40 hex
    chars). ``full_sha`` folds those onto one key; a commit git cannot resolve
    keeps its raw string.
    """
    by_commit: dict[str, dict[str, ReviewFile]] = {}
    for r in list_review_history(repo_root, node_id):
        if r.ok and r.data.get("node_id") == node_id:
            key = full_sha(repo_root, r.data["commit"]) or r.data["commit"]
            by_commit.setdefault(key, {})[r.data["model"]] = r
    return [Round(c, list(m.values())) for c, m in by_commit.items()]


def _id_key(aid: str) -> int:
    return int(aid[1:])


def _trigger_ids(ids: list[str] | None) -> list[str]:
    return sorted(ids or [], key=_id_key)


def _rca_semantic_errors(
    repo_root: Path,
    node_id: str,
    data: dict[str, Any],
    rounds: list[Round],
    policy: dict[str, Any],
    config: dict[str, Any],
    resolved: int,
) -> list[str]:
    """Whether an RCA record matches the escalation it claims and an independent analyst filed it."""
    errs: list[str] = []
    trig = data["trigger"]
    rnd = int(trig["round"])
    if rnd > len(rounds):
        return [f"trigger.round is {rnd}, but the history has {len(rounds)} round(s)"]
    esc = escalation(rounds[:rnd], policy, resolved)
    if esc is None:
        errs.append("trigger does not match an escalation active at that round")
        return errs
    if trig["rule"] != esc.rule:
        errs.append(f"trigger.rule is {trig['rule']!r}, expected {esc.rule!r} for that round")
    if _trigger_ids(trig.get("acceptance_ids")) != esc.acceptance_ids:
        errs.append(f"trigger.acceptance_ids {trig.get('acceptance_ids')!r} do not match "
                    f"escalation {esc.acceptance_ids!r}")
    model = data["model"]
    parties = rca_parties(repo_root, node_id, LoopState(rounds, [], None))
    if model in parties:
        errs.append(f"model {model!r} implemented or reviewed this leaf and may not file an RCA")
    elif not is_rostered_reviewer(config, model) and substitute_for(config, node_id, model) is None:
        errs.append(f"model {model!r} is not a rostered reviewer for this leaf")
    return errs


def escalation(rounds: list[Round], policy: dict[str, Any], resolved: int = 0) -> Escalation | None:
    window = rounds[resolved:]
    same = int(policy["escalate_same_acceptance_blocks"])
    if len(window) >= same:
        ids = set.intersection(*(r.failed for r in window[-same:]))
        if ids:
            return Escalation("same_acceptance", len(rounds), sorted(ids, key=_id_key), same)
    total = int(policy["escalate_review_rounds"])
    if len(window) >= total:
        return Escalation("review_rounds", len(rounds), [], total)
    return None


def loop_state(repo_root: Path, node_id: str) -> LoopState:
    config, _ = effective_config(repo_root, policy_source(repo_root)[0])
    policy = config["policy"]
    rounds = review_rounds(repo_root, node_id)
    rcas = list_rcas(repo_root, node_id)
    resolved = 0
    for r in sorted((x for x in rcas if x.ok), key=lambda x: int(x.data["trigger"]["round"])):
        r.errors.extend(_rca_semantic_errors(repo_root, node_id, r.data, rounds, policy, config, resolved))
        if r.ok:
            resolved = max(resolved, int(r.data["trigger"]["round"]))
    return LoopState(rounds, rcas, escalation(rounds, policy, resolved))


def escalated_note(loop: LoopState, node_id: str) -> list[str]:
    """What a review prompt says while the loop is escalated and no RCA covers it."""
    if loop.escalation is None:
        return []
    return [
        "## Loop escalated",
        "",
        f"This leaf's review loop is escalated: {loop.escalation.describe()}. Another review round is not "
        f"the next step: a root-cause analysis is (`specy-road prompt {node_id} --role rca --model <id>`). "
        "If you were sent anyway, review as asked, judge each item against its text as written, and do not "
        "raise a finding the earlier rounds already raised unless the diff reintroduced it.",
        "",
    ]


def rca_parties(repo_root: Path, node_id: str, loop: LoopState) -> set[str]:
    """Models that may not analyse the loop: its executors and its reviewers."""
    return ({str(r.data.get("agent")) for r in list_ready(repo_root, node_id) if r.ok}
            | {r.data["model"] for rnd in loop.rounds for r in rnd.records})


def _skeleton(node_id: str, model: str, esc: Escalation) -> list[str]:
    ids = ", ".join(esc.acceptance_ids)
    return [
        "```yaml",
        "---",
        f"node_id: {node_id}",
        f"model: {model}",
        "date: YYYY-MM-DD",
        f"trigger: {{rule: {esc.rule}, acceptance_ids: [{ids}], round: {esc.round}}}",
        "classification: {primary: <class>, secondary: <class, optional>, confidence: 0.0-1.0}",
        "evidence:",
        "  - {kind: finding|commit|acceptance|signal|check_result, ref: <round/reviewer, sha, A#, check>, "
        "supports: primary|secondary|against, note: <one line>}",
        "recommended_action: {type: <action>, instructions: <what to do>, requires_human_approval: true|false}",
        "criterion_rewrite:   # required when primary is specification",
        "  acceptance_id: A#",
        "  original_text: <as in the brief>",
        "  proposed_text: <bounded rewrite>",
        "  finding_disposition:",
        "    - {finding: <round/reviewer: text>, label: in_scope_must_fix|out_of_scope_now|already_resolved, "
        "justification: <one line>}",
        "---",
        "<your reasoning: evidence for and against each class, and the counterfactuals>",
        "```",
        "",
    ]


def rca_preamble(repo_root: Path, node_id: str, model: str, esc: Escalation) -> list[str]:
    out = reviews_dir(repo_root, node_id) / f"{RCA_PREFIX}{esc.round}.md"
    return [
        "## Your role: root-cause analyst",
        "",
        f"Leaf `{node_id}`'s implement/review loop is escalated: {esc.describe()}. You did not implement "
        "it and did not review it. Do not fix code, re-review the change, or edit any tracked file: diagnose "
        "why the loop is not converging, from the brief, the review history and the diffs below.",
        "",
        f"1. Classify the primary cause as exactly one of {', '.join(f'`{c}`' for c in CLASSES)}, optionally "
        "with one secondary. `specification`: the criterion admits more than one reasonable reading or leaves "
        "its scope open (typical sign: each round's findings name a new input class on the same criterion). "
        "`reviewer`: findings contradict the criterion's text, repeat, or land on lines unchanged since an "
        "earlier pass. `environment`: wrong base, stale packet, touch zones, or verify already failing at the "
        "base. `hard_problem`: every finding is real and each fix creates a new one.",
        "2. For each class, give the evidence for and against, citing round, reviewer, acceptance id or "
        "commit; a claim without a citation is ignored. Then the counterfactual: the smallest intervention "
        "for that class, and which past blocking findings it would have prevented. Prefer the class whose "
        "counterfactual prevents the most findings with the smallest change.",
        "3. Where a check you can run settles it (a test, a git command, the criterion read against the "
        "diff), run it and cite the result as `check_result` evidence. Do not run a debate or a self-critique "
        "loop.",
        f"4. Name the cheapest corrective action, one of {', '.join(f'`{a}`' for a in ACTIONS)}. When the "
        "class is `specification`, write a bounded rewrite of the criterion: what is in and out of scope, "
        "every term defined operationally, no wider than the original; then label every past blocking finding "
        "on it. A rewrite is a proposal for a human: set `requires_human_approval: true` and never edit the "
        "roadmap.",
        f"5. Write the record to `{out}` (gitignored; open the absolute path) in this shape, validated against "
        "specy-road's `rca-record` schema, then run "
        f"`specy-road handoff status {node_id}`: a valid record clears the escalation, and an invalid one is "
        "listed as a problem. Stop.",
        "",
        *_skeleton(node_id, model, esc),
    ]


def _diff(repo_root: Path, a: str | None, b: str) -> list[str]:
    text = (git_stdout(["diff", a, b], repo_root) or "") if a else ""
    if not text.strip():
        return ["_(empty, or git could not produce it)_", ""]
    ticks = "````" if "```" in text else "```"
    return [f"{ticks}diff", text.rstrip(), ticks, ""]


def _record_lines(r: ReviewFile) -> list[str]:
    d = r.data
    failed = sorted((a for a, v in (d.get("acceptance") or {}).items() if v == "fail"), key=_id_key)
    out = [f"#### {d['model']} ({d.get('family') or '?'}): {d['verdict']}"
           + (f", fails {', '.join(failed)}" if failed else ""), ""]
    for key, items in (d.get("findings") or {}).items():
        out += [f"- {key}: {x}" for x in items]
    out += [f"- required change: {x}" for x in d.get("required_changes") or []]
    body = r.body.strip()
    return out + ([""] + [f"> {line}" if line else ">" for line in body.splitlines()] if body else []) + [""]


def rca_evidence(repo_root: Path, t: ReviewTarget, loop: LoopState) -> list[str]:
    """Every round side by side, then the diff each round answered; the brief precedes this."""
    out = ["---", "", "## Review history", "",
           "_Every record `review record` filed for this leaf, grouped by the commit reviewed (oldest first)._",
           ""]
    prev = t.base
    for i, rnd in enumerate(loop.rounds, 1):
        out += [f"### Round {i}: `{rnd.commit[:12]}`", ""]
        for r in rnd.records:
            out += _record_lines(r)
        label = "changes since the base" if i == 1 else f"what round {i} changed after round {i - 1}'s review"
        out += [f"**Diff: {label}**", ""] + _diff(repo_root, prev, rnd.commit)
        prev = rnd.commit
    return out
