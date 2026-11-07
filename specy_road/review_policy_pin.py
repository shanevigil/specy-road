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

A matching digest passes with no human: the rules that will judge the leaf are the ones it started under. A
different digest means the review rules changed after the work started, so the gate asks a person.
``review accept-policy <ID>`` records an acceptance for that leaf and those two digests only; ``--all-open`` asks
once for every open claim whose pin differs, prints each distinct set of changes once with the leaves it affects,
and writes each of those leaves the same per-leaf file. Re-claiming the leaf declines and pins the policy then in
force. The prompt and the gate refusal name this module, which is installed with the package.

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

from specy_road import review_lock, safe_write
from specy_road.bundled_scripts.registration_pickup_commit import with_policy_trailer
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.git_subprocess import git_text, run
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.review_files import check_handoff_read, project_of, reviews_dir
from specy_road.review_policy_ref import policy_source
from specy_road.review_target import REGISTER_SUBJECT, ReviewTargetError, full_sha, resolve_target
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

ORCHESTRATION_REL = "roadmap/orchestration.yaml"
WORKFLOW_REL = "roadmap/git-workflow.yaml"
SWITCH = "require_implementation_review_before_finish"
ACCEPTANCE_NAME = "POLICY-ACCEPTED.yaml"
#: Named by the accept-policy prompt and the gate refusal. This module ships in the wheel; ``docs/`` does not.
INSTALLED_REFERENCE = "specy_road.review_policy_pin"
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
    unreadable or invalid (the module's one rule; a directory or a symlink in its place, dangling or not, counts as
    present). The presence check is inside the boundary: an unreadable parent is invalid, never absent."""
    path = acceptance_path(root, node_id)
    try:
        with _unreadable_as(ACCEPTANCE_NAME):
            try:
                path.lstat()
            except FileNotFoundError:
                return None, None
            check_handoff_read(path)
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
    return _policy_refusal(nid, ref, at, lines)


def pin_holds_or_exit(root: Path, node: dict[str, Any]) -> None:
    """``finish-this-task``: exit 1 with the problem when the policy changed since the claim (checked at HEAD)."""
    if problem := pin_problem(root, node, "HEAD"):
        print(f"error: {problem}", file=sys.stderr)
        raise SystemExit(1)


def _user(root: Path) -> str:
    name, email = (git_text(["config", f"user.{k}"], root) for k in ("name", "email"))
    return f"{name} <{email}>" if name and email else name or email or getpass.getuser()


def _asked_because() -> str:
    """Plain language for the accept-policy prompt and the gate refusal: what changed, why a person is asked,
    what approving covers, and the installed-package reference. The raw change lines are printed below it."""
    return (
        "What changed is listed below, one line per change. "
        "The review rules changed after this work started, so a person is asked before the review gate can pass. "
        "Approving means each named leaf may be judged by the policy on the integration branch now. "
        "An acceptance covers only that leaf and the two digests it names, the one pinned when it was claimed "
        "and the one accepted now; a later policy change needs a new acceptance. "
        "Decline by re-claiming the leaf. "
        f"What is fingerprinted is in the installed package: {INSTALLED_REFERENCE}."
    )


def _policy_refusal(nid: str, ref: str, at: str, lines: list[str]) -> str:
    """The gate's refusal: the plain-language explanation, then each raw change line, then how to accept."""
    raw = "".join(f"\n      {line}" for line in lines)   # one line per change, below the explanation
    return (
        f"review policy changed on {ref} since {nid} was claimed ({at[:12]}):\n"
        f"    {_asked_because()}\n"
        f"{raw}\n"
        f"    a human accepts it with `specy-road review accept-policy {nid}` in a terminal, "
        "or re-claims the leaf"
    )


def _open_policy_changes(root: Path) -> list[dict[str, Any]]:
    """Open claims whose pinned review policy differs from the integration branch, in registry order."""
    nodes = load_roadmap(root)["nodes"]
    changes = []
    for entry in read_registry(registry_path(root)).get("entries") or []:
        if not isinstance(entry, dict) or not entry.get("node_id"):
            continue
        target = resolve_target(root, str(entry["node_id"]), None, nodes=nodes)
        state = _pin_state(root, target.node, target.commit or "HEAD")
        if state is None:
            continue
        ref, pinned, at, current, lines = state
        changes.append({"node_id": str(entry["node_id"]), "ref": ref, "pinned": pinned, "at": at,
                        "current": current, "lines": tuple(lines)})
    return changes


def _change_groups(changes: list[dict[str, Any]]) -> list[tuple[tuple[str, ...], list[dict[str, Any]]]]:
    """Each distinct set of change lines once, with the leaves it affects, earliest leaf id first."""
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for change in changes:
        grouped.setdefault(change["lines"], []).append(change)
    return sorted(grouped.items(), key=lambda item: min(row["node_id"] for row in item[1]))


