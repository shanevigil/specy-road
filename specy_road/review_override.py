"""An operator's review decision, recorded by the coordinator, and the review gate's reading of it (M22.51).

``specy-road review operator-decision <NODE_ID>`` records what the operator decided in plain words ("approved",
"accept as-is"), with no prompt and no root-cause analysis: one closed ``kind: decision`` entry in
``roadmap/decisions.yaml`` with ``decided_by: operator`` whose answer names the commit under review, each counted
block it settles (:func:`block_item`: reviewer, commit, findings, correctness findings included), any approval
shortfall (:func:`shortfall_text`), the operator's words and the recorder's git identity; and
``work/reviews/<NODE_ID>/OPERATOR-<commit>.yaml`` holding the session. The coordinator form (``--rule``) accepts
with limits under an open ``kind: standing-rule`` entry instead of the operator's words: it cites two root-cause
analyses and two alignment reviews by model, path and sha256 (:func:`evidence_problem`), names every counted
finding in exactly one ``--limit``, never applies to a trust-boundary leaf (:func:`sheet_tier` on the integration
branch), and records ``decided_by: coordinator``. Only the coordinator records either: the command reads
``SPECY_ROAD_ORCHESTRATION_ROLE`` itself before anything else (:func:`role_refusal`; unset is the manual
coordinator, and any set value but exactly ``coordinator`` is refused).

The entry is the authority and the marker a cache, as ``review defer``'s are (:mod:`specy_road.review_deferral`).
The gate (:func:`apply_operator_decisions`) reads a decision only through a marker, and honours it only while the
entry is a closed decision of this node with ``decided_by`` whose answer names the marker's commit, and that commit
is the one under review or only this leaf's sheet or review bookkeeping changed since
(:func:`~specy_road.review_bookkeeping.only_planning_or_review_bookkeeping_since`). It then settles only the
blocks and the shortfall the answer names; every other gate condition applies unchanged.
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
from specy_road.decisions import (DECISIONS_REL, STANDING_RULE, decisions_path, next_decision_id, read_decisions,
                                  standing_rule_active, write_decisions)
from specy_road.git_subprocess import git_code, git_stdout, git_text
from specy_road.nested_repos_land import checked_out_in, in_temp_worktree, move_ref
from specy_road.orchestration_role_env import ROLE_ENV
from specy_road.review_bookkeeping import only_planning_or_review_bookkeeping_since, review_commit
from specy_road.review_deferral import write_marker
from specy_road.review_files import ReviewFile, project_of, reviews_dir
from specy_road.review_policy_ref import committed_yaml, policy_source
from specy_road.runtime_paths import add_repo_root_arg, project_prefix, resolve_repo_root
from specy_road.text_sections import find_section

if TYPE_CHECKING:   # review_gate imports this module
    from specy_road.review_gate import GateResult

OPERATOR_PREFIX = "OPERATOR-"
OPERATOR, COORDINATOR = "operator", "coordinator"
PM_GUI = "pm-gui"   # the ``channel`` of a decision recorded from the PM GUI's status modal (M17.15)
APPROVE, ACCEPT_WITH_LIMITS = "approve", "accept-with-limits"
TRUST_BOUNDARY = "trust boundary"
_SHORTFALL = re.compile(r"approval shortfall: need (\d+), have (\d+)")
_RULE = re.compile(r"under rule (\S+) by coordinator")


def finding_texts(findings: Any) -> list[str]:
    """A record's findings as ``<category>: <text>`` strings, whitespace collapsed, in record order."""
    return [f"{cat}: {' '.join(str(t).split())}" for cat, texts in (findings or {}).items() for t in texts or []]


def block_item(reviewer: str, commit: str, findings: Any) -> str:
    """How a decision's answer names one counted block it settles (``commit`` full), and what the gate looks for."""
    return f"block by {reviewer} at {commit} with findings {json.dumps(finding_texts(findings), ensure_ascii=False)}"


def shortfall_text(need: int, have: int) -> str:
    """How a decision's answer names the approval shortfall it settles."""
    return f"approval shortfall: need {need}, have {have}"


def accepted_line(entry: dict[str, Any]) -> str:
    """What the gate summary, ``handoff status`` and ``review list`` print for an honoured decision."""
    if entry["decided_by"] == COORDINATOR:
        rule = _RULE.search(entry["answer"])[1]   # honoured() requires it
        return f"accepted with limits under rule {rule} by coordinator, decision {entry['id']}"
    return f"accepted by operator decision {entry['id']}"


