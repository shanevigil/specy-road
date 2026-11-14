"""Where the review policy is read from, and a leaf's review policy pinned at claim.

The policy is read from the integration branch :func:`policy_source` names (section below); a
feature branch cannot lower its own bar. :func:`gate_config_mismatch` reports when
``orchestration.yaml`` asks for reviewers that finish does not enforce.

Pickup appends ``Review-policy: sha256:<hex> at <commit>`` to its ``chore(rm-<codename>): register
as in-progress`` commit: the digest of the review policy committed at the integration branch HEAD
the claim is made on (:func:`policy_digest`). The gate and ``finish-this-task`` compare it with the
policy at the integration branch (:func:`policy_source`) and refuse a change made after the claim
until a human accepts it with ``specy-road review accept-policy <ID>``
(``work/reviews/<ID>/POLICY-ACCEPTED.yaml``), or the leaf is re-claimed.

What is hashed: ``roster``, ``substitutions`` and ``policy`` of ``roadmap/orchestration.yaml`` and
``require_implementation_review_before_finish`` of ``roadmap/git-workflow.yaml``, as committed (a
missing key is null, no toolkit defaults, no local availability overlay). A registration commit
without the trailer (a claim made before this change) is judged as before. Pin and acceptance are
honour-system, like READY files (maintainer decision 2026-11-05); the steering guard is the broader
protection.

A matching digest passes with no human: the rules that will judge the leaf are the ones it started
under. A different digest means the review rules changed after the work started, so the gate asks a
person. ``review accept-policy <ID>`` records an acceptance for that leaf and those two digests
only; ``--all-open`` asks once for every open claim whose pin differs, prints each distinct set of
changes once with the leaves it affects, and writes each of those leaves the same per-leaf file.
Re-claiming the leaf declines and pins the policy then in force. The prompt and the gate refusal
name this module, which is installed with the package. The ``review accept-policy`` command itself
lives in :mod:`specy_road.bundled_scripts.review_cli`: it loads the roadmap through the public
loader, and the gate imports this module, so the gate's imports never reach the loader.

Unreadable input — one rule (:func:`_unreadable_as`). There are two input boundaries: the committed
policy (every git read, decode, YAML load, shape check, digest and change line, in
:func:`policy_digest` and the gate's pin check) and ``POLICY-ACCEPTED.yaml``
(:func:`read_acceptance`: file read, decode, YAML load, schema). Inside either, any failure —
``OSError``, ``UnicodeDecodeError``, ``yaml.YAMLError``, ``ValueError`` (including YAML constructor
errors such as an impossible unquoted date), ``TypeError``/``AttributeError`` from a wrong shape,
``RecursionError`` from deep nesting — becomes :class:`PolicyUnreadable` (the acceptance: the
invalid-acceptance result). So the gate reports a problem, and pickup, finish,
``mark-implementation-reviewed`` and ``review accept-policy`` refuse with a message, never a
traceback, and an unreadable input is never read as absent or empty. Limit: other exception types
(for example ``MemoryError``) are not caught, and the toolkit's other readers of the same files
(``effective_config``) keep their own rules.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.git_subprocess import git_stdout, git_text, run
from specy_road.git_workflow_config import require_implementation_review_before_finish
from specy_road.orchestration_config import DEFAULT_POLICY, load_orchestration_config
from specy_road.review_files import check_handoff_read, reviews_dir
from specy_road.review_target import REGISTER_SUBJECT, full_sha

ORCHESTRATION_REL = "roadmap/orchestration.yaml"
WORKFLOW_REL = "roadmap/git-workflow.yaml"
SWITCH = "require_implementation_review_before_finish"
ACCEPTANCE_NAME = "POLICY-ACCEPTED.yaml"
#: Named by the accept-policy prompt and the gate refusal. This module ships in the wheel; ``docs/``
#: does not.
INSTALLED_REFERENCE = "specy_road.review_policy_pin"
TRAILER_KEY = "Review-policy:"
_TRAILER = re.compile(r"^Review-policy: sha256:([0-9a-f]{64}) at ([0-9a-f]{40})$")
_SCHEMA = Path(__file__).resolve().parent / "schemas" / "policy-acceptance.schema.json"


class PolicyUnreadable(ValueError):
    """A policy input (committed policy, pin trailer, acceptance file) is present but cannot be
    read."""


#: Every failure a read, decode, parse or shape step can raise on bad input (module docstring).
UNREADABLE = (OSError, ValueError, TypeError, AttributeError, RecursionError, yaml.YAMLError)


# --- Which git ref the review policy and roster are read from (:func:`policy_source`) ---
#
# In a repo with remotes, the integration branch *name* comes from
# ``roadmap/git-workflow.yaml`` as committed on the remote's default branch
# (``refs/remotes/<remote>/HEAD``) — a ref no feature commit moves. That ref must
# exist (``git clone`` sets it; ``git remote set-head <remote> <name>`` restores
# it, while ``--auto`` fails when the remote's HEAD is unborn), and its copy must
# name the same remote as HEAD's copy, so a feature commit cannot switch to a
# secondary remote. Out of scope: a remote whose default branch the feature author
# can push to. Without a remote (a local-only repo) HEAD's copy names the branch. Then:
#
# * **self-consistency** — the branch the name points at must itself name that
#   branch as the integration branch in its own committed ``git-workflow.yaml``;
# * **remote preference** — with remotes, policy is read from
#   ``refs/remotes/<remote>/<name>`` and nothing else, so retargeting needs push
#   rights to a branch the remote protects; without, the local branch is all
#   there is. A remote name that is not configured in a repo that has remotes is
#   an error, not a local repo.
#
# Any failure is an error the caller fails closed on, never a fall back. The
# missing-ref error may name a branch in ``git remote set-head``. That sentence is
# for the developer (one ``git show`` per remote-tracking ref, and only on that
# path); the gate does not read policy from it.


def committed_yaml(repo_root: Path, rev: str, rel: str) -> dict[str, Any]:
    # ./ = relative to the project root, not the git root
    text = git_stdout(["show", f"{rev}:./{rel}"], repo_root)
    try:
        data = yaml.safe_load(text) if text else None
    except UNREADABLE:   # an unreadable file is never a traceback
        return {}
    return data if isinstance(data, dict) else {}


def _hint_branch(repo_root: Path, remote: str) -> str | None:
    """The one remote branch to name in the set-head hint, or ``None`` to name none.

    Counts a ref only when its tip is not HEAD's commit and its committed workflow
    is a readable mapping whose ``integration_branch`` equals that ref's own name.
    An empty or missing value does not count as ``main``. A malformed or non-mapping
    file, or a failed ref listing, is not a match and raises nothing.
    """
    head = git_text(["rev-parse", "HEAD"], repo_root)
    listed = git_stdout(
        ["for-each-ref", "--format=%(objectname) %(refname)", f"refs/remotes/{remote}/"],
        repo_root,
    )
    if not head or listed is None:
        return None
    prefix = f"refs/remotes/{remote}/"
    found: list[str] = []
    for line in listed.splitlines():
        sha, sep, ref = line.partition(" ")
        if not sep or sha == head or not ref.startswith(prefix):
            continue
        branch = ref[len(prefix):]
        if not branch or branch == "HEAD":
            continue
        named = committed_yaml(repo_root, ref, WORKFLOW_REL).get("integration_branch")
        if isinstance(named, str) and named == branch:
            found.append(branch)
    return found[0] if len(found) == 1 else None


def _missing_anchor_message(repo_root: Path, remote: str, anchor: str) -> str:
    """Fail-closed text: a working ``set-head`` command, and why ``--auto`` does not."""
    branch = _hint_branch(repo_root, remote)
    name = branch if branch else "<name>"
    which = "" if branch else " with the remote's real default branch"
    return (
        f"{anchor} (the remote's default branch) is missing, and with a remote configured the "
        f"integration branch is named only there; run `git remote set-head {remote} {name}`{which} "
        f"(`git remote set-head {remote} --auto` fails when the remote's HEAD is unborn)"
    )


def integration_name(repo_root: Path,
                     remotes: list[str]) -> tuple[tuple[str, str, str] | None, str | None]:
    """``((remote, branch, where), error)``: the integration branch to read policy from, and whose
    config named it.

    With remotes, the remote's default branch names it, so a feature branch cannot nominate itself.
    A missing ``refs/remotes/<remote>/HEAD`` stays an error. Any branch in that message is a hint,
    not a result.
    """
    head = committed_yaml(repo_root, "HEAD", WORKFLOW_REL)
    remote = str(head.get("remote") or "origin")
    if not remotes:
        branch = str(head.get("integration_branch") or "main")
        return (remote, branch, "(roadmap/git-workflow.yaml at HEAD)"), None
    if remote not in remotes:
        return None, (
            f"remote {remote!r} (roadmap/git-workflow.yaml at HEAD) is not configured, but this "
            f"repo has remote(s) {', '.join(remotes)}; review policy is read only from a "
            "configured remote's tracking ref, so fix remote on the integration branch"
        )
    anchor = f"refs/remotes/{remote}/HEAD"
    if not git_text(["rev-parse", "--verify", "--quiet", f"{anchor}^{{commit}}"], repo_root):
        return None, _missing_anchor_message(repo_root, remote, anchor)
    pinned = committed_yaml(repo_root, anchor, WORKFLOW_REL)
    named = str(pinned.get("remote") or "origin")
    if named != remote:
        return None, (
            f"roadmap/git-workflow.yaml at HEAD names remote {remote!r}, but at {anchor} it names "
            f"{named!r}; review policy is read only through the remote the default branch names, "
            "so fix remote on this branch"
        )
    branch = str(pinned.get("integration_branch") or "main")
    return (remote, branch, f"(roadmap/git-workflow.yaml at {anchor})"), None


def trusted_integration_ref(
    repo_root: Path, remotes: list[str], remote: str, ib: str, where: str
) -> tuple[str | None, str | None]:
    """``(ref, error)`` for integration branch ``ib`` named by the workflow config ``where``."""
    if remotes:
        ref = f"refs/remotes/{remote}/{ib}"
        if not git_text(["rev-parse", "--verify", "--quiet", ref], repo_root):
            return None, (
                f"integration branch {ib!r} {where} is not fetched as {remote}/{ib}, and with the "
                f"remote {remote!r} configured the review policy is read only from that "
                f"remote-tracking ref; run `git fetch {remote} {ib}`, or fix integration_branch on "
                "the integration branch"
            )
    else:
        from specy_road.finish_implementation_check import base_ref   # the finish gate's helpers

        ref = base_ref(repo_root, remote, ib)
        if ref is None:
            return None, (
                f"integration branch {ib!r} {where} has neither {remote}/{ib} nor a local branch, "
                "so review policy cannot be read from it; fetch it, or fix integration_branch on "
                "the integration branch"
            )
    named = str(committed_yaml(repo_root, ref, WORKFLOW_REL).get("integration_branch") or "main")
    if named != ib:
        return None, (
            f"integration branch {ib!r} {where}, but {ref} names {named!r} "
            "in its own committed copy; review policy is read only from a branch that names "
            "itself. Either HEAD was pointed at the wrong branch (fix integration_branch on this "
            f"branch to {named!r}) or {ib!r} is not the integration branch"
        )
    return ref, None


def policy_source(repo_root: Path) -> tuple[str | None, str | None]:
    """``(ref, error)``: the integration branch ref that review policy is read from.

    The remote and branch come from ``roadmap/git-workflow.yaml`` as committed
    on the remote's default branch, or at HEAD in a repo without remotes
    (:func:`integration_name`) — never from the working tree or the
    ``SPECY_ROAD_INTEGRATION_BRANCH`` / ``SPECY_ROAD_REMOTE`` variables, which an
    agent can change without a trace. When that branch cannot be found the
    result is an error, not a fall back: the gate fails closed. ``(None, None)``
    only outside git, where the working tree is all there is.

    The branch named must name itself too, and with a remote configured only
    the remote-tracking ref is read (:func:`trusted_integration_ref`).
    """
    if not full_sha(repo_root, "HEAD"):
        return None, None
    remotes = (git_text(["remote"], repo_root) or "").split()
    named, err = integration_name(repo_root, remotes)
    if named is None:
        return None, err
    return trusted_integration_ref(repo_root, remotes, *named)


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
    flag = committed_yaml(repo_root, ref, WORKFLOW_REL)
    return bool(flag.get("require_implementation_review_before_finish"))


# --- Whether the two review-gate settings agree ---
#
# ``roadmap/orchestration.yaml`` says how many reviewers a leaf needs;
# ``require_implementation_review_before_finish`` in ``roadmap/git-workflow.yaml`` says whether
# ``finish-this-task`` enforces them. With the first asking for reviewers and the second off,
# ``review status`` reports a gate that finish never checks, so finish lands the leaf with the gate
# unmet. ``validate`` and ``doctor`` report that as an error. Nothing turns the gate on: that is the
# project's call.
#
# The gate counts as on by :func:`review_required`, the rule finish uses (working tree or
# integration branch, failing closed). A missing ``orchestration.yaml`` asks for no reviewers here:
# the file is optional, and a repo without one has stated no review policy. An unreadable one is
# left to the commands that report its error.

GATE_KEY = SWITCH
#: The fix the mismatch message names, also printed by ``mark-implementation-reviewed``.
GATE_FIX = f"set `{GATE_KEY}: true` in {WORKFLOW_REL}"


def gate_config_mismatch(repo_root: Path, *, gate_on: bool | None = None) -> str | None:
    """The error when ``orchestration.yaml`` requires reviewers but finish does not enforce them,
    else ``None``.

    ``gate_on`` is :func:`review_required` when the caller already has it.
    """
    data, err = load_orchestration_config(repo_root)
    if err or data is None:
        return None
    required = int({**DEFAULT_POLICY, **(data.get("policy") or {})}["reviewers_required"])
    if review_required(repo_root) if gate_on is None else gate_on:
        return None
    return (
        f"{ORCHESTRATION_REL} requires {required} reviewer(s) "
        "(policy.reviewers_required), "
        f"but {WORKFLOW_REL} leaves {GATE_KEY} off, so finish-this-task does not "
        f"enforce the review gate and would land a leaf without those reviews. Fix: {GATE_FIX}."
    )


def report_gate_mismatch(repo_root: Path) -> bool:
    """Print the mismatch as ``error:`` on stderr; whether there was one."""
    msg = gate_config_mismatch(repo_root)
    if msg:
        print(f"error: {msg}", file=sys.stderr)
    return msg is not None


@contextlib.contextmanager
def _unreadable_as(what: str) -> Iterator[None]:
    """The module's one rule: inside a boundary, any :data:`UNREADABLE` failure becomes
    :class:`PolicyUnreadable` naming ``what``; a :class:`PolicyUnreadable` raised inside passes
    through unchanged."""
    try:
        yield
    except PolicyUnreadable:
        raise
    except UNREADABLE as e:
        first = (str(e).splitlines() or [""])[0][:200]
        raise PolicyUnreadable(f"{what} cannot be read ({type(e).__name__}: {first})") from e


def _git_read(root: Path, args: list[str]) -> str | None:
    """git's output; ``None`` only when git ran and exited non-zero (a path or commit that is not
    there). Output git could not deliver or decode (``GitResult.failure``) raises
    :class:`PolicyUnreadable`: never read as absent."""
    r = run(args, root)
    if r.failure:
        raise PolicyUnreadable(
            f"`git {' '.join(args)}` output cannot be read ({r.failure}: {r.message})")
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
    """The hashed keys at ``ref``. One shape rule, checked here so every reader (claim, gate,
    finish, accept-policy) gets it: ``roster`` is null or a list of mappings and ``policy`` is null
    or a mapping; anything else raises :class:`PolicyUnreadable`. ``substitutions`` and the review
    switch are hashed and compared as written, whatever their shape (their change lines need no
    structure)."""
    orch, flow = _yaml_at(root, ref, ORCHESTRATION_REL), _yaml_at(root, ref, WORKFLOW_REL)
    roster, policy = orch.get("roster"), orch.get("policy")
    if not (roster is None
            or isinstance(roster, list) and all(isinstance(e, dict) for e in roster)):
        raise PolicyUnreadable(f"{ORCHESTRATION_REL} at {ref}: roster is not a list of mappings")
    if not (policy is None or isinstance(policy, dict)):
        raise PolicyUnreadable(f"{ORCHESTRATION_REL} at {ref}: policy is not a mapping")
    return {"roster": roster, "substitutions": orch.get("substitutions"), "policy": policy,
            SWITCH: flow.get(SWITCH)}


def _encode(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def policy_digest(root: Path, ref: str) -> tuple[str, dict[str, Any]]:
    """``(sha256 hex, parts)`` of the review policy committed at ``ref``; raises
    :class:`PolicyUnreadable`."""
    # sort_keys on mixed-type keys, deep nesting
    with _unreadable_as(f"the review policy at {ref}"):
        parts = policy_parts(root, ref)
        return hashlib.sha256(_encode(parts).encode("utf-8")).hexdigest(), parts


def pinned_message(root: Path, message: str) -> str:
    """Pickup's registration message with the pin trailer for HEAD; exits 1 when a policy file does
    not parse.

    Nothing is committed in a repository with no commit yet, so there is nothing to pin.
    """
    # Imported here: ``validate`` imports this module for :func:`review_required`, and the
    # pickup commit module is not part of what it checks.
    from specy_road.registration_pickup_commit import with_policy_trailer

    head = full_sha(root, "HEAD")
    if not head:
        return message
    try:
        digest, _ = policy_digest(root, head)
    except PolicyUnreadable as e:
        print(f"error: {e}; fix it on the integration branch before claiming "
              "(nothing was registered)", file=sys.stderr)
        raise SystemExit(1) from e
    return with_policy_trailer(message, digest, head)


def pin_of(root: Path, codename: str, tip: str) -> tuple[str, str] | None:
    """``(sha256, commit)`` from the newest registration commit of ``codename`` reachable from
    ``tip``.

    ``None`` when there is no such commit or it has no trailer; :class:`PolicyUnreadable` when the
    trailer is present but does not parse.
    """
    subject = f"chore(rm-{codename}): {REGISTER_SUBJECT}"
    log = _git_read(root, ["log", "--format=%H %s", f"--grep={REGISTER_SUBJECT}",
                           "--fixed-strings", tip]) or ""
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
            out += [f"roster {rid}.{p} {_encode(before[rid].get(p))} -> "
                    f"{_encode(after[rid].get(p))}"
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
        out.append("roster or policy changed in order or form "
                   "(for example a missing key now empty)")
    return out


def acceptance_path(root: Path, node_id: str) -> Path:
    return reviews_dir(root, node_id) / ACCEPTANCE_NAME


def read_acceptance(root: Path, node_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """``(acceptance, None)``, ``(None, None)`` when there is none, or ``(None, why)`` when it is
    present but unreadable or invalid (the module's one rule; a directory or a symlink in its place,
    dangling or not, counts as present). The presence check is inside the boundary: an unreadable
    parent is invalid, never absent."""
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


def _pin_state(root: Path, node: dict[str, Any],
               commit: str) -> tuple[str, str, str, str, list[str]] | None:
    """``(ref, pinned sha256, pinned commit, current sha256, change lines)`` when the policy changed
    since the claim, else ``None``. The gate's committed-policy boundary: every read here is under
    the module's one rule."""
    ref, _err = policy_source(root)   # an unreadable source is the gate's config error already
    with _unreadable_as("the review policy pin"):
        pin = pin_of(root, node["codename"], commit) if ref and node.get("codename") else None
        if pin is None:
            return None
        current, _ = policy_digest(root, ref)
        return None if current == pin[0] else (ref, pin[0], pin[1], current,
                                               change_lines(root, pin[1], ref))