def _write_acceptances(root: Path, rows: list[dict[str, Any]]) -> int:
    """One ``POLICY-ACCEPTED.yaml`` per leaf, under that leaf's review lock.

    Nothing is written when a lock is held, or when any acceptance path is a symlink.
    """
    ordered = sorted(rows, key=lambda row: row["node_id"])
    user = _user(root)
    at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    with contextlib.ExitStack() as stack:
        for row in ordered:
            try:
                stack.enter_context(review_lock.review_run_lock(
                    reviews_dir(root, row["node_id"]), wait=review_lock.FILING_WAIT))
            except review_lock.ReviewRunBusy:
                print(f"error: {review_lock.filing_busy(row['node_id'])}", file=sys.stderr)
                return 1
            except safe_write.SafeWriteError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
        prepared: list[tuple[Path, str]] = []
        for row in ordered:
            path = acceptance_path(root, row["node_id"])
            record = {"node_id": row["node_id"], "pinned_sha256": row["pinned"], "accepted_sha256": row["current"],
                      "user": user, "at": at}
            try:
                safe_write.check(project_of(path), path)
            except safe_write.SafeWriteError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            prepared.append((path, yaml.safe_dump(record, sort_keys=False)))
        for path, body in prepared:
            try:
                safe_write.write(project_of(path), path, body)
            except safe_write.SafeWriteError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            print(f"wrote {path}")
    return 0


def _accept_one(root: Path, node_id: str, ref: str | None) -> int:
    target = resolve_target(root, node_id, ref, nodes=load_roadmap(root)["nodes"])
    state = _pin_state(root, target.node, target.commit or "HEAD")
    if state is None:
        print(f"{node_id}: the review policy is unchanged since the claim (or not pinned); nothing to accept")
        return 0
    where, pinned, at, current, lines = state
    print(f"review policy changed on {where} since {node_id} was claimed ({at[:12]}):")
    print(_asked_because())
    for line in lines:
        print(f"  - {line}")
    if input(f"Type {node_id} to accept this policy for {node_id}: ").strip() != node_id:
        print("not accepted; nothing was written", file=sys.stderr)
        return 1
    return _write_acceptances(root, [{"node_id": node_id, "pinned": pinned, "current": current}])


def _print_groups(changes: list[dict[str, Any]]) -> None:
    print(f"Open claims whose pinned review policy differs from {changes[0]['ref']}:")
    print(_asked_because())
    for lines, leaves in _change_groups(changes):
        ordered = sorted(leaves, key=lambda row: row["node_id"])
        print(", ".join(row["node_id"] for row in ordered) + ":")
        for row in ordered:
            print(f"  {row['node_id']}: pinned {row['pinned']} accepted {row['current']}")
        for line in lines:
            print(f"  - {line}")


def _accept_all(root: Path) -> int:
    """``--all-open``: one confirmation, then one acceptance file per leaf that differs."""
    changes = _open_policy_changes(root)
    if not changes:
        print("no open claim has a review policy that differs from its pin; nothing to accept")
        return 0
    _print_groups(changes)
    token = " ".join(sorted(row["node_id"] for row in changes))
    if input(f"Type {token} to accept this policy for {token}: ").strip() != token:
        print("not accepted; nothing was written", file=sys.stderr)
        return 1
    return _write_acceptances(root, changes)


def _usage_error(ns: argparse.Namespace) -> str | None:
    if bool(ns.node_id) == bool(ns.all_open):
        return "pass one node id or --all-open, not both and not neither"
    if ns.all_open and ns.ref:
        return "--ref is for one node; --all-open uses each claim's registered branch"
    return None


def cmd_accept_policy(ns: argparse.Namespace) -> int:
    """``review accept-policy``: a human, in a terminal, accepts the policy change since the claim.

    One node id is that leaf. ``--all-open`` is every open claim whose pin differs: one confirmation, then
    one acceptance file per leaf.
    """
    if not sys.stdin.isatty():
        print("error: a human accepts a review policy change in a terminal; nothing was written", file=sys.stderr)
        return 1
    if reason := _usage_error(ns):
        print(f"error: {reason}; nothing was written", file=sys.stderr)
        return 1
    root = resolve_repo_root(ns)
    try:
        if ns.all_open:
            return _accept_all(root)
        return _accept_one(root, ns.node_id, ns.ref)
    except (ReviewTargetError, PolicyUnreadable) as e:
        print(f"error: {e}; nothing was written", file=sys.stderr)
        return 1


def add_parser(rsub: Any) -> None:
    sp = rsub.add_parser("accept-policy", help="Human-only: accept a review policy change made on the integration "
                                               "branch since the leaf was claimed")
    sp.add_argument("node_id", nargs="?", help="One leaf; omit it with --all-open")
    sp.add_argument("--all-open", action="store_true",
                    help="Every open claim whose pinned policy differs: print each distinct change once, "
                         "ask once, write one POLICY-ACCEPTED.yaml per leaf")
    sp.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_accept_policy)