def marker_path(repo_root: Path, node_id: str, commit: str) -> Path:
    """``OPERATOR-<full commit>.yaml`` in the hand-off directory (gitignored, like the reviews)."""
    return reviews_dir(repo_root, node_id) / f"{OPERATOR_PREFIX}{commit}.yaml"


def _markers(repo_root: Path, node_id: str) -> list[dict[str, Any]]:
    """The node's readable markers; an unreadable one, or one not shaped as the command writes it, settles nothing."""
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
    """The working-tree ledger, then the one committed on the integration branch ``ref``: the coordinator commits
    the entry there, and ``mark-implementation-reviewed`` reads the gate on the leaf branch."""
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
    """The entry ``marker`` names when the gate honours it at ``commit``, else ``None``: a closed decision of this
    node with ``decided_by`` whose answer names the marker's commit, which is ``commit`` or only bookkeeping since."""
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
    """Settle what each honoured decision names (:func:`honoured`): a counted block whose reviewer, commit and
    findings it names moves to ``ineligible``, and the shortfall it names is settled while the current one is no
    larger, unless ``policy.signed_reviews`` is on. Without a marker, no ledger is read."""
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
    """A planning sheet's ``## Tier`` value: the first line's words before any ``:`` or ``(``, lower-cased;
    ``None`` when the section is missing or empty."""
    body = find_section(text or "", {"tier"}) or ""
    first = next((line for line in body.splitlines() if line.strip()), "")
    return re.split(r"[:(]", first, maxsplit=1)[0].strip(" *_`").lower() or None


def role_refusal() -> str | None:
    """Why the launch role may not record a decision. One rule: unset is the manual coordinator, and the only set
    value accepted is exactly ``coordinator``; any other, including empty, padded or differently cased, is refused."""
    raw = os.environ.get(ROLE_ENV)
    if raw is not None and raw != COORDINATOR:
        return (f"{ROLE_ENV} is {raw!r}: only the coordinator records an operator decision (unset is the manual "
                "coordinator); an executor, reviewer or root-cause analyst may not")
    return None


