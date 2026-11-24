"""An operator's review decision, recorded by the coordinator, and the review gate's reading of it.

``specy-road review operator-decision <NODE_ID>`` records what the operator decided in plain words
("approved", "accept as-is"), with no prompt and no root-cause analysis: one closed ``kind:
decision`` entry in ``roadmap/decisions.yaml`` with ``decided_by: operator`` whose answer names the
commit under review, each counted block it settles (:func:`block_item`: reviewer, commit, findings,
correctness findings included), any approval shortfall (:func:`shortfall_text`), the operator's
words and the recorder's git identity; and ``work/reviews/<NODE_ID>/OPERATOR-<commit>.yaml`` holding
the session. The coordinator form (``--rule``) accepts with limits under an open ``kind:
standing-rule`` entry instead of the operator's words: it cites two root-cause analyses and two
alignment reviews by model, path and sha256 (:func:`evidence_problem`), names every counted finding
in exactly one ``--limit``, never applies to a trust-boundary leaf (:func:`sheet_tier` on the
integration branch), and records ``decided_by: coordinator``. Only the coordinator records either:
the command reads ``SPECY_ROAD_ORCHESTRATION_ROLE`` itself before anything else
(:func:`role_refusal`; unset is the manual coordinator, and any set value but exactly
``coordinator`` is refused).

The entry is the authority and the marker a cache, as ``review defer``'s are
(:mod:`specy_road.review_defer_rules`). The gate (:func:`apply_operator_decisions`) reads a decision
only through a marker, and honours it only while the entry is a closed decision of this node with
``decided_by`` whose answer names the marker's commit, and that commit is the one under review or
only this leaf's sheet or review bookkeeping changed since
(:func:`only_planning_or_review_bookkeeping_since`). It then settles only the blocks and the
shortfall the answer names; every other gate condition applies unchanged.

The bookkeeping carry (section below) decides whether a later commit leaves an approval in force.
Operator decisions call :func:`only_planning_or_review_bookkeeping_since` without ``records`` and
keep today's rule: this leaf's own sheet, its implementation summary and its review files, and never
a merge. Review records pass ``records=True`` (the gate's :func:`count_at_later_commit`). That carry
also accepts project-relative roadmap and planning paths, and a two-parent merge from the
integration branch whose non-bookkeeping diff is unchanged. It refuses when this leaf's acceptance,
touch zones or tier changed, when its sheet has no tier value, or when the graph or sheet cannot be
read.

The command handler (``cmd_operator_decision``) lives in
:mod:`specy_road.bundled_scripts.review_cli`: it loads the roadmap through the public loader,
and the gate imports this module, so the gate's imports never reach the loader.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import yaml

from specy_road.clock import utc_now_iso
from specy_road.orchestration.records.decisions import (DECISIONS_REL, STANDING_RULE, decisions_path, next_decision_id, read_decisions,
                                  standing_rule_active, write_decisions)
from specy_road.git_subprocess import git_code, git_stdout, git_text
from specy_road.nested_repos_land import checked_out_in, in_temp_worktree, move_ref
from specy_road.orchestration.guard.orchestration_role_env import ROLE_ENV
from specy_road.review_defer_rules import write_marker
from specy_road.git_changed_paths import diff_paths
from specy_road.review_files import REVIEWS_REL, ReviewFile, project_of, reviews_dir
from specy_road.review_policy_pin import committed_yaml, policy_source
from specy_road.review_target import full_sha
from specy_road.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.sibling_repos import Sibling, literal_pathspec, sibling_repos
from specy_road.text_sections import find_section

if TYPE_CHECKING:   # review_gate imports this module
    from specy_road.review_gate import GateResult

OPERATOR_PREFIX = "OPERATOR-"
OPERATOR, COORDINATOR = "operator", "coordinator"
PM_GUI = "pm-gui"   # the ``channel`` of a decision recorded from the PM GUI's status modal
APPROVE, ACCEPT_WITH_LIMITS = "approve", "accept-with-limits"
TRUST_BOUNDARY = "trust boundary"
_SHORTFALL = re.compile(r"approval shortfall: need (\d+), have (\d+)")
_RULE = re.compile(r"under rule (\S+) by coordinator")


def finding_texts(findings: Any) -> list[str]:
    """A record's findings as ``<category>: <text>`` strings, whitespace collapsed, in record
    order."""
    return [f"{cat}: {' '.join(str(t).split())}" for cat, texts in (findings or {}).items() for t in texts or []]


def block_item(reviewer: str, commit: str, findings: Any) -> str:
    """How a decision's answer names one counted block it settles (``commit`` full), and what the
    gate looks for."""
    return f"block by {reviewer} at {commit} with findings {json.dumps(finding_texts(findings), ensure_ascii=False)}"


def shortfall_text(need: int, have: int) -> str:
    """How a decision's answer names the approval shortfall it settles."""
    return f"approval shortfall: need {need}, have {have}"


def accepted_line(entry: dict[str, Any]) -> str:
    """What the gate summary, ``handoff status`` and ``review list`` print for an honoured
    decision."""
    if entry["decided_by"] == COORDINATOR:
        rule = _RULE.search(entry["answer"])[1]   # honoured() requires it
        return f"accepted with limits under rule {rule} by coordinator, decision {entry['id']}"
    return f"accepted by operator decision {entry['id']}"


