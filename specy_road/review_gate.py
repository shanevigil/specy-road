"""Decide whether a node's implementation has the reviews its policy requires.

The rule ``mark-implementation-reviewed`` enforces, and ``handoff status``
reports. A review record counts only when all of these hold:

* it validates (schema plus :func:`review_files.review_semantic_errors`,
  including a result for every acceptance id in the brief);
* its ``commit`` is the commit under review — any later commit makes it stale,
  which is how "a substantive fix restarts both reviews" needs no extra state;
* it is for this node, and no other record from the same model already counts;
* its model is rostered with the ``reviewer`` role, or is the substitute in an
  active substitution covering this node — its family always comes from the
  roster, never from the file;
* it attests a fresh session when policy requires one.

Policy is read from ``roadmap/orchestration.yaml`` **as committed on the
integration branch** (its remote-tracking ref when present), and the gate is on
when either that branch or the working tree turns it on: a feature branch
cannot lower its own bar.

The gate passes when no counted record blocks and the counted approvals reach
``reviewers_required`` — counted by distinct family when
``reviewers_distinct_families`` is set.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_stdout
from specy_road.git_workflow_config import (
    require_implementation_review_before_finish,
    resolve_integration_defaults,
)
from specy_road.orchestration_config import (
    effective_config,
    family_of,
    is_rostered_reviewer,
    substitute_for,
)
from specy_road.review_files import HUMAN, ReviewFile, list_reviews, render_front_matter, review_path
from specy_road.review_target import full_sha, resolve_target_or_exit, same_commit


def policy_ref(repo_root: Path) -> str | None:
    """The integration branch ref policy is read from, or ``None`` (working tree)."""
    ib, remote, _ = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)
    return base_ref(repo_root, remote, ib)


def review_required(repo_root: Path) -> bool:
    """Whether the review gate is on — in the working tree **or** on the integration branch."""
    if require_implementation_review_before_finish(repo_root):
        return True
    ref = policy_ref(repo_root)
    text = git_stdout(["show", f"{ref}:roadmap/git-workflow.yaml"], repo_root) if ref else None
    try:
        data = yaml.safe_load(text) if text else None
    except yaml.YAMLError:
        return False
    return isinstance(data, dict) and bool(data.get("require_implementation_review_before_finish"))


@dataclass
class CountedReview:
    review: ReviewFile
    family: str
    substitution: dict[str, Any] | None = None

    @property
    def model(self) -> str:
        return self.review.data["model"]

    @property
    def verdict(self) -> str:
        return self.review.data["verdict"]


@dataclass
class GateResult:
    node_id: str
    commit: str | None
    required: int
    distinct_families: bool
    approvals: list[CountedReview] = field(default_factory=list)
    blocks: list[CountedReview] = field(default_factory=list)
    stale: list[ReviewFile] = field(default_factory=list)
    invalid: list[ReviewFile] = field(default_factory=list)
    ineligible: list[tuple[ReviewFile, str]] = field(default_factory=list)
    config_error: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def approval_count(self) -> int:
        if self.distinct_families:
            return len({a.family for a in self.approvals})
        return len(self.approvals)

    @property
    def passed(self) -> bool:
        return (
            self.config_error is None
            and self.commit is not None
            and not self.blocks
            and self.approval_count >= self.required
        )

    def summary(self) -> str:
        unit = "distinct-family approvals" if self.distinct_families else "approvals"
        state = "met" if self.passed else "not met"
        return f"{self.approval_count}/{self.required} {unit}, {len(self.blocks)} block(s): {state}"

    def problems(self) -> list[str]:
        out = []
        if self.config_error:
            out.append(f"orchestration config: {self.config_error}")
        if self.commit is None:
            out.append("no commit under review could be resolved")
        for b in self.blocks:
            out.append(f"{b.review.path.name}: {b.model} blocks this commit")
        for r in self.stale:
            out.append(f"{r.path.name}: reviewed {r.data.get('commit')}, not the current commit — re-review")
        for r in self.invalid:
            out.append(f"{r.path.name}: invalid — {'; '.join(r.errors)}")
        for r, why in self.ineligible:
            out.append(f"{r.path.name}: does not count — {why}")
        if self.approval_count < self.required:
            unit = "distinct-family approvals" if self.distinct_families else "approvals"
            out.append(f"need {self.required} {unit} at this commit, have {self.approval_count}")
        return out


def _eligibility(
    config: dict[str, Any], node_id: str, review: ReviewFile, today: date | None
) -> tuple[CountedReview | None, str | None]:
    model = review.data["model"]
    sub = None
    if not is_rostered_reviewer(config, model):
        sub = substitute_for(config, node_id, model, today)
        if sub is None:
            return None, (
                f"model {model!r} is not a rostered reviewer and no active substitution "
                f"covers {node_id} (roadmap/orchestration.yaml)"
            )
    if config["policy"].get("reviewer_fresh_session", True) and not review.data.get("fresh_session"):
        return None, "policy requires a fresh reviewer session (fresh_session: true)"
    family = family_of(config, model)
    if not family:
        return None, f"no family for {model!r}: add it to the roster"
    return CountedReview(review, family, sub), None


def _count(result: GateResult, counted: CountedReview) -> None:
    """One vote per model: a block from any of its records wins, extras are listed."""
    same = [c for c in result.approvals + result.blocks if c.model == counted.model]
    if not same:
        (result.blocks if counted.verdict == "block" else result.approvals).append(counted)
        return
    if counted.verdict == "block" and same[0].verdict != "block":
        result.approvals.remove(same[0])
        result.blocks.append(counted)
        result.ineligible.append((same[0].review, f"{counted.model} also blocks in {counted.review.path.name}"))
        return
    result.ineligible.append((counted.review, f"{same[0].review.path.name} already counts for {counted.model}"))


def evaluate_gate(
    repo_root: Path,
    node: dict[str, Any],
    commit: str | None,
    *,
    today: date | None = None,
) -> GateResult:
    config, err = effective_config(repo_root, policy_ref(repo_root))
    policy = config["policy"]
    result = GateResult(
        node_id=node["id"],
        commit=full_sha(repo_root, commit),
        required=int(policy["reviewers_required"]),
        distinct_families=bool(policy["reviewers_distinct_families"]),
        config_error=err,
        config=config,
    )
    for review in list_reviews(repo_root, node["id"], acceptance_ids(node)):
        if review.ok and review.data.get("node_id") != node["id"]:
            review.errors.append(f"node_id is {review.data.get('node_id')!r}, not {node['id']!r}")
        if not review.ok:
            result.invalid.append(review)
            continue
        if not same_commit(repo_root, review.data["commit"], result.commit):
            result.stale.append(review)
            continue
        counted, why = _eligibility(config, node["id"], review, today)
        if counted is None:
            result.ineligible.append((review, why or "not eligible"))
        else:
            _count(result, counted)
    return result


def human_approval_completes(repo_root: Path, gate: GateResult) -> bool:
    """Whether one interactive human approval would satisfy the policy.

    True only when ``human`` is a rostered reviewer, nothing blocks, the
    config loads, and the human's family is the one approval still missing.
    """
    if gate.config_error or gate.commit is None or gate.blocks:
        return False
    config = gate.config
    if not is_rostered_reviewer(config, HUMAN):
        return False
    others = [a for a in gate.approvals if a.model != HUMAN]
    if gate.distinct_families:
        family = family_of(config, HUMAN) or HUMAN
        return len({a.family for a in others} | {family}) >= gate.required
    return len(others) + 1 >= gate.required


def write_human_approval(repo_root: Path, node: dict[str, Any], commit: str) -> Path:
    """File the interactive approval as ``REVIEW-human.md`` at ``commit``."""
    data = {
        "node_id": node["id"],
        "model": HUMAN,
        "family": HUMAN,
        "date": date.today().isoformat(),
        "verdict": "approve",
        "commit": commit,
        "acceptance": {aid: "pass" for aid in acceptance_ids(node)},
        "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
        "commands_rerun": [],
        "required_changes": [],
        "fresh_session": True,
        "authored_fix": False,
        # Whoever runs mark-implementation-reviewed is coordinating; say so.
        "is_coordinator": True,
    }
    path = review_path(repo_root, node["id"], HUMAN)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "Approved interactively with `specy-road mark-implementation-reviewed`.\n"
    path.write_text(render_front_matter(data, body), encoding="utf-8")
    return path


def commit_trailers(gate: GateResult) -> list[str]:
    """``Reviewed-by`` lines for the gate commit: the durable record of who approved."""
    return [
        f"Reviewed-by: {a.model} ({a.family}) approve {gate.commit}"
        + (f" [substitute for {a.substitution['slot']}]" if a.substitution else "")
        for a in gate.approvals
    ]


def gate_holds_at_head_or_exit(repo_root: Path, node: dict[str, Any]) -> None:
    """Refuse to finish when work landed after the approval (``finish-this-task``).

    ``implementation_review: approved`` is written once; without this check a
    commit made after approval would ship unreviewed. A fix restarts review.
    """
    gate = evaluate_gate(repo_root, node, resolve_target_or_exit(repo_root, node["id"], "HEAD").commit)
    if gate.passed:
        return
    print(
        f"error: the review approval for {node['id']} no longer holds at this commit "
        f"({gate.summary()}).",
        file=sys.stderr,
    )
    for problem in gate.problems():
        print(f"  - {problem}", file=sys.stderr)
    print(
        f"  Re-review, then run specy-road mark-implementation-reviewed again "
        f"(specy-road handoff status {node['id']}).",
        file=sys.stderr,
    )
    raise SystemExit(1)