def _form_problem(ns: argparse.Namespace) -> str | None:
    """Why the flags are neither the operator form (``--quote``) nor the coordinator form (``--rule``)."""
    if ns.rule is None:
        if ns.rca or ns.alignment or ns.limit:
            return "--rca, --alignment and --limit belong to the coordinator form (--rule)"
        if not (ns.quote or "").strip():
            return "--quote is empty: give the operator's words as they said them, or the coordinator form --rule"
    elif ns.quote is not None:
        return "--quote and --rule are two forms; give one"
    elif ns.decision != ACCEPT_WITH_LIMITS:
        return f"the coordinator form (--rule) records only --decision {ACCEPT_WITH_LIMITS}"
    if not (ns.session or "").strip():
        return "--session is empty: name the session the operator decided in"
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
    """The coordinator form needs a ``## Tier`` value other than trust boundary on the integration branch's sheet."""
    from specy_road.review_policy_ref import policy_source

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
    bases = (root.resolve(), project_of(reviews_dir(root, node_id)).resolve())   # a linked worktree's hand-offs
    rel = next((p.relative_to(b).as_posix() for b in bases if p.is_relative_to(b)), None)
    if rel is None:
        return None, f"{flag} {raw!r}: {p} is outside the project"
    return {"model": model.strip(), "path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}, None


def evidence_problem(config: dict[str, Any], parties: set[str], blockers: set[str],
                     rcas: list[dict[str, str]], alignments: list[dict[str, str]]) -> str | None:
    """Two RCAs by two roster families, neither a party to the leaf; two alignment reviews by two roster families,
    neither an RCA analyst nor a blocking reviewer."""
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
    """The counted blocks, and those the decision already recorded for ``sha`` settles: a new decision replaces
    its marker, so it names them again."""
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
    """The next ``D#`` used in neither ledger under ``root`` nor ``clone``'s ``decisions.local.yaml``. One rule for
    every new decision entry: ``root`` may be a temporary worktree of the integration branch, which has no local
    ledger, and the clone's local overlay would hide a shared entry with the same id (``load_merged``). A local id
    in another clone is not visible here; that clone's overlay can still hide the entry (a documented limit)."""
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
    """What a decision settling ``blocks`` names, in its answer's order: one :func:`block_item` per block, then the
    :func:`shortfall_text` when ``gate`` is short of approvals."""
    settles = [block_item(m, review_commit(gate, root, r) or str(r.data["commit"]), r.data.get("findings"))
               for m, r in blocks]
    if gate.approval_count < gate.required:
        settles.append(shortfall_text(gate.required, gate.approval_count))
    return settles


def append_decision(root: Path, ns: argparse.Namespace, gate: GateResult, blocks: list[tuple[str, ReviewFile]],
                    who: str, cited: list[dict[str, str]] | None = None,
                    channel: str | None = None, clone: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Append the closed decision entry settling ``blocks`` and any shortfall of ``gate`` to the ledger under
    ``root`` (its id from :func:`free_decision_id`, ``clone`` the checkout whose local ledger is reserved too,
    ``root`` by default); ``(entry, what it settles)``. ``channel`` (:data:`PM_GUI`) says where it
    was decided. No marker is written: the caller writes it (:func:`write_operator_marker`). Raises
    ``ValueError`` when ``root``'s copied schema refuses the entry."""
    sha = str(gate.commit)
    settles = settle_lines(root, gate, blocks)
    entry = _entry(root, ns, sha, _answer(ns, sha, who, settles, cited or []), channel, clone or root)
    path = decisions_path(root)
    doc = read_decisions(path)
    doc.setdefault("entries", []).append(entry)
    write_decisions(path, doc)
    return entry, settles


def write_operator_marker(repo_root: Path, entry: dict[str, Any], sha: str, session: str) -> Path:
    """Write ``OPERATOR-<sha>.yaml`` naming ``entry`` in ``repo_root``'s hand-off directory; its path."""
    marker = marker_path(repo_root, entry["node"], sha)
    write_marker(marker, {"node_id": entry["node"], "decision": entry["id"], "commit": sha,
                          "decided_by": entry["decided_by"], "session": session.strip()})
    return marker


def as_if_decided(gate: GateResult) -> GateResult:
    """A copy of ``gate`` with every counted block settled, and the shortfall unless ``policy.signed_reviews`` is
    on: what an operator decision now would leave. Its ``passed`` says whether the decision would pass the gate,
    and its ``problems()`` name what would still fail (a policy pin, an unmet ``strong_review`` item, ...)."""
    signed = bool((gate.config.get("policy") or {}).get("signed_reviews"))
    return dataclasses.replace(gate, blocks=[], shortfall_settled=gate.shortfall_settled or not signed)


def over_block_offer(root: Path, gate: GateResult) -> dict[str, Any]:
    """What the PM GUI may offer for a claimed leaf's gate: ``commit``, ``can_approve_over_block`` (counted blocks
    stand and settling them would pass the gate, :func:`as_if_decided`) and ``settles`` (:func:`settle_lines` of
    :func:`blocks_to_settle`, as :func:`append_decision` would name them)."""
    return {"commit": gate.commit, "can_approve_over_block": bool(gate.blocks) and as_if_decided(gate).passed,
            "settles": settle_lines(root, gate, blocks_to_settle(root, gate, str(gate.commit)))}


# --- recording on the integration branch (M22.67; shared with the PM GUI, M17.15) ---


def integration(ref: str) -> tuple[str | None, str]:
    """``(remote or None, branch)`` of the ref the gate reads policy from."""
    if ref.startswith("refs/remotes/"):
        remote, ib = ref.removeprefix("refs/remotes/").split("/", 1)
        return remote, ib
    return None, ref.removeprefix("refs/heads/")


def integration_preflight(root: Path) -> tuple[str | None, str | None]:
    """``(the integration ref, why a decision may not be recorded on it)``: the role rule, git identity, the
    policy source, then with a remote a fetch of the integration branch, or with none a clean holder of it."""
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
    """``(the gate at the integration tip, the integration ref, why approving over the block is withheld)``.

    Every check that can refuse runs here, before anything is written: :func:`integration_preflight`, then that
    settling the counted blocks would pass the gate (re-read at the fetched tip with a remote). The caller's own
    checks (the CLI's clean leaf checkout) come first."""
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
    """A ledger commit on the integration branch: the entry written, the commit and where it went, or why not
    (``error``: nothing was recorded)."""
    where: str
    entry: dict[str, Any] | None = None
    commit: str | None = None
    error: str | None = None


def commit_ledger_entry(root: Path, ref: str, write: Callable[[Path], dict[str, Any]],
                        message: Callable[[dict[str, Any]], str]) -> Landed:
    """Run ``write(project root)`` in a detached temporary worktree of ``ref``'s tip, commit only the project's
    ledger there with ``message(entry)``, then push it fast-forward only, or with no remote move the local branch
    by compare-and-swap (a worktree holding it follows). No checkout of the repository is touched otherwise.
    A ``ValueError`` from ``write`` (a copied schema refusing the entry) is an error naming refresh-schemas."""
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
    """What :func:`record_over_block` did: the integration commit (``landed``), and once it landed the marker and
    the gate re-evaluated with it."""
    landed: Landed
    marker: Path | None = None
    gate: GateResult | None = None


def record_over_block(root: Path, node: dict[str, Any], gate: GateResult, ref: str, reason: str, branch: str, *,
                      session: str, channel: str | None = None) -> OverBlockRecord:
    """Commit the operator decision settling ``gate``'s blocks on the integration branch from a temporary worktree
    of the tip the gate read (:func:`commit_ledger_entry`), then write the marker here with ``session`` and
    re-evaluate the gate. Nothing is written here when the commit does not land."""
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


def cmd_operator_decision(ns: argparse.Namespace) -> int:
    if why := role_refusal():   # before anything is read or written
        return _fail(why)
    root = resolve_repo_root(ns)
    if why := _form_problem(ns):
        return _fail(why)
    who = recorder(root)
    if not who:
        return _fail("set git user.name and user.email: the decision entry names who recorded it")
    from specy_road.roadmap_load import load_roadmap
    from specy_road.review_gate import evaluate_gate
    from specy_road.review_target import ReviewTargetError, resolve_target

    nodes = load_roadmap(root)["nodes"]
    if any(n.get("parent_id") == ns.node_id for n in nodes):
        return _fail(f"{ns.node_id} has children: an operator decision is for one leaf and one commit")
    try:
        t = resolve_target(root, ns.node_id, nodes=nodes)
    except ReviewTargetError as e:
        return _fail(f"the commit under review does not resolve: {e}")
    gate = evaluate_gate(root, t.node, t.commit, branch=(t.entry or {}).get("branch"))
    sha = gate.commit
    blocks = blocks_to_settle(root, gate, sha)
    cited: list[dict[str, str]] = []
    if ns.rule:
        why, cited = _coordinator_problem(root, ns, gate, t.node, blocks)
        if why:
            return _fail(why)
    try:
        entry, settles = append_decision(root, ns, gate, blocks, who, cited)
    except ValueError as e:   # a copied schema from before decided_by
        return _fail(f"{e}; nothing was written. Run `specy-road refresh-schemas` and try again")
    marker = write_operator_marker(root, entry, sha, ns.session)
    print(f"[ok] decision {entry['id']} closed (decided_by: {entry['decided_by']}) for {ns.node_id} at {sha[:12]}: "
          f"{'; '.join(settles) or 'nothing to settle'}; wrote {marker}")
    print(f"  Commit {DECISIONS_REL.as_posix()} on the integration branch, then `specy-road handoff status "
          f"{ns.node_id}`. A later commit on the leaf beyond its sheet or review bookkeeping ends the decision.")
    return 0


def add_parser(rsub: Any) -> None:
    sp = rsub.add_parser("operator-decision", help="Coordinator: record the operator's review decision for the "
                                                   "commit under review, or accept with limits under a standing rule")
    sp.add_argument("node_id")
    sp.add_argument("--decision", required=True, choices=[APPROVE, ACCEPT_WITH_LIMITS])
    sp.add_argument("--quote", help="The operator's words, as they said them (operator form)")
    sp.add_argument("--session", required=True, help="The session the operator decided in; kept in the marker")
    sp.add_argument("--rule", metavar="ID", help="Coordinator form: an open standing-rule entry in "
                                                 "roadmap/decisions.yaml; only --decision accept-with-limits")
    sp.add_argument("--rca", action="append", default=[], metavar="MODEL=PATH",
                    help="Coordinator form: a root-cause analysis; give two, of two roster families")
    sp.add_argument("--alignment", action="append", default=[], metavar="MODEL=PATH",
                    help="Coordinator form: an alignment review; give two, of two roster families")
    sp.add_argument("--limit", action="append", default=[], metavar="TEXT",
                    help="Coordinator form: an accepted limit; each counted finding is named in exactly one")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_operator_decision)
