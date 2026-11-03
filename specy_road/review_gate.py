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
* that model's roster ``may_process`` includes the node's sensitivity, as
  ``orchestrate plan`` and ``prompt`` require;
* it attests a fresh session when policy requires one.

Policy is read from ``roadmap/orchestration.yaml`` **as committed on the
integration branch** (its remote-tracking ref when present), and the gate is on
when either that branch or the working tree turns it on: a feature branch
cannot lower its own bar. Which branch that is comes from the committed
``git-workflow.yaml`` on the remote's default branch (at HEAD only in a repo
with no remote), and a branch that cannot be found fails closed (:func:`policy_source`).

The gate passes when no counted record blocks and the counted approvals reach
``reviewers_required`` — counted by distinct family when
``reviewers_distinct_families`` is set. With ``policy.integrity_gate`` on, each
test-integrity finding the node did not declare in ``planned_test_changes`` on
the integration branch is a problem too (:mod:`specy_road.integrity_gate`).
An approval naming ``delta_from`` (a delta review) must also meet :func:`delta_problem`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.finish_implementation_check import in_zones
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_code
from specy_road.git_workflow_config import require_implementation_review_before_finish
from specy_road.integrity import compare_integrity
from specy_road.integrity_gate import integrity_gate_problems
from specy_road.orchestrate_plan import entry_may_process, may_handle, node_sensitivity
from specy_road.orchestration_config import (effective_config, family_of, is_rostered_reviewer, roster_entry,
                                            substitute_for)
from specy_road.review_gate_ready import (  # noqa: F401 — public names re-exported
    TRIAL_MERGE_BOOKKEEPING, TrialMerge, is_trial_merge_bookkeeping, trial_merge, trial_merge_or_exit,
    write_human_approval)
from specy_road.review_signing import (  # noqa: F401 — SigningError re-exported
    SigningError, notes_problem, verify)
from specy_road.review_bookkeeping import CARRY_NOTE, count_at_later_commit, only_planning_or_review_bookkeeping_since
from specy_road.review_files import (HUMAN, PACKET_NAME, ReviewFile, executor_blocked_gate_problems, latest_ready,
                                     list_review_history, list_reviews, review_semantic_errors, reviews_dir,
                                     verifier_gate_problems)
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.review_policy_ref import committed_yaml as _committed_yaml, policy_source
from specy_road.review_resumed_delta import fresh_session_problem
from specy_road.review_target import full_sha, resolve_target_or_exit, same_commit
from specy_road.runtime_paths import project_prefix, rebase_to_project
#: A fix round is reviewed from a delta packet only when it changes at most this many files.
DELTA_MAX_FILES = 3
_DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")
_TEST_DIRS = frozenset({"tests", "test", "__tests__"})
#: ``review-packet --full`` stamps ``PACKET.md``; while that is the commit's packet, no delta counts.
FULL_MARK = "- **Delta review:** off (`--full`): every reviewer reads this full packet"


def review_required(repo_root: Path) -> bool:
    """Whether the review gate is on — in the working tree **or** on the integration branch.

    Fails closed: when the integration branch cannot be found, its switch
    cannot be read, so the gate counts as on.
    """
    if require_implementation_review_before_finish(repo_root):
        return True
    ref, err = policy_source(repo_root)
    if err:
        return True
    if ref is None:
        return False
    flag = _committed_yaml(repo_root, ref, "roadmap/git-workflow.yaml")
    return bool(flag.get("require_implementation_review_before_finish"))


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
    verifier_problems: list[str] = field(default_factory=list)
    config_error: str | None = None
    bookkeeping_carry: bool = False; config: dict[str, Any] = field(default_factory=dict)

    @property
    def approval_count(self) -> int:
        return len({a.family for a in self.approvals}) if self.distinct_families else len(self.approvals)

    @property
    def passed(self) -> bool:
        return (self.config_error is None and self.commit is not None and not self.blocks
                and not self.verifier_problems and self.approval_count >= self.required)

    def summary(self) -> str:
        unit = "distinct-family approvals" if self.distinct_families else "approvals"
        state = "met" if self.passed else "not met"
        return f"{self.approval_count}/{self.required} {unit}, {len(self.blocks)} block(s): {state}" + (CARRY_NOTE if self.bookkeeping_carry else "")

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
        out.extend(self.verifier_problems)
        return out


def _signature_problem(config: dict[str, Any], model: str, review: ReviewFile) -> str | None:
    """Why a record's signature keeps it from counting, else ``None``.

    A present signature is always verified (tampering is caught even with the
    policy off); a missing one matters only when ``signed_reviews`` is on.
    """
    sig = review.data.get("signature")
    entry = roster_entry(config, model) or {}
    pub = entry.get("public_key")
    if sig:
        if not pub:
            return f"signed, but the roster entry for {model!r} has no public_key to verify against"
        ok, reason = verify(review.data, sig, pub, model)
        return None if ok else f"signature does not verify for {model!r}: {reason}"
    if config["policy"].get("signed_reviews"):
        return "policy requires signed reviews (signature missing); file it with `review record --sign-key`"
    return None