def pin_problem(root: Path, node: dict[str, Any], commit: str) -> str | None:
    """Why the policy that judges ``node`` at ``commit`` is not the one pinned at its claim, else
    ``None``.

    One rule for the acceptance file: when ``POLICY-ACCEPTED.yaml`` exists and is invalid it is a
    problem, whatever the pin and the policy say, so an invalid file is never silently ignored; a
    valid one counts only for the pinned and current digests it names.
    """
    nid = node["id"]
    accepted, invalid = read_acceptance(root, nid)
    if invalid:
        return (f"{invalid}; an invalid acceptance never counts: delete "
                f"work/reviews/{nid}/{ACCEPTANCE_NAME}, and a human re-runs "
                f"`specy-road review accept-policy {nid}` in a terminal if the policy changed")
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
    """``finish-this-task``: exit 1 with the problem when the policy changed since the claim
    (checked at HEAD)."""
    if problem := pin_problem(root, node, "HEAD"):
        print(f"error: {problem}", file=sys.stderr)
        raise SystemExit(1)


def _asked_because() -> str:
    """Plain language for the accept-policy prompt and the gate refusal: what changed, why a person
    is asked, what approving covers, and the installed-package reference. The raw change lines are
    printed below it."""
    return (
        "What changed is listed below, one line per change. "
        "The review rules changed after this work started, so a person is asked before the review "
        "gate can pass. "
        "Approving means each named leaf may be judged by the policy on the integration branch "
        "now. "
        "An acceptance covers only that leaf and the two digests it names, the one pinned when it "
        "was claimed and the one accepted now; a later policy change needs a new acceptance. "
        "Decline by re-claiming the leaf. "
        f"What is fingerprinted is in the installed package: {INSTALLED_REFERENCE}."
    )


def _policy_refusal(nid: str, ref: str, at: str, lines: list[str]) -> str:
    """The gate's refusal: the plain-language explanation, then each raw change line, then how to
    accept."""
    # one line per change, below the explanation
    raw = "".join(f"\n      {line}" for line in lines)
    return (
        f"review policy changed on {ref} since {nid} was claimed ({at[:12]}):\n"
        f"    {_asked_because()}\n"
        f"{raw}\n"
        f"    a human accepts it with `specy-road review accept-policy {nid}` in a terminal, "
        "or re-claims the leaf"
    )
