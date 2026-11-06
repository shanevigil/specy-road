"""A leaf's review policy is pinned at claim (M21.30, CR1).

Pickup appends ``Review-policy: sha256:<hex> at <commit>`` to its ``chore(rm-<codename>): register as in-progress``
commit: the digest of the review policy committed at the integration branch HEAD the claim is made on
(:func:`policy_digest`). The gate and ``finish-this-task`` compare it with the policy at the integration branch
(``review_policy_ref.policy_source``) and refuse a change made after the claim until a human accepts it with
``specy-road review accept-policy <ID>`` (``work/reviews/<ID>/POLICY-ACCEPTED.yaml``), or the leaf is re-claimed.

What is hashed: ``roster``, ``substitutions`` and ``policy`` of ``roadmap/orchestration.yaml`` and
``require_implementation_review_before_finish`` of ``roadmap/git-workflow.yaml``, as committed (a missing key is
null, no toolkit defaults, no local availability overlay). A registration commit without the trailer (a claim made
before this change) is judged as before. Pin and acceptance are honour-system, like READY files (maintainer
decision 2026-11-05); M22.5's steering guard is the broader protection.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road import review_lock
from specy_road.bundled_scripts.registration_pickup_commit import with_policy_trailer
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.git_subprocess import git_text, run
from specy_road.review_files import reviews_dir
from specy_road.review_policy_ref import policy_source
from specy_road.review_target import REGISTER_SUBJECT, ReviewTargetError, full_sha, resolve_target
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

ORCHESTRATION_REL = "roadmap/orchestration.yaml"
WORKFLOW_REL = "roadmap/git-workflow.yaml"
SWITCH = "require_implementation_review_before_finish"
ACCEPTANCE_NAME = "POLICY-ACCEPTED.yaml"
TRAILER_KEY = "Review-policy:"
_TRAILER = re.compile(r"^Review-policy: sha256:([0-9a-f]{64}) at ([0-9a-f]{40})$")
_SCHEMA = Path(__file__).resolve().parent / "schemas" / "policy-acceptance.schema.json"


class PolicyUnreadable(ValueError):
    """A policy file is present but does not parse, or a pin trailer is present but does not parse."""


def _yaml_at(root: Path, ref: str, rel: str) -> dict[str, Any]:
    r = run(["show", f"{ref}:./{rel}"], root)
    if not r.ok:
        return {}   # not committed there: every key is null
    try:
        data = yaml.safe_load(r.out)
    except yaml.YAMLError as e:
        raise PolicyUnreadable(f"{rel} at {ref} does not parse: {str(e).splitlines()[0]}") from e
    if data is not None and not isinstance(data, dict):
        raise PolicyUnreadable(f"{rel} at {ref} is not a mapping")
    return data or {}


def policy_parts(root: Path, ref: str) -> dict[str, Any]:
    orch, flow = _yaml_at(root, ref, ORCHESTRATION_REL), _yaml_at(root, ref, WORKFLOW_REL)
    return {"roster": orch.get("roster"), "substitutions": orch.get("substitutions"),
            "policy": orch.get("policy"), SWITCH: flow.get(SWITCH)}


def _encode(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def policy_digest(root: Path, ref: str) -> tuple[str, dict[str, Any]]:
    """``(sha256 hex, parts)`` of the review policy committed at ``ref``; raises :class:`PolicyUnreadable`."""
    parts = policy_parts(root, ref)
    return hashlib.sha256(_encode(parts).encode("utf-8")).hexdigest(), parts


def pinned_message(root: Path, message: str) -> str:
    """Pickup's registration message with the pin trailer for HEAD; exits 1 when a policy file does not parse.

    Nothing is committed in a repository with no commit yet, so there is nothing to pin.
    """
    head = full_sha(root, "HEAD")
    if not head:
        return message
    try:
        digest, _ = policy_digest(root, head)
    except PolicyUnreadable as e:
        print(f"error: {e}; fix it on the integration branch before claiming (nothing was registered)",
              file=sys.stderr)
        raise SystemExit(1) from e
    return with_policy_trailer(message, digest, head)


def pin_of(root: Path, codename: str, tip: str) -> tuple[str, str] | None:
    """``(sha256, commit)`` from the newest registration commit of ``codename`` reachable from ``tip``.

    ``None`` when there is no such commit or it has no trailer; :class:`PolicyUnreadable` when the trailer is
    present but does not parse.
    """
    subject = f"chore(rm-{codename}): {REGISTER_SUBJECT}"
    log = git_text(["log", "--format=%H %s", f"--grep={REGISTER_SUBJECT}", "--fixed-strings", tip], root) or ""
    sha = next((s for s, _, subj in (line.partition(" ") for line in log.splitlines())
                if subj.startswith(subject)), None)
    body = sha and git_text(["log", "-1", "--format=%B", sha], root) or ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith(TRAILER_KEY)]
    if not lines:
        return None
    m = _TRAILER.match(lines[-1])
    if len(lines) > 1 or not m or not full_sha(root, m.group(2)):
        raise PolicyUnreadable(f"the {TRAILER_KEY} trailer of {sha[:12]} does not parse")
    return m.group(1), m.group(2)


def change_lines(root: Path, pinned_commit: str, ref: str) -> list[str]:
    """One line per change from the policy at ``pinned_commit`` to the policy at ``ref``."""
    old, new = policy_parts(root, pinned_commit), policy_parts(root, ref)
    out: list[str] = []
    before = {str(e.get("id")): e for e in old["roster"] or [] if isinstance(e, dict)}
    after = {str(e.get("id")): e for e in new["roster"] or [] if isinstance(e, dict)}
    for rid in sorted(before.keys() | after.keys()):
        if rid not in after:
            out.append(f"roster {rid} removed: {_encode(before[rid])}")
        elif rid not in before:
            out.append(f"roster {rid} added: {_encode(after[rid])}")
        else:
            out += [f"roster {rid}.{p} {_encode(before[rid].get(p))} -> {_encode(after[rid].get(p))}"
                    for p in sorted(before[rid].keys() | after[rid].keys())
                    if _encode(before[rid].get(p)) != _encode(after[rid].get(p))]
    if _encode(old["substitutions"]) != _encode(new["substitutions"]):
        out.append("substitutions changed")
    po, pn = old["policy"] or {}, new["policy"] or {}
    out += [f"policy.{k} {_encode(po.get(k))} -> {_encode(pn.get(k))}"
            for k in sorted(po.keys() | pn.keys()) if _encode(po.get(k)) != _encode(pn.get(k))]
    if _encode(old[SWITCH]) != _encode(new[SWITCH]):
        out.append(f"{SWITCH} {_encode(old[SWITCH])} -> {_encode(new[SWITCH])}")
    if not out and _encode(old) != _encode(new):
        out.append("roster or policy changed in order or form (for example a missing key now empty)")
    return out


def acceptance_path(root: Path, node_id: str) -> Path:
    return reviews_dir(root, node_id) / ACCEPTANCE_NAME


def read_acceptance(root: Path, node_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """``(acceptance, None)``, ``(None, None)`` when there is none, or ``(None, why)`` when it is invalid."""
    path = acceptance_path(root, node_id)
    if not path.is_file():
        return None, None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        return None, f"{ACCEPTANCE_NAME} does not parse: {str(e).splitlines()[0]}"
    errors = sorted(Draft202012Validator(json.loads(_SCHEMA.read_text(encoding="utf-8"))).iter_errors(data),
                    key=str)
    if errors:
        return None, f"{ACCEPTANCE_NAME} is invalid: {errors[0].message}"
    if data["node_id"] != node_id:
        return None, f"{ACCEPTANCE_NAME} is for {data['node_id']}, not {node_id}"
    return data, None


def _pin_state(root: Path, node: dict[str, Any], commit: str) -> tuple[str, str, str, str] | None:
    """``(ref, pinned sha256, pinned commit, current sha256)`` when the policy changed since the claim, else
    ``None``; raises :class:`PolicyUnreadable`."""
    ref, _err = policy_source(root)   # an unreadable source is the gate's config error already
    pin = pin_of(root, node["codename"], commit) if ref and node.get("codename") else None
    if pin is None:
        return None
    current, _ = policy_digest(root, ref)
    return None if current == pin[0] else (ref, pin[0], pin[1], current)


def pin_problem(root: Path, node: dict[str, Any], commit: str) -> str | None:
    """Why the policy that judges ``node`` at ``commit`` is not the one pinned at its claim, else ``None``.

    One rule for the acceptance file: when ``POLICY-ACCEPTED.yaml`` exists and is invalid it is a problem, whatever
    the pin and the policy say, so an invalid file is never silently ignored; a valid one counts only for the
    pinned and current digests it names.
    """
    nid = node["id"]
    accepted, invalid = read_acceptance(root, nid)
    if invalid:
        return (f"{invalid}; an invalid acceptance never counts: delete work/reviews/{nid}/{ACCEPTANCE_NAME}, "
                f"and a human re-runs `specy-road review accept-policy {nid}` in a terminal if the policy changed")
    try:
        state = _pin_state(root, node, commit)
    except PolicyUnreadable as e:
        return f"review policy pin of {nid} cannot be checked: {e}"
    if state is None:
        return None
    ref, pinned, at, current = state
    if accepted and accepted["pinned_sha256"] == pinned and accepted["accepted_sha256"] == current:
        return None
    lines = "; ".join(change_lines(root, at, ref))
    return (f"review policy changed on {ref} since {nid} was claimed ({at[:12]}): {lines}; a human accepts "
            f"it with `specy-road review accept-policy {nid}` in a terminal, or re-claims the leaf")


def pin_holds_or_exit(root: Path, node: dict[str, Any]) -> None:
    """``finish-this-task``: exit 1 with the problem when the policy changed since the claim (checked at HEAD)."""
    if problem := pin_problem(root, node, "HEAD"):
        print(f"error: {problem}", file=sys.stderr)
        raise SystemExit(1)


def _user(root: Path) -> str:
    name, email = (git_text(["config", f"user.{k}"], root) for k in ("name", "email"))
    return f"{name} <{email}>" if name and email else name or email or getpass.getuser()


def cmd_accept_policy(ns: argparse.Namespace) -> int:
    """``review accept-policy <ID>``: a human, in a terminal, accepts the policy change since the claim."""
    if not sys.stdin.isatty():
        print("error: a human accepts a review policy change in a terminal; nothing was written", file=sys.stderr)
        return 1
    root = resolve_repo_root(ns)
    try:
        t = resolve_target(root, ns.node_id, ns.ref, nodes=load_roadmap(root)["nodes"])
        state = _pin_state(root, t.node, t.commit or "HEAD")
    except (ReviewTargetError, PolicyUnreadable) as e:
        print(f"error: {e}; nothing was written", file=sys.stderr)
        return 1
    if state is None:
        print(f"{ns.node_id}: the review policy is unchanged since the claim (or not pinned); nothing to accept")
        return 0
    ref, pinned, at, current = state
    print(f"review policy changed on {ref} since {ns.node_id} was claimed ({at[:12]}):")
    for line in change_lines(root, at, ref):
        print(f"  - {line}")
    if input(f"Type {ns.node_id} to accept this policy for {ns.node_id}: ").strip() != ns.node_id:
        print("not accepted; nothing was written", file=sys.stderr)
        return 1
    record = {"node_id": ns.node_id, "pinned_sha256": pinned, "accepted_sha256": current, "user": _user(root),
              "at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()}
    try:
        with review_lock.review_run_lock(reviews_dir(root, ns.node_id), wait=review_lock.FILING_WAIT):
            acceptance_path(root, ns.node_id).write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    except review_lock.ReviewRunBusy:
        print(f"error: {review_lock.filing_busy(ns.node_id)}", file=sys.stderr)
        return 1
    print(f"wrote {acceptance_path(root, ns.node_id)}")
    return 0


def add_parser(rsub: Any) -> None:
    sp = rsub.add_parser("accept-policy", help="Human-only: accept a review policy change made on the integration "
                                               "branch since the leaf was claimed")
    sp.add_argument("node_id")
    sp.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_accept_policy)