def rerun_problem(policy: dict[str, Any], data: dict[str, Any]) -> str | None:
    """Why an approval without a re-run does not count under ``reviewer_reruns_required``.

    The interactive human approval is exempt: it records no commands, and a
    human-only roster must still be able to close the gate.
    """
    if (policy.get("reviewer_reruns_required") and data.get("verdict") == "approve"
            and data.get("model") != HUMAN and not data.get("commands_rerun")):
        return "approved without re-running a command (policy.reviewer_reruns_required)"
    return None


def _eligibility(config: dict[str, Any], node: dict[str, Any], review: ReviewFile,
                 today: date | None) -> tuple[CountedReview | None, str | None]:
    model, node_id = review.data["model"], node["id"]
    sub = None
    if not is_rostered_reviewer(config, model):
        sub = substitute_for(config, node_id, model, today)
        if sub is None:
            return None, (
                f"model {model!r} is not a rostered reviewer and no active substitution "
                f"covers {node_id} (roadmap/orchestration.yaml)"
            )
    entry = roster_entry(config, model) or {}
    if not may_handle(entry, node_sensitivity(node)):
        return None, (f"{node_id} is {node_sensitivity(node)!r} and {model!r} may process only "
                      f"{entry_may_process(entry)} (roster may_process)")
    if why := fresh_session_problem(config["policy"], review.data):
        return None, why
    why = (rerun_problem(config["policy"], review.data) or notes_problem(review.data, review.body)
           or _signature_problem(config, model, review))
    if why:
        return None, why
    family = family_of(config, model)
    if not family:
        return None, f"no family for {model!r}: add it to the roster"
    return CountedReview(review, family, sub), None


def is_doc_or_test(path: str) -> bool:
    """A documentation file (by suffix) or a test file (under a tests directory, or named as one)."""
    p = PurePosixPath(path)
    return (p.suffix.lower() in _DOC_SUFFIXES or bool(_TEST_DIRS & set(p.parts[:-1]))
            or p.name.startswith("test_") and p.suffix == ".py" or p.stem.endswith("_test")
            or ".test." in p.name or ".spec." in p.name)


def delta_problem(repo_root: Path, node: dict[str, Any], approved: str, commit: str | None,
                  policy: dict[str, Any]) -> str | None:
    """Why ``approved..commit`` needs a full review, else ``None``: the delta review rule."""
    if not policy.get("delta_review", True):
        return "policy.delta_review is off"
    if not commit or same_commit(repo_root, approved, commit) or \
            git_code(["merge-base", "--is-ancestor", approved, commit], repo_root)[0] != 0:
        return f"{approved} is not an earlier commit of {commit}"
    packet = reviews_dir(repo_root, node["id"]) / PACKET_NAME   # commit-bound: a new commit lifts it
    if FULL_MARK in (text := packet.read_text(encoding="utf-8") if packet.is_file() else "") and \
            f"**Commit under review:** `{full_sha(repo_root, commit)}`" in text:
        return f"`review-packet --full` forces a full review of {commit}"
    paths = diff_paths(repo_root, f"{approved}..{commit}")
    if paths is None or len(paths) > DELTA_MAX_FILES:
        return f"the delta touches {'?' if paths is None else len(paths)} files (at most {DELTA_MAX_FILES})"
    entry = next((e for e in read_registry(registry_path(repo_root)).get("entries") or []
                  if e.get("node_id") == node["id"]), None) or {}
    zones = [z.strip().strip("/") for z in entry.get("touch_zones") or node.get("touch_zones") or []
             if isinstance(z, str) and z.strip()]
    prefix, summary = project_prefix(repo_root), f"work/implementation-summary-{node['id']}.md"
    for p in paths:
        if not is_doc_or_test(p):
            return f"{p} is not a documentation or test file"
        if (rebase_to_project(p, prefix) or p) != summary and not in_zones(zones, p, prefix):
            return f"{p} is outside the touch zones"
    findings = compare_integrity(repo_root, approved, commit)
    return f"the delta's integrity report has findings ({findings[0].line()})" if findings else None


def _delta_why(repo_root: Path, node: dict[str, Any], priors: list[ReviewFile], review: ReviewFile,
               commit: str | None, policy: dict[str, Any]) -> str | None:
    """Why ``review``'s ``delta_from`` approval of ``commit`` does not count given the model's counting ``priors``."""
    model, base = review.data["model"], review.data["delta_from"]
    if not any(same_commit(repo_root, k.data["commit"], base) for k in priors):
        return f"a delta review from {base}, which {model} did not approve; a full review is needed"
    why = delta_problem(repo_root, node, base, commit, policy)
    return f"a delta review from {base}, but {why}; a full review is needed" if why else None