def marker_path(repo_root: Path, node_id: str, commit: str) -> Path:
    """``OPERATOR-<full commit>.yaml`` in the hand-off directory (gitignored, like the reviews)."""
    return reviews_dir(repo_root, node_id) / f"{OPERATOR_PREFIX}{commit}.yaml"


def _markers(repo_root: Path, node_id: str) -> list[dict[str, Any]]:
    """The node's readable markers; an unreadable one, or one not shaped as the command writes it,
    settles nothing."""
    d = reviews_dir(repo_root, node_id)
    out = []
    for p in sorted(d.glob(f"{OPERATOR_PREFIX}*.yaml")) if d.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("node_id") == node_id and \
                isinstance(data.get("decision"), str) and isinstance(data.get("commit"), str):
            out.append(data)
    return out


def _ledgers(repo_root: Path, ref: str | None) -> list[dict[str, Any]]:
    """The working-tree ledger, then the one committed on the integration branch ``ref``: the
    coordinator commits the entry there, and ``mark-implementation-reviewed`` reads the gate on the
    leaf branch."""
    docs: list[Any] = []
    try:
        docs.append(read_decisions(decisions_path(repo_root)))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        pass   # an unreadable working-tree ledger honours nothing; the committed one may still
    if ref:
        docs.append(committed_yaml(repo_root, ref, DECISIONS_REL.as_posix()))
    return [d for d in docs if isinstance(d, dict)]


