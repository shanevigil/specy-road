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

Unreadable input — one rule (:func:`_unreadable_as`). There are two input boundaries: the committed policy (every
git read, decode, YAML load, shape check, digest and change line, in :func:`policy_digest` and the gate's pin check)
and ``POLICY-ACCEPTED.yaml`` (:func:`read_acceptance`: file read, decode, YAML load, schema). Inside either, any
failure — ``OSError``, ``UnicodeDecodeError``, ``yaml.YAMLError``, ``ValueError`` (including YAML constructor errors
such as an impossible unquoted date), ``TypeError``/``AttributeError`` from a wrong shape, ``RecursionError`` from
deep nesting — becomes :class:`PolicyUnreadable` (the acceptance: the invalid-acceptance result). So the gate reports
a problem, and pickup, finish, ``mark-implementation-reviewed`` and ``review accept-policy`` refuse with a message,
never a traceback, and an unreadable input is never read as absent or empty. Limit: other exception types (for
example ``MemoryError``) are not caught, and the toolkit's other readers of the same files (``effective_config``)
keep their own rules.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import getpass
import hashlib
import json
import re
import sys
from collections.abc import Iterator
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
    """A policy input (committed policy, pin trailer, acceptance file) is present but cannot be read."""


#: Every failure a read, decode, parse or shape step can raise on bad input (module docstring).
UNREADABLE = (OSError, ValueError, TypeError, AttributeError, RecursionError, yaml.YAMLError)


@contextlib.contextmanager
def _unreadable_as(what: str) -> Iterator[None]:
    """The module's one rule: inside a boundary, any :data:`UNREADABLE` failure becomes :class:`PolicyUnreadable`
    naming ``what``; a :class:`PolicyUnreadable` raised inside passes through unchanged."""
    try:
        yield
    except PolicyUnreadable:
        raise
    except UNREADABLE as e:
        first = (str(e).splitlines() or [""])[0][:200]
        raise PolicyUnreadable(f"{what} cannot be read ({type(e).__name__}: {first})") from e


def _git_read(root: Path, args: list[str]) -> str | None:
    """git's output; ``None`` only when git ran and exited non-zero (a path or commit that is not there). Output git
    could not deliver or decode (``GitResult.failure``) raises :class:`PolicyUnreadable`: never read as absent."""
    r = run(args, root)
    if r.failure:
        raise PolicyUnreadable(f"`git {' '.join(args)}` output cannot be read ({r.failure}: {r.message})")
    return r.out if r.ok else None


def _yaml_at(root: Path, ref: str, rel: str) -> dict[str, Any]:
    text = _git_read(root, ["show", f"{ref}:./{rel}"])
    if text is None:
        return {}   # not committed there: every key is null
    with _unreadable_as(f"{rel} at {ref}"):
        data = yaml.safe_load(text)
    if data is not None and not isinstance(data, dict):
        raise PolicyUnreadable(f"{rel} at {ref} is not a mapping")
    return data or {}


def policy_parts(root: Path, ref: str) -> dict[str, Any]:
    """The hashed keys at ``ref``. One shape rule, checked here so every reader (claim, gate, finish, accept-policy)
    gets it: ``roster`` is null or a list of mappings and ``policy`` is null or a mapping; anything else raises
    :class:`PolicyUnreadable`. ``substitutions`` and the review switch are hashed and compared as written, whatever
    their shape (their change lines need no structure)."""
    orch, flow = _yaml_at(root, ref, ORCHESTRATION_REL), _yaml_at(root, ref, WORKFLOW_REL)
    roster, policy = orch.get("roster"), orch.get("policy")
    if not (roster is None or isinstance(roster, list) and all(isinstance(e, dict) for e in roster)):
        raise PolicyUnreadable(f"{ORCHESTRATION_REL} at {ref}: roster is not a list of mappings")
    if not (policy is None or isinstance(policy, dict)):
        raise PolicyUnreadable(f"{ORCHESTRATION_REL} at {ref}: policy is not a mapping")
    return {"roster": roster, "substitutions": orch.get("substitutions"), "policy": policy, SWITCH: flow.get(SWITCH)}


def _encode(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def policy_digest(root: Path, ref: str) -> tuple[str, dict[str, Any]]:
    """``(sha256 hex, parts)`` of the review policy committed at ``ref``; raises :class:`PolicyUnreadable`."""
    with _unreadable_as(f"the review policy at {ref}"):   # sort_keys on mixed-type keys, deep nesting
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
    log = _git_read(root, ["log", "--format=%H %s", f"--grep={REGISTER_SUBJECT}", "--fixed-strings", tip]) or ""
    sha = next((s for s, _, subj in (line.partition(" ") for line in log.splitlines())
                if subj.startswith(subject)), None)
    body = sha and _git_read(root, ["log", "-1", "--format=%B", sha]) or ""
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
    before = {str(e.get("id")): e for e in old["roster"] or []}
    after = {str(e.get("id")): e for e in new["roster"] or []}
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
    """``(acceptance, None)``, ``(None, None)`` when there is none, or ``(None, why)`` when it is present but
    unreadable or invalid (the module's one rule; a directory in its place counts as present)."""
    path = acceptance_path(root, node_id)
    if not path.exists():
        return None, None
    try:
        with _unreadable_as(ACCEPTANCE_NAME):
            data = yaml.safe_load(path.read_bytes().decode("utf-8"))
            schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
            if errors := sorted(Draft202012Validator(schema).iter_errors(data), key=str):
                raise PolicyUnreadable(f"{ACCEPTANCE_NAME} is invalid: {errors[0].message}")
            if data["node_id"] != node_id:
                raise PolicyUnreadable(f"{ACCEPTANCE_NAME} is for {data['node_id']}, not {node_id}")
    except PolicyUnreadable as e:
        return None, str(e)
    return data, None


def _pin_state(root: Path, node: dict[str, Any], commit: str) -> tuple[str, str, str, str, list[str]] | None:
    """``(ref, pinned sha256, pinned commit, current sha256, change lines)`` when the policy changed since the claim,
    else ``None``. The gate's committed-policy boundary: every read here is under the module's one rule."""
    ref, _err = policy_source(root)   # an unreadable source is the gate's config error already
    with _unreadable_as("the review policy pin"):
        pin = pin_of(root, node["codename"], commit) if ref and node.get("codename") else None
        if pin is None:
            return None
        current, _ = policy_digest(root, ref)
        return None if current == pin[0] else (ref, pin[0], pin[1], current, change_lines(root, pin[1], ref))


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
    ref, pinned, at, current, lines = state
    if accepted and accepted["pinned_sha256"] == pinned and accepted["accepted_sha256"] == current:
        return None
    return (f"review policy changed on {ref} since {nid} was claimed ({at[:12]}):"
            + "".join(f"\n      {line}" for line in lines)   # one line per change (A2)
            + f"\n    a human accepts it with `specy-road review accept-policy {nid}` in a terminal, "
            "or re-claims the leaf")


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
    ref, pinned, at, current, lines = state
    print(f"review policy changed on {ref} since {ns.node_id} was claimed ({at[:12]}):")
    for line in lines:
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