def prior_approvals(repo_root: Path, config: dict[str, Any], node: dict[str, Any], model: str,
                    commit: str | None, today: date | None = None) -> list[ReviewFile]:
    """``model``'s counting approvals of other commits, in filing order. Its latest record on a commit is its
    verdict there; an approval naming ``delta_from`` counts only while that basis counts and the delta qualifies."""
    latest: dict[str, ReviewFile] = {}   # full sha -> the model's latest record on it, in filing order
    for r in list_review_history(repo_root, node["id"]) + list_reviews(repo_root, node["id"]):
        if r.ok and r.data.get("node_id") == node["id"] and r.data["model"] == model and \
                not same_commit(repo_root, r.data["commit"], commit):
            sha = full_sha(repo_root, r.data["commit"]) or r.data["commit"]
            latest = {k: v for k, v in latest.items() if k != sha} | {sha: r}   # moves it last
    counts: dict[str, bool] = {}
    ids = acceptance_ids(node)   # history is loaded without them

    def counting(sha: str) -> bool:   # False is set first, so a delta_from cycle never counts
        if sha not in counts:
            counts[sha], r = False, latest.get(sha)
            base = full_sha(repo_root, r.data.get("delta_from")) if r else None
            counts[sha] = bool(r and r.data["verdict"] == "approve" and not review_semantic_errors(r.data, ids)
                               and _eligibility(config, node, r, today)[0] is not None
                               and (not r.data.get("delta_from") or base in latest and counting(base)
                                    and not delta_problem(repo_root, node, base, r.data["commit"], config["policy"])))
        return counts[sha]
    return [r for sha, r in latest.items() if counting(sha)]


def delta_basis(repo_root: Path, node: dict[str, Any], model: str, commit: str | None) -> tuple[ReviewFile | None, str]:
    """``(model's latest counting approval of an earlier commit, "")`` when the change since may be reviewed
    from a delta packet, else ``(None, why)``; an unreadable policy fails closed."""
    ref, err = policy_source(repo_root)
    config, err = (None, err) if err else effective_config(repo_root, ref)
    prior = [] if err else prior_approvals(repo_root, config, node, model, commit)
    why = err or ("no earlier approval" if not prior else
                  delta_problem(repo_root, node, prior[-1].data["commit"], commit, config["policy"]))
    return (None, why) if why else (prior[-1], "")


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


def evaluate_gate(repo_root: Path, node: dict[str, Any], commit: str | None, *,
                  today: date | None = None, branch: str | None = None) -> GateResult:
    ref, ref_err = policy_source(repo_root)
    config, err = effective_config(repo_root, ref)
    err = ref_err or err
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
        if not count_at_later_commit(result, repo_root, node, review):
            continue
        counted, why = _eligibility(config, node, review, today)
        if counted is not None and counted.verdict == "approve" and review.data.get("delta_from"):
            priors = prior_approvals(repo_root, config, node, review.data["model"], result.commit, today)
            why = _delta_why(repo_root, node, priors, review, result.commit, policy)
            counted = None if why else counted
        if counted is None:
            result.ineligible.append((review, why or "not eligible"))
        else:
            _count(result, counted)
    ready = latest_ready(repo_root, node["id"], branch, acceptance_ids(node))
    result.verifier_problems = verifier_gate_problems(ready, result.approvals)
    if ready is not None and same_commit(repo_root, ready.data["commit"], result.commit):
        result.verifier_problems += executor_blocked_gate_problems(ready)
    result.verifier_problems += integrity_gate_problems(repo_root, policy, node["id"], result.commit, ref)
    return result


def human_approval_completes(repo_root: Path, gate: GateResult, node: dict[str, Any],
                             sign_key: Path | None = None) -> bool:
    """Whether one interactive human approval would satisfy the policy.

    True only when ``human`` is a rostered reviewer that may process the node's
    sensitivity, nothing blocks, the config loads, the human's family is the one
    approval still missing, and — under ``signed_reviews`` — a key was given and
    the roster has its public key.
    """
    if gate.config_error or gate.commit is None or gate.blocks or gate.verifier_problems:
        return False
    config = gate.config
    if not is_rostered_reviewer(config, HUMAN) or not may_handle(roster_entry(config, HUMAN), node_sensitivity(node)):
        return False
    has_key = bool((roster_entry(config, HUMAN) or {}).get("public_key"))
    if config["policy"].get("signed_reviews") and (sign_key is None or not has_key):
        return False
    if sign_key is not None and not has_key:
        return False   # a signature the roster cannot verify would be rejected by the gate
    others = [a for a in gate.approvals if a.model != HUMAN]
    if gate.distinct_families:
        family = family_of(config, HUMAN) or HUMAN
        return len({a.family for a in others} | {family}) >= gate.required
    return len(others) + 1 >= gate.required


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
    target = resolve_target_or_exit(repo_root, node["id"], "HEAD")
    gate = evaluate_gate(repo_root, node, target.commit, branch=(target.entry or {}).get("branch"))
    if gate.passed:
        return
    print(f"error: the review approval for {node['id']} no longer holds at this commit ({gate.summary()}).",
          file=sys.stderr)
    for problem in gate.problems():
        print(f"  - {problem}", file=sys.stderr)
    print(f"  Re-review, then run specy-road mark-implementation-reviewed again "
          f"(specy-road handoff status {node['id']}).", file=sys.stderr)
    raise SystemExit(1)