def honoured(repo_root: Path, node: dict[str, Any], marker: dict[str, Any], commit: str,
             ledgers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The entry ``marker`` names when the gate honours it at ``commit``, else ``None``: a closed
    decision of this node with ``decided_by`` whose answer names the marker's commit, which is
    ``commit`` or only bookkeeping since."""
    at = marker["commit"]
    if at != commit and not only_planning_or_review_bookkeeping_since(repo_root, node, at, commit):
        return None
    for doc in ledgers:
        e = next((e for e in doc.get("entries") or [] if isinstance(e, dict) and e.get("id") == marker["decision"]),
                 None)
        answer = str((e or {}).get("answer") or "")
        if e and e.get("status") == "closed" and e.get("kind") == "decision" and e.get("node") == node["id"] \
                and e.get("decided_by") in (OPERATOR, COORDINATOR) and f"for commit {at}," in answer \
                and (e["decided_by"] == OPERATOR or _RULE.search(answer)):
            return e
    return None


def apply_operator_decisions(repo_root: Path, result: GateResult, node: dict[str, Any], ref: str | None) -> None:
    """Settle what each honoured decision names (:func:`honoured`): a counted block whose reviewer,
    commit and findings it names moves to ``ineligible``, and the shortfall it names is settled
    while the current one is no larger, unless ``policy.signed_reviews`` is on. Without a marker, no
    ledger is read."""
    markers = _markers(repo_root, result.node_id) if result.commit else []
    ledgers = _ledgers(repo_root, ref) if markers else []
    for marker in markers:
        entry = honoured(repo_root, node, marker, result.commit, ledgers)
        if entry is None:
            continue
        line, answer = accepted_line(entry), entry["answer"]
        named = [b for b in result.blocks if block_item(b.model, review_commit(result, repo_root, b.review) or "",
                                                        b.review.data.get("findings")) in answer]
        for b in named:
            result.blocks.remove(b)
            result.ineligible.append((b.review, line))
        need = _SHORTFALL.search(answer)
        settles = bool(need and result.approval_count < result.required <= int(need[1])
                       and result.approval_count >= int(need[2]) and not result.config["policy"].get("signed_reviews"))
        result.shortfall_settled = result.shortfall_settled or settles
        if named or settles:
            result.accepted.append(line)


def sheet_tier(text: str | None) -> str | None:
    """A planning sheet's ``## Tier`` value: the first line's words before any ``:`` or ``(``,
    lower-cased; ``None`` when the section is missing or empty."""
    body = find_section(text or "", {"tier"}) or ""
    first = next((line for line in body.splitlines() if line.strip()), "")
    return re.split(r"[:(]", first, maxsplit=1)[0].strip(" *_`").lower() or None


def role_refusal() -> str | None:
    """Why the launch role may not record a decision. One rule: unset is the manual coordinator, and
    the only set value accepted is exactly ``coordinator``; any other, including empty, padded or
    differently cased, is refused."""
    raw = os.environ.get(ROLE_ENV)
    if raw is not None and raw != COORDINATOR:
        return (f"{ROLE_ENV} is {raw!r}: only the coordinator records an operator decision (unset is the manual "
                "coordinator); an executor, reviewer or root-cause analyst may not")
    return None


def recorder(root: Path) -> str | None:
    """``<user.name> <<user.email>>`` from git config, or ``None`` when either is unset."""
    name, email = (git_text(["config", f"user.{k}"], root) for k in ("name", "email"))
    return f"{name} <{email}>" if name and email else None


def _rule_problem(root: Path, rule_id: str) -> str | None:
    entries = read_decisions(decisions_path(root)).get("entries") or []
    e = next((e for e in entries if isinstance(e, dict) and e.get("id") == rule_id), None)
    if e is None:
        return f"--rule {rule_id}: no such entry in {DECISIONS_REL.as_posix()}"
    if e.get("kind") != STANDING_RULE:
        return (f"--rule {rule_id} is a {e.get('kind')} entry, not a standing-rule: only a standing operator rule "
                "(`decisions add --kind standing-rule`) authorises the coordinator form")
    return None if standing_rule_active(e) else f"--rule {rule_id} is closed or expired"


def _tier_problem(root: Path, node: dict[str, Any]) -> str | None:
    """The coordinator form needs a ``## Tier`` value other than trust boundary on the integration
    branch's sheet."""
    from specy_road.review_policy_pin import policy_source

    ref = policy_source(root)[0]
    rel = (node.get("planning_dir") or "").strip().strip("/")
    tier = sheet_tier(git_stdout(["show", f"{ref}:./{rel}"], root) if ref else None)
    if tier is None:
        return (f"{rel} has no ## Tier value on the integration branch ({ref or 'unreadable'}); the coordinator "
                "form needs one")
    if tier == TRUST_BOUNDARY:
        return f"{node['id']} is a trust-boundary leaf: only the operator's own words (--quote) may decide it"
    return None


def _cited(root: Path, node_id: str, flag: str, raw: str) -> tuple[dict[str, str] | None, str | None]:
    """``<model>=<path>`` as ``{model, path (project-relative), sha256}``, else ``(None, why)``."""
    model, sep, path = raw.partition("=")
    if not sep or not model.strip() or not path.strip():
        return None, f"{flag} {raw!r}: give <model>=<path>"
    p = Path(path.strip()).expanduser().resolve()
    if not p.is_file():
        return None, f"{flag} {raw!r}: {p} is not a file"
    # a linked worktree's hand-offs
    bases = (root.resolve(), project_of(reviews_dir(root, node_id)).resolve())
    rel = next((p.relative_to(b).as_posix() for b in bases if p.is_relative_to(b)), None)
    if rel is None:
        return None, f"{flag} {raw!r}: {p} is outside the project"
    return {"model": model.strip(), "path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}, None


def evidence_problem(config: dict[str, Any], parties: set[str], blockers: set[str],
                     rcas: list[dict[str, str]], alignments: list[dict[str, str]]) -> str | None:
    """Two RCAs by two roster families, neither a party to the leaf; two alignment reviews by two
    roster families, neither an RCA analyst nor a blocking reviewer."""
    from specy_road.orchestration_config import family_of

    analysts = {c["model"] for c in rcas}
    for flag, cited, barred, who in (
            ("--rca", rcas, parties, "a party to the leaf (it implemented or reviewed it)"),
            ("--alignment", alignments, analysts | blockers, "an RCA analyst or a blocking reviewer")):
        if len(cited) != 2:
            return f"{flag} is given {len(cited)} time(s); the coordinator form cites two"
        families = [family_of(config, c["model"]) for c in cited]
        if None in families:
            return f"{flag}: {cited[families.index(None)]['model']} is not on the roster"
        if families[0] == families[1]:
            return f"{flag}: both are of family {families[0]!r}; cite two roster families"
        if bad := [c["model"] for c in cited if c["model"] in barred]:
            return f"{flag}: {bad[0]} is {who}"
    return None


def _limit_problem(blocks: list[tuple[str, ReviewFile]], limits: list[str]) -> str | None:
    """Each counted finding's text must appear in exactly one ``--limit``."""
    norm = [" ".join(x.split()) for x in limits]
    for model, review in blocks:
        for text in finding_texts(review.data.get("findings")):
            n = sum(text.split(": ", 1)[1] in lim for lim in norm)
            if n != 1:
                return f"{model}'s finding {text!r} is named by {n} --limit(s); each counted finding needs exactly one"
    return None


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def blocks_to_settle(root: Path, gate: GateResult, sha: str) -> list[tuple[str, ReviewFile]]:
    """The counted blocks, and those the decision already recorded for ``sha`` settles: a new
    decision replaces its marker, so it names them again."""
    prior = next((m["decision"] for m in _markers(root, gate.node_id) if m["commit"] == sha), None)
    again = [(r.data["model"], r) for r, why in gate.ineligible
             if prior and why.startswith("accepted ") and why.endswith(f"decision {prior}")]
    return [(b.model, b.review) for b in gate.blocks] + again


def _coordinator_problem(root: Path, ns: argparse.Namespace, gate: GateResult, node: dict[str, Any],
                         blocks: list[tuple[str, ReviewFile]]) -> tuple[str | None, list[dict[str, str]]]:
    """``(why the coordinator form is refused, the cited evidence)``."""
    from specy_road.review_rca import loop_state, rca_parties

    why = _rule_problem(root, ns.rule) or _tier_problem(root, node) or (
        None if blocks else "no block counts at the commit under review; the coordinator form accepts blocks")
    rcas: list[dict[str, str]] = []
    aligns: list[dict[str, str]] = []
    for flag, given, into in (("--rca", ns.rca, rcas), ("--alignment", ns.alignment, aligns)):
        for raw in given:
            c, bad = _cited(root, node["id"], flag, raw)
            why = why or bad
            into.extend([c] if c else [])
    why = why or evidence_problem(gate.config, rca_parties(root, node["id"], loop_state(root, node["id"])),
                                  {m for m, _ in blocks}, rcas, aligns) or _limit_problem(blocks, ns.limit)
    return why, rcas + aligns


def _answer(ns: argparse.Namespace, sha: str, who: str, settles: list[str], cited: list[dict[str, str]]) -> str:
    head = (f"Accepted with limits under rule {ns.rule} by coordinator" if ns.rule
            else f"Accepted by operator decision ({ns.decision})")
    text = f"{head} for commit {sha}, recorded by {who}. Settles: {'; '.join(settles) or 'nothing named'}."
    if ns.rule:
        rcas, aligns = cited[:2], cited[2:]
        return text + (f" Limits: {json.dumps(ns.limit, ensure_ascii=False)}. RCA: "
                       + "; ".join(f"{c['model']} {c['path']} sha256:{c['sha256']}" for c in rcas)
                       + ". Alignment: " + "; ".join(f"{c['model']} {c['path']} sha256:{c['sha256']}" for c in aligns)
                       + ".")
    return text + f" Operator's words: {json.dumps(ns.quote.strip(), ensure_ascii=False)}"


def free_decision_id(root: Path, clone: Path) -> str:
    """The next ``D#`` used in neither ledger under ``root`` nor ``clone``'s
    ``decisions.local.yaml``. One rule for every new decision entry: ``root`` may be a temporary
    worktree of the integration branch, which has no local ledger, and the clone's local overlay
    would hide a shared entry with the same id (``load_merged``). A local id in another clone is not
    visible here; that clone's overlay can still hide the entry (a documented limit)."""
    entries = [*(read_decisions(decisions_path(root)).get("entries") or []),
               *(read_decisions(decisions_path(root, True)).get("entries") or []),
               *(read_decisions(decisions_path(clone, True)).get("entries") or [])]
    return next_decision_id({"entries": entries}, "D")


def _entry(root: Path, ns: argparse.Namespace, sha: str, answer: str, channel: str | None,
           clone: Path) -> dict[str, Any]:
    by = COORDINATOR if ns.rule else OPERATOR
    return {
        "id": free_decision_id(root, clone), "node": ns.node_id, "kind": "decision",
        "summary": f"{ns.decision} {ns.node_id} at {sha[:12]} ({by}"
                   + (f" under standing rule {ns.rule})" if ns.rule else " decision)"),
        "why_now": (f"standing rule {ns.rule} lets the coordinator accept with limits on this evidence" if ns.rule
                    else "the operator decided the review outcome in plain words"),
        "options": [{"label": ns.decision, "effect": "the gate settles the blocks and shortfall the answer names, "
                                                     "at the commit it names"},
                    {"label": "keep reviewing", "effect": "the blocks and shortfall still count"}],
        "recommendation": ns.decision, "recommendation_reason": f"decided by the {by}",
        "default_if_unanswered": "keep reviewing", "asked": date.today().isoformat(), "status": "closed",
        "answer": answer, "closed": utc_now_iso(), "decided_by": by, **({"channel": channel} if channel else {}),
    }


def settle_lines(root: Path, gate: GateResult, blocks: list[tuple[str, ReviewFile]]) -> list[str]:
    """What a decision settling ``blocks`` names, in its answer's order: one :func:`block_item` per
    block, then the :func:`shortfall_text` when ``gate`` is short of approvals."""
    settles = [block_item(m, review_commit(gate, root, r) or str(r.data["commit"]), r.data.get("findings"))
               for m, r in blocks]
    if gate.approval_count < gate.required:
        settles.append(shortfall_text(gate.required, gate.approval_count))
    return settles


def append_decision(root: Path, ns: argparse.Namespace, gate: GateResult, blocks: list[tuple[str, ReviewFile]],
                    who: str, cited: list[dict[str, str]] | None = None,
                    channel: str | None = None, clone: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Append the closed decision entry settling ``blocks`` and any shortfall of ``gate`` to the
    ledger under ``root`` (its id from :func:`free_decision_id`, ``clone`` the checkout whose local
    ledger is reserved too, ``root`` by default); ``(entry, what it settles)``. ``channel``
    (:data:`PM_GUI`) says where it was decided. No marker is written: the caller writes it
    (:func:`write_operator_marker`). Raises ``ValueError`` when ``root``'s copied schema refuses the
    entry."""
    sha = str(gate.commit)
    settles = settle_lines(root, gate, blocks)
    entry = _entry(root, ns, sha, _answer(ns, sha, who, settles, cited or []), channel, clone or root)
    path = decisions_path(root)
    doc = read_decisions(path)
    doc.setdefault("entries", []).append(entry)
    write_decisions(path, doc)
    return entry, settles


def write_operator_marker(repo_root: Path, entry: dict[str, Any], sha: str, session: str) -> Path:
    """Write ``OPERATOR-<sha>.yaml`` naming ``entry`` in ``repo_root``'s hand-off directory; its
    path."""
    marker = marker_path(repo_root, entry["node"], sha)
    write_marker(marker, {"node_id": entry["node"], "decision": entry["id"], "commit": sha,
                          "decided_by": entry["decided_by"], "session": session.strip()})
    return marker


def as_if_decided(gate: GateResult) -> GateResult:
    """A copy of ``gate`` with every counted block settled, and the shortfall unless
    ``policy.signed_reviews`` is on: what an operator decision now would leave. Its ``passed`` says
    whether the decision would pass the gate, and its ``problems()`` name what would still fail (a
    policy pin, an unmet ``strong_review`` item, ...)."""
    signed = bool((gate.config.get("policy") or {}).get("signed_reviews"))
    return dataclasses.replace(gate, blocks=[], shortfall_settled=gate.shortfall_settled or not signed)


def over_block_offer(root: Path, gate: GateResult) -> dict[str, Any]:
    """What the PM GUI may offer for a claimed leaf's gate: ``commit``, ``can_approve_over_block``
    (counted blocks stand and settling them would pass the gate, :func:`as_if_decided`) and
    ``settles`` (:func:`settle_lines` of :func:`blocks_to_settle`, as :func:`append_decision` would
    name them)."""
    return {"commit": gate.commit, "can_approve_over_block": bool(gate.blocks) and as_if_decided(gate).passed,
            "settles": settle_lines(root, gate, blocks_to_settle(root, gate, str(gate.commit)))}


# --- recording on the integration branch (shared with the PM GUI) ---


def integration(ref: str) -> tuple[str | None, str]:
    """``(remote or None, branch)`` of the ref the gate reads policy from."""
    if ref.startswith("refs/remotes/"):
        remote, ib = ref.removeprefix("refs/remotes/").split("/", 1)
        return remote, ib
    return None, ref.removeprefix("refs/heads/")


def integration_preflight(root: Path) -> tuple[str | None, str | None]:
    """``(the integration ref, why a decision may not be recorded on it)``: the role rule, git
    identity, the policy source, then with a remote a fetch of the integration branch, or with none
    a clean holder of it."""
    if why := role_refusal():
        return None, why
    if not recorder(root):
        return None, "git identity: set git user.name and user.email; the decision entry names who recorded it"
    ref, err = policy_source(root)
    if ref is None:
        return None, err or "no integration branch to record the decision on"
    remote, ib = integration(ref)
    if remote:   # the gate reads only the remote-tracking ref: read the policy at the fetched tip
        code, out = git_code(["fetch", remote, ib], root)
        if code != 0:
            return ref, f"git fetch {remote} {ib} failed: {out}"
    elif (holder := checked_out_in(root, ib)) is not None:
        status = git_text(["status", "--porcelain", "--untracked-files=no"], holder)
        if status is None or status:
            return ref, (f"{ib} is checked out in {holder} with uncommitted changes (or an unreadable "
                         "status); commit or stash them there first")
    return ref, None


def over_block_preflight(
    root: Path, node: dict[str, Any], gate: GateResult, branch: str
) -> tuple[GateResult, str | None, str | None]:
    """``(the gate at the integration tip, the integration ref, why approving over the block is
    withheld)``.

    Every check that can refuse runs here, before anything is written:
    :func:`integration_preflight`, then that settling the counted blocks would pass the gate
    (re-read at the fetched tip with a remote). The caller's own checks (the CLI's clean leaf
    checkout) come first."""
    from specy_road.review_gate import evaluate_gate

    ref, why = integration_preflight(root)
    if why or ref is None:
        return gate, ref, why
    if integration(ref)[0]:
        gate = evaluate_gate(root, node, gate.commit, branch=branch)
    after = as_if_decided(gate)
    if not after.passed:
        return gate, ref, "settling the block(s) would not pass the gate: " + "; ".join(after.problems())
    return gate, ref, None


@dataclasses.dataclass
class Landed:
    """A ledger commit on the integration branch: the entry written, the commit and where it went,
    or why not (``error``: nothing was recorded)."""
    where: str
    entry: dict[str, Any] | None = None
    commit: str | None = None
    error: str | None = None


def commit_ledger_entry(root: Path, ref: str, write: Callable[[Path], dict[str, Any]],
                        message: Callable[[dict[str, Any]], str]) -> Landed:
    """Run ``write(project root)`` in a detached temporary worktree of ``ref``'s tip, commit only
    the project's ledger there with ``message(entry)``, then push it fast-forward only, or with no
    remote move the local branch by compare-and-swap (a worktree holding it follows). No checkout of
    the repository is touched otherwise. A ``ValueError`` from ``write`` (a copied schema refusing
    the entry) is an error naming refresh-schemas."""
    remote, ib = integration(ref)
    out = Landed(where=f"{remote}/{ib}" if remote else f"local {ib}")
    tip, prefix = git_text(["rev-parse", ref], root) or "", project_prefix(root)
    rel = f"{prefix}{DECISIONS_REL.as_posix()}"

    def commit(tree: Path) -> str | None:
        try:
            entry = write(tree / prefix)
        except ValueError as e:   # a copied schema from before decided_by or channel
            return f"{e}; run `specy-road refresh-schemas`"
        git_code(["add", "--", rel], tree)
        code, text = git_code(["commit", "-q", "-m", message(entry), "--", rel], tree)
        if code != 0:
            return f"the decision commit failed: {text}"
        new = git_text(["rev-parse", "HEAD"], tree) or ""
        if remote:
            code, text = git_code(["push", remote, f"HEAD:refs/heads/{ib}"], tree)
            if code != 0:
                return f"git push {remote} HEAD:refs/heads/{ib} was refused: {text}"
        elif err := move_ref(root, f"refs/heads/{ib}", tip, new, checked_out_in(root, ib), "the decision commit"):
            return err
        out.entry, out.commit = entry, new
        return None

    out.error = in_temp_worktree(root, tip, commit)
    return out


@dataclasses.dataclass
class OverBlockRecord:
    """What :func:`record_over_block` did: the integration commit (``landed``), and once it landed
    the marker and the gate re-evaluated with it."""
    landed: Landed
    marker: Path | None = None
    gate: GateResult | None = None


def record_over_block(root: Path, node: dict[str, Any], gate: GateResult, ref: str, reason: str, branch: str, *,
                      session: str, channel: str | None = None) -> OverBlockRecord:
    """Commit the operator decision settling ``gate``'s blocks on the integration branch from a
    temporary worktree of the tip the gate read (:func:`commit_ledger_entry`), then write the marker
    here with ``session`` and re-evaluate the gate. Nothing is written here when the commit does not
    land."""
    from specy_road.review_gate import evaluate_gate

    sha = str(gate.commit)
    ns = argparse.Namespace(node_id=node["id"], decision=APPROVE, quote=reason, rule=None, limit=[], session=session)
    blocks, who = blocks_to_settle(root, gate, sha), str(recorder(root))
    landed = commit_ledger_entry(
        root, ref, lambda project: append_decision(project, ns, gate, blocks, who, channel=channel, clone=root)[0],
        lambda entry: f"roadmap: operator decision {entry['id']} approves {node['id']} over the block")
    if landed.error or landed.entry is None:
        return OverBlockRecord(landed)
    marker = write_operator_marker(root, landed.entry, sha, session)
    return OverBlockRecord(landed, marker, evaluate_gate(root, node, sha, branch=branch))


# --- The bookkeeping carry: whether a later commit leaves an approval in force ---

CARRY_NOTE = ("; approvals still count (only roadmap, planning or review bookkeeping changed since "
              "the reviewed commit)")

# Review policy a reviewer must see. Under roadmap/, but not bookkeeping.
_POLICY = ("roadmap/orchestration.yaml", "roadmap/git-workflow.yaml")


def _leaf_files(node: dict[str, Any]) -> tuple[str, str]:
    """This leaf's implementation summary and its review directory, project-relative."""
    return (f"work/implementation-summary-{node['id']}.md",
            f"{REVIEWS_REL.as_posix()}/{node['id']}")


def _is_leaf_file(rel: str, node: dict[str, Any]) -> bool:
    summary, handoffs = _leaf_files(node)
    return rel == summary or rel == handoffs or rel.startswith(f"{handoffs}/")


def _carries_path(rel: str | None, node: dict[str, Any]) -> bool:
    """A project-relative path the wider carry accepts. ``None`` is outside the project."""
    if not rel or rel in _POLICY:
        return False
    if rel in ("roadmap.md", "roadmap-context.md") or rel.startswith(("roadmap/", "planning/")):
        return True
    return _is_leaf_file(rel, node)


def _narrow_since(repo_root: Path, node: dict[str, Any], approved: str, commit: str | None) -> bool:
    """Today's predicate: this leaf's sheet, summary and review files, and never a merge.

    A missing ``commit``, a range that is not ancestral, any merge, or any other path is false.
    """
    if not commit:
        return False
    if git_code(["merge-base", "--is-ancestor", approved, commit], repo_root)[0] != 0:
        return False
    if git_text(["rev-list", "--merges", f"{approved}..{commit}"], repo_root):
        return False
    paths = diff_paths(repo_root, f"{approved}..{commit}")
    if paths is None:
        return False
    pd = (node.get("planning_dir") or "").strip().strip("/")
    if not pd:
        return False
    prefix = project_prefix(repo_root)
    for path in paths:
        rel = rebase_to_project(path, prefix)
        if rel is None or (rel != pd and not _is_leaf_file(rel, node)):
            return False
    return True


def _parents(repo_root: Path, sha: str) -> list[str] | None:
    """Parent shas of ``sha``, or ``None`` when git cannot answer."""
    text = git_text(["rev-list", "--parents", "-n", "1", sha], repo_root)
    if not text:
        return None
    parts = text.split()
    return parts[1:] if parts[0] == sha else None


def _on_integration(repo_root: Path, sha: str) -> bool:
    """Whether ``sha`` is on the integration history the review policy is read from."""
    ref, err = policy_source(repo_root)
    if err or not ref:
        return False
    return git_code(["merge-base", "--is-ancestor", sha, ref], repo_root)[0] == 0


def _diff_spec(path: str, prefix: str, node: dict[str, Any]) -> str | None:
    """A pathspec for one non-bookkeeping path, or ``None`` when the path carries."""
    rel = rebase_to_project(path, prefix)
    if _carries_path(rel, node):
        return None
    return f":(top,literal){path}" if rel is None else literal_pathspec(rel)


def _code_diff(repo_root: Path, left: str, right: str, node: dict[str, Any]) -> str | None:
    """The ``--full-index`` diff of non-bookkeeping paths, or ``None`` when git cannot answer.

    Bookkeeping paths are left out, including this leaf's summary and review files. Policy files
    stay in. Both sides of a comparison use this, so equal results are byte-identical.
    """
    paths = diff_paths(repo_root, left, right)
    if paths is None:
        return None
    prefix = project_prefix(repo_root)
    specs = sorted({spec for path in paths if (spec := _diff_spec(path, prefix, node))})
    if not specs:
        return ""
    return git_stdout(
        ["diff", "--full-index", "--no-color", "--no-ext-diff", left, right, "--", *specs],
        repo_root)


def _merge_keeps_code(repo_root: Path, sha: str, node: dict[str, Any]) -> bool:
    """A two-parent integration merge whose non-bookkeeping diff matches the first parent's."""
    parents = _parents(repo_root, sha)
    if not parents or len(parents) != 2:
        return False
    first, second = parents
    if not _on_integration(repo_root, second):
        return False
    base = git_text(["merge-base", first, second], repo_root)
    if not base:
        return False
    before = _code_diff(repo_root, base, first, node)
    after = _code_diff(repo_root, second, sha, node)
    return before is not None and before == after


def _ordinary_carries(repo_root: Path, parent: str, sha: str, node: dict[str, Any]) -> bool:
    paths = diff_paths(repo_root, parent, sha)
    if paths is None:
        return False
    prefix = project_prefix(repo_root)
    return all(_carries_path(rebase_to_project(path, prefix), node) for path in paths)


def _commits_carry(repo_root: Path, approved: str, commit: str, node: dict[str, Any]) -> bool:
    """Every first-parent commit in the range is bookkeeping, or a code-neutral integration merge.

    ``--first-parent`` does not walk commits the merge brought in; the diff comparison covers those.
    Any other merge shape, an unrelated merge, or a failed git query refuses the whole range.
    """
    listed = git_text(["rev-list", "--first-parent", f"{approved}..{commit}"], repo_root)
    if listed is None:
        return False
    for sha in listed.split():
        parents = _parents(repo_root, sha)
        if not parents or len(parents) > 2:
            return False
        if len(parents) == 2:
            if not _merge_keeps_code(repo_root, sha, node):
                return False
            continue
        if not _ordinary_carries(repo_root, parents[0], sha, node):
            return False
    return True


def _node_by_key(repo_root: Path, commit: str, node: dict[str, Any]) -> dict[str, Any] | None:
    """``node``'s ``node_key`` in the graph at ``commit``, across chunk moves."""
    key = node.get("node_key")
    if not isinstance(key, str) or not key:
        return None
    nodes = load_roadmap_nodes_at_ref(repo_root, commit)
    if not nodes:
        return None
    found = [item for item in nodes if item.get("node_key") == key]
    return found[0] if len(found) == 1 else None


def _sheet_text(repo_root: Path, commit: str, node: dict[str, Any]) -> str | None:
    """The sheet ``node`` names at ``commit``, or ``None`` when it cannot be read."""
    rel = str(node.get("planning_dir") or "").strip().strip("/")
    if not rel:
        return None
    return git_stdout(["show", f"{commit}:./{rel}"], repo_root)


def _contract_problem(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    if before.get("acceptance") != after.get("acceptance"):
        return "this leaf's acceptance changed"
    if before.get("touch_zones") != after.get("touch_zones"):
        return "this leaf's touch zones changed"
    return None


def _carry_tier_problem(old: str, new: str) -> str | None:
    """Why the sheet's tier refuses the carry. A sheet with no tier value is not eligible."""
    old_tier, new_tier = sheet_tier(old), sheet_tier(new)
    if old_tier != new_tier:
        return "this leaf's tier changed"
    if old_tier is None:
        return "this leaf's planning sheet has no tier value"
    return None


def _evidence_problem(repo_root: Path, approved: str, commit: str,
                      node: dict[str, Any]) -> str | None:
    """Why this leaf's own contract refuses a carry the paths would allow."""
    before, after = _node_by_key(repo_root, approved, node), _node_by_key(repo_root, commit, node)
    if before is None or after is None:
        return "this leaf's graph cannot be resolved"
    if problem := _contract_problem(before, after):
        return problem
    old, new = _sheet_text(repo_root, approved, before), _sheet_text(repo_root, commit, after)
    if old is None or new is None:
        return "this leaf's planning sheet cannot be resolved"
    return _carry_tier_problem(old, new)


def only_planning_or_review_bookkeeping_since(
    repo_root: Path, node: dict[str, Any], approved: str, commit: str | None, *,
    records: bool = False,
) -> bool | str:
    """Whether ``approved..commit`` keeps an approval.

    Without ``records`` (operator decisions), today's rule: a bool, false for a merge or any path
    other than this leaf's sheet, summary and review files. With ``records``, the wider carry: true
    when it holds, false when the paths or a merge do not qualify, or a reason string when this
    leaf's acceptance, zones, tier (including a sheet with no tier value), graph or sheet refuses
    it.
    """
    if not records:
        return _narrow_since(repo_root, node, approved, commit)
    if not commit or git_code(["merge-base", "--is-ancestor", approved, commit], repo_root)[0] != 0:
        return False
    if not _commits_carry(repo_root, approved, commit, node):
        return False
    return _evidence_problem(repo_root, approved, commit, node) or True


def _siblings(result: Any, repo_root: Path) -> list[Sibling]:
    """The sibling repositories, found once per gate evaluation (kept on ``result``)."""
    if getattr(result, "sibling_repos", None) is None:
        result.sibling_repos = sibling_repos(repo_root)
    return result.sibling_repos


def heads_problem(recorded: dict[str, str] | None, siblings: list[Sibling]) -> str | None:
    """Why sibling HEADs a record saw no longer hold, else ``None``; a record without them is not
    checked."""
    if recorded is None:
        return None
    current = {s.path: s.head for s in siblings if s.head}
    moved = sorted(p for p in set(recorded) | set(current) if recorded.get(p) != current.get(p))
    dirty = [s.path for s in siblings if s.dirty]
    if moved:
        return f"sibling repositories changed since the review ({', '.join(moved)})"
    return f"sibling repositories have uncommitted changes ({', '.join(dirty)})" if dirty else None


def review_commit(result: Any, repo_root: Path, review: ReviewFile) -> str | None:
    """The full sha of ``review``'s recorded commit (``None``: not a commit here), resolved once per
    gate evaluation and kept on ``result``; every comparison and display of a record's commit goes
    through it."""
    cache = getattr(result, "review_commits", None)
    if cache is None:
        cache = result.review_commits = {}
    if review.path not in cache:
        cache[review.path] = full_sha(repo_root, str(review.data["commit"]))
    return cache[review.path]


def _shown(result: Any, review: ReviewFile) -> str:
    """``review``'s commit as the policy line shows it: twelve characters of the resolved sha, else
    the record's."""
    sha = (getattr(result, "review_commits", None) or {}).get(review.path)
    return sha[:12] if sha else f"{review.data['commit']} (not a commit in this repository)"


def _refuse_carry(result: Any, review: ReviewFile, why: str) -> bool:
    d = review.data
    result.carry_refused = [*(getattr(result, "carry_refused", None) or []),
                            f"{d['model']}'s {d['verdict']} at {_shown(result, review)} is stale: "
                            f"{why}"]
    result.stale.append(review)
    return False


def count_at_later_commit(result: Any, repo_root: Path, node: dict[str, Any],
                          review: ReviewFile) -> bool:
    """False when ``review`` is stale at ``result.commit`` (appended to ``result.stale``).

    A record's ``sibling_heads`` is checked first, on every path: the current sibling map (which
    siblings, and each one's HEAD, all clean) must equal it exactly, whether or not the root commit
    moved; a record without the field is not checked. While a sibling repository exists
    (:mod:`specy_road.sibling_repos`) the bookkeeping carry never applies. Review records ask for
    the wider carry; a reason string from it is listed the same way. Each refusal's reason is listed
    in ``result.carry_refused`` for :func:`policy_line`.
    """
    siblings, sha = _siblings(result, repo_root), review_commit(result, repo_root, review)
    if sha is None:
        return _refuse_carry(result, review, "re-review the commit under review")
    if why := heads_problem(review.data.get("sibling_heads"), siblings):
        return _refuse_carry(result, review, why)
    if sha == result.commit:
        return True
    carried = only_planning_or_review_bookkeeping_since(repo_root, node, sha, result.commit,
                                                        records=True)
    if carried is True:
        if not siblings:
            result.bookkeeping_carry = True
            return True
        return _refuse_carry(result, review,
                             f"sibling repositories {', '.join(s.path for s in siblings)} are "
                             "present and nested_repos does not configure them, so changes there "
                             "cannot be seen")
    if isinstance(carried, str):
        return _refuse_carry(result, review, carried)
    result.stale.append(review)
    return False


def policy_line(gate: Any) -> str:
    """``gate.summary()`` with each counted approval as ``<model>@<commit>``, carried ones marked,
    and why an approval did not carry; the ``policy:`` line of ``handoff status`` and ``review
    record``."""
    line = gate.summary()
    if gate.approvals:
        head, sep, rest = line.partition(",")
        commits = getattr(gate, "review_commits", None) or {}
        listed = ", ".join(f"{a.model}@{_shown(gate, a.review)}" + (
            "" if commits.get(a.review.path) == gate.commit else " carried from an older commit")
            for a in gate.approvals)
        line = f"{head} ({listed}){sep}{rest}"
    return "; ".join([line, *(getattr(gate, "carry_refused", None) or [])])
