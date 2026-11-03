"""Escalate a review loop that is not converging, and build its root-cause prompt.

A **round** is one reviewed commit in the order ``review record`` filed it
(``work/reviews/<ID>/history/``); it **blocks on** ``A<n>`` when a blocking
record at that commit (the latest per model) marks ``A<n>: fail``. A leaf is
escalated when the last ``escalate_same_acceptance_blocks`` rounds all block on
one acceptance id; when one reviewer family (from the roster) blocked that many
of the rounds it reviewed in a row, whatever ids or models it named; or after
``escalate_review_rounds`` rounds. A coordinator may also force an analysis with
a reason (:func:`forced_escalation`). An ``RCA-*.md`` record resolves every
round up to its ``trigger.round``, so counting restarts after each analysis.
Thresholds come from the gate's policy (the integration branch). Design:
``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from specy_road.git_subprocess import git_stdout
from specy_road.orchestration_config import (
    effective_config,
    family_of,
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

    def family_verdicts(self, family: Callable[[str], str]) -> dict[str, bool]:
        """Each family that filed here -> whether any of its models blocks."""
        out: dict[str, bool] = {}
        for r in self.records:
            f = family(r.data["model"])
            out[f] = out.get(f, False) or r.data["verdict"] == "block"
        return out


@dataclass
class Escalation:
    rule: str
    round: int
    acceptance_ids: list[str]
    threshold: int
    family: str | None = None   # same_family: the family that kept blocking
    reason: str | None = None   # forced: the coordinator's reason

    def describe(self) -> str:
        if self.rule == "same_acceptance":
            return (f"the last {self.threshold} review rounds all block on {', '.join(self.acceptance_ids)} "
                    f"(same_acceptance, round {self.round})")
        if self.rule == "same_family":
            return (f"{self.family} reviewers blocked the last {self.threshold} rounds they reviewed "
                    f"(same_family, round {self.round})")
        if self.rule == "forced":
            return f"a coordinator forced an analysis, giving the reason {self.reason!r} (forced, round {self.round})"
        return f"{self.threshold} review rounds without converging (review_rounds, round {self.round})"

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "round": self.round, "acceptance_ids": self.acceptance_ids,
                "threshold": self.threshold, "family": self.family, "reason": self.reason,
                "describe": self.describe()}


@dataclass
class LoopState:
    rounds: list[Round]
    rcas: list[ReviewFile]
    escalation: Escalation | None
    resolved: int = 0   # rounds an RCA record already covers

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
    esc = escalation(rounds[:rnd], policy, resolved, _family(config))
    if esc is None and trig["rule"] == "forced":
        esc = forced_escalation(rounds[:rnd], resolved, trig.get("reason") or "")
        if esc is None:
            errs.append(f"trigger.rule is 'forced', but no review round after round {resolved} is up to "
                        f"round {rnd}")
            return errs
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


def _family(config: dict[str, Any]) -> Callable[[str], str]:
    """A model's roster family; a model the roster does not name is its own family."""
    return lambda model: family_of(config, model) or model


def _family_streak(window: list[Round], family: Callable[[str], str], n: int) -> str | None:
    """The family whose last ``n`` verdicts (one per round it reviewed in ``window``) all block."""
    seq: dict[str, list[bool]] = {}
    for rnd in window:
        for f, blocked in rnd.family_verdicts(family).items():
            seq.setdefault(f, []).append(blocked)
    return next((f for f, v in sorted(seq.items()) if len(v) >= n and all(v[-n:])), None)


def escalation(rounds: list[Round], policy: dict[str, Any], resolved: int = 0,
               family: Callable[[str], str] | None = None) -> Escalation | None:
    """The rule active after ``rounds``; ``family`` maps a model to its family (default: the model id)."""
    window = rounds[resolved:]
    same = int(policy["escalate_same_acceptance_blocks"])
    if len(window) >= same:
        ids = set.intersection(*(r.failed for r in window[-same:]))
        if ids:
            return Escalation("same_acceptance", len(rounds), sorted(ids, key=_id_key), same)
    fam = _family_streak(window, family or (lambda m: m), same)
    if fam is not None:
        return Escalation("same_family", len(rounds), [], same, family=fam)
    total = int(policy["escalate_review_rounds"])
    if len(window) >= total:
        return Escalation("review_rounds", len(rounds), [], total)
    return None


def forced_escalation(rounds: list[Round], resolved: int, reason: str) -> Escalation | None:
    """A coordinator-initiated analysis of the rounds since the last RCA; ``None`` when there are none."""
    if len(rounds) <= resolved or not reason.strip():
        return None
    return Escalation("forced", len(rounds), [], 0, reason=reason.strip())


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
    return LoopState(rounds, rcas, escalation(rounds, policy, resolved, _family(config)), resolved)


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


def rca_trigger(repo_root: Path, node_id: str, model: str, loop: LoopState,
                force_reason: str | None = None) -> tuple[Escalation | None, str | None]:
    """``(escalation the prompt analyses, error)``. ``force_reason`` (``prompt --role rca --force --reason``)
    starts a coordinator-initiated analysis when nothing is escalated; an active escalation wins over it."""
    esc = loop.escalation
    if esc is not None and force_reason:
        print(f"note: {node_id} is already escalated ({esc.describe()}); --force is ignored", file=sys.stderr)
    if esc is None and force_reason:
        esc = forced_escalation(loop.rounds, loop.resolved, force_reason)
        if esc is None:
            return None, (f"{node_id} has no review round since the last root-cause analysis; "
                          "there is nothing to analyse")
    if esc is None:
        return None, (f"{node_id}'s review loop is not escalated; no root-cause analysis is due "
                      f"(`specy-road handoff status {node_id}`); a coordinator can start one anyway "
                      "with `--force --reason '<why>'`")
    if model in rca_parties(repo_root, node_id, loop):
        return None, (f"{model!r} implemented or reviewed {node_id}; the root-cause analyst must be "
                      "a rostered reviewer that is neither")
    return esc, None


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
        f"trigger: {{rule: {esc.rule}, acceptance_ids: [{ids}], round: {esc.round}"
        + (f", reason: {json.dumps(esc.reason)}" if esc.reason else "") + "}",
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
        f"`specy-road handoff status {node_id}`: a valid record clears the escalation (a forced one restarts "
        "the round count), and an invalid one is "
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
