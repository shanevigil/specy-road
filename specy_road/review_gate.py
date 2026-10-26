"""Decide whether a node's implementation has the reviews its policy requires.

The rule ``mark-implementation-reviewed`` enforces, and ``handoff status``
reports. A review record counts only when all of these hold:

* it validates (schema plus :func:`review_files.review_semantic_errors`,
  including a result for every acceptance id in the brief);
* its ``commit`` is the commit under review — any later commit makes it stale,
  which is how "a substantive fix restarts both reviews" needs no extra state;
* its model is rostered with the ``reviewer`` role, or is the substitute in an
  active substitution covering this node;
* it attests a fresh session when policy requires one.

The gate passes when no counted record blocks and the counted approvals reach
``reviewers_required`` — counted by distinct family when
``reviewers_distinct_families`` is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.orchestration_config import (
    effective_config,
    family_of,
    is_rostered_reviewer,
    substitute_for,
)
from specy_road.review_files import ReviewFile, list_reviews
from specy_road.review_target import same_commit


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
    family = family_of(config, model) or review.data.get("family")
    if not family:
        return None, f"no family for {model!r}: add it to the roster"
    return CountedReview(review, family, sub), None


def evaluate_gate(
    repo_root: Path,
    node: dict[str, Any],
    commit: str | None,
    *,
    today: date | None = None,
) -> GateResult:
    config, err = effective_config(repo_root)
    policy = config["policy"]
    result = GateResult(
        node_id=node["id"],
        commit=commit,
        required=int(policy["reviewers_required"]),
        distinct_families=bool(policy["reviewers_distinct_families"]),
        config_error=err,
    )
    for review in list_reviews(repo_root, node["id"], acceptance_ids(node)):
        if not review.ok:
            result.invalid.append(review)
            continue
        if not same_commit(review.data["commit"], commit):
            result.stale.append(review)
            continue
        counted, why = _eligibility(config, node["id"], review, today)
        if counted is None:
            result.ineligible.append((review, why or "not eligible"))
        elif counted.verdict == "block":
            result.blocks.append(counted)
        else:
            result.approvals.append(counted)
    return result
