"""The roster and profiles as the integration branch has them: what prompts, plans and workers must route by.

The review gate reads ``roadmap/orchestration.yaml`` from the integration
branch (``review_policy_ref.policy_source``), never from the working tree an agent
can edit without a trace. Routing has to read the same file: a working-tree
roster could widen ``may_process`` on an outside model, add a ``channels.cli``
or ``preflight`` command, or name a reviewer the gate will later refuse.

The same goes for a model profile: its ``access.cli`` is executed by
``prompt --channel cli`` and ``worker delegate``, so
:func:`pinned_profile_for_entry` reads it from the same ref and refuses a
working-tree copy that differs from it. Outside git the working tree is all
there is. :func:`roster_source` names the ref, and says when the working-tree
or local integration branch's roster is not what routing reads, or when there is none.
"""

from __future__ import annotations

import copy
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.model_profiles import (
    PROFILES_REL,
    Profile,
    parse_profile,
    profile_for_entry,
    profile_rel_problem,
)
from specy_road.orchestration_config import (
    DEFAULT_CONFIG,
    ORCHESTRATION_REL,
    effective_config,
    load_orchestration_config,
    orchestration_yaml_path,
)
from specy_road.review_policy_ref import integration_name, policy_source
from specy_road.review_target import full_sha
from specy_road.roster_local import merge_local_roster


#: ``roster_ref`` of a plan built with ``worktree=True``: a dry run nothing may launch from.
WORKTREE_REF = "worktree"


def pinned_config(repo_root: Path, *, worktree: bool = False) -> tuple[dict[str, Any], str | None]:
    """``(config, error)`` from the integration branch; an unreadable branch is an error, not a fallback.

    This clone's ``roster_add`` entries (:mod:`specy_road.roster_local`) follow the pinned ones.
    ``worktree=True`` reads the working tree's file instead; only ``orchestrate plan --roster-from-worktree``
    passes it, and every delegation entry point keeps the pinned roster."""
    if worktree:
        config, err = effective_config(repo_root)
    else:
        ref, err = policy_source(repo_root)
        if err:
            return {}, err
        config, err = effective_config(repo_root, ref)
    if err:
        return config, err
    local_err = merge_local_roster(repo_root, config,
                                   lambda e: pinned_profile_for_entry(repo_root, e, worktree=worktree))
    return (copy.deepcopy(DEFAULT_CONFIG), local_err) if local_err else (config, None)


def roster_diff(repo_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """The working tree's roster against the pinned one, by entry id: ``{added, removed, changed}`` with
    ``changed`` mapping an id to its differing fields; ``None`` when they agree (or outside git).

    The two files are compared as written, before this clone's availability overlay, which would
    otherwise apply the same values to both and hide an edited field."""
    ref, err = policy_source(repo_root)
    if err or ref is None:
        return None, err
    pinned, err = _file_roster(repo_root, ref)
    mine, mine_err = _file_roster(repo_root) if not err else ([], None)
    if err or mine_err:
        return None, err or f"working tree: {mine_err}"
    old = {str(e.get("id")): e for e in pinned}
    new = {str(e.get("id")): e for e in mine}
    changed = {i: sorted(k for k in {*old[i], *new[i]} if old[i].get(k) != new[i].get(k))
               for i in old.keys() & new.keys() if old[i] != new[i]}
    diff = {"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "changed": dict(sorted(changed.items()))}
    return (diff if any(diff.values()) else None), None


def _file_roster(repo_root: Path, ref: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """The validated file's roster at ``ref`` (working tree when ``None``), with no overlay applied;
    an absent file is the default roster, as :func:`effective_config` has it."""
    data, err = load_orchestration_config(repo_root, ref)
    if err:
        return [], err
    return (DEFAULT_CONFIG if data is None else data).get("roster") or [], None


class RosterReport(NamedTuple):
    ref: str | None             # where routing reads the roster: <remote>/<branch> or <branch>; None outside git
    drift: str | None           # a roster the adopter can see that routing does not read, and the remedy
    none_anywhere: bool = False  # no roster at the ref, on the local branch or in the working tree
    on_ref: bool = False        # the ref has a roster, so routing does not use the default one


def roster_source(repo_root: Path) -> tuple[str | None, str | None]:
    """``(ref, drift)`` from :func:`roster_report`."""
    report = roster_report(repo_root)
    return report.ref, report.drift


def roster_report(repo_root: Path) -> RosterReport:
    """Where :func:`pinned_config` reads the roster from, and a sentence when routing ignores a roster
    (or a deletion) the adopter can see.

    Three copies are compared: the working tree's ``roadmap/orchestration.yaml``, the local
    integration branch's when it has unpushed commits, and the ref's. A working tree that differs from
    both (edited, added or deleted) says commit to the integration branch (and push); a roster added,
    deleted or changed on the unpushed local branch says push, whatever the working tree holds. With
    no roster anywhere the sentence says so and points at the docs, since the default roster has no
    executor; ``validate`` reports that case as a notice rather than a warning."""
    full, err = policy_source(repo_root)
    if err or full is None:
        return RosterReport(None, None)
    ref = full.removeprefix("refs/remotes/").removeprefix("refs/heads/")
    local, rel = orchestration_yaml_path(repo_root), ORCHESTRATION_REL.as_posix()
    try:
        mine = local.read_text(encoding="utf-8") if local.is_file() else None
    except OSError:
        mine = None
    committed = _blob(repo_root, full, rel)
    remote, ib = _integration(repo_root, full, ref)
    # The local integration branch counts only when it is ahead of the ref: a stale one is not news.
    branch = _blob(repo_root, f"refs/heads/{ib}", rel) if remote and _unpushed(repo_root, full, ib) else committed
    where = f"{ref}, where the roster is read from"
    on_ref = committed is not None
    if mine != committed and mine != branch:   # neither copy: an uncommitted edit, addition or deletion
        fix = f"committed to {ib} and pushed to {remote}" if remote else f"committed to {ib}"
        if mine is None:
            return RosterReport(ref, f"{rel} is deleted in the working tree but still on {where}; routing "
                                     f"uses the copy there until the deletion is {fix}", on_ref=on_ref)
        if committed is None:
            return RosterReport(ref, f"{rel} is not on {where}, so routing uses the default roster "
                                     f"(no models) until it is {fix}")
        return RosterReport(ref, f"{rel} in the working tree differs from {where}; routing uses the copy "
                                 f"there until the change is {fix}", on_ref=on_ref)
    push = f"until {ib} is pushed to {remote}"
    if branch != committed and committed is None:
        return RosterReport(ref, f"{rel} is committed on the local {ib} but not on {where}, so routing "
                                 f"uses the default roster (no models) {push}")
    if branch != committed and branch is None:
        return RosterReport(ref, f"{rel} is deleted on the local {ib} but still on {where}; routing uses "
                                 f"the copy there {push}", on_ref=on_ref)
    if branch != committed:
        return RosterReport(ref, f"{rel} on the local {ib} differs from {where}; routing uses the copy "
                                 f"there {push}", on_ref=on_ref)
    if mine is None and committed is None:
        return RosterReport(ref, f"no {rel} on {where}, nor in the working tree, so routing uses the default "
                                 "roster (one human, no executor); see docs/orchestration.md to write and "
                                 "commit one", none_anywhere=True)
    return RosterReport(ref, None, on_ref=on_ref)


def _unpushed(repo_root: Path, full: str, ib: str) -> bool:
    """The local ``ib`` has commits the remote-tracking ref lacks (a merely stale one is not news)."""
    return (git_text(["rev-list", "--count", f"{full}..refs/heads/{ib}"], repo_root) or "0").strip() != "0"


def _integration(repo_root: Path, full: str, ref: str) -> tuple[str | None, str]:
    """``(remote, branch)`` behind the roster ref; ``remote`` is ``None`` when it is a local branch."""
    if not full.startswith("refs/remotes/"):
        return None, ref
    named, _err = integration_name(repo_root, (git_text(["remote"], repo_root) or "").split())
    if named is None:   # policy_source just resolved it; split the ref as a fallback
        remote, _, ib = ref.partition("/")
        return remote, ib
    return named[0], named[1]


def _blob(repo_root: Path, sha: str, rel: str) -> str | None:
    """The committed text, or ``None`` when absent; a symlink in the tree counts as absent."""
    mode = git_text(["ls-tree", sha, "--", rel], repo_root) or ""
    if not mode or mode.startswith("120000"):
        return None
    return git_stdout(["show", f"{sha}:./{rel}"], repo_root)   # ./ = project-root relative (nested layout)


def _pinned_at(repo_root: Path, sha: str, rel: str, ref: str) -> Profile:
    """The committed profile, refused when the working-tree copy would be a different thing to run."""
    committed = _blob(repo_root, sha, rel)
    local = repo_root / rel
    if committed is None:
        return Profile(local, {}, errors=[
            f"{rel} is not committed on the integration branch ({ref}); "
            "commit it there first — its access.cli is executed, so it is read from the pinned ref"])
    try:
        mine = local.read_text(encoding="utf-8") if local.is_file() else None
    except OSError:
        mine = None
    if mine is not None and mine != committed:
        return Profile(local, {}, errors=[
            f"{rel} in the working tree differs from the copy on the integration branch ({ref}); "
            "commit it to the integration branch first (dispatch runs only the committed profile)"])
    return parse_profile(local, committed)


@cache
def _committed_profile_paths(root: str, sha: str) -> tuple[str, ...]:
    out = git_text(["ls-tree", "-r", "--name-only", sha, "--", PROFILES_REL.as_posix()], Path(root)) or ""
    return tuple(p for p in out.splitlines() if p.endswith(".md") and not p.endswith("/README.md"))


def _pinned_for_id(repo_root: Path, sha: str, path: str, ref: str, model_id: Any) -> Profile | None:
    """The pinned profile when it is ``model_id``, including one refused because the working tree differs.

    A refusal carries no front matter, so :meth:`Profile.for_id` can see only the file name and an
    alias or ``api_id`` would miss it. The committed text is what decides the match; the refusal
    itself is what is returned, so dispatch still stops.
    """
    pinned = _pinned_at(repo_root, sha, path, ref)
    if pinned.ok:
        return pinned.for_id(model_id)
    text = _blob(repo_root, sha, path)
    if text is not None and parse_profile(pinned.path, text).for_id(model_id):
        return pinned
    return pinned.for_id(model_id)


def pinned_profile_for_entry(repo_root: Path, entry: dict[str, Any], *, worktree: bool = False) -> Profile | None:
    """The roster entry's profile as committed on the integration branch (working tree outside git, or
    with ``worktree=True``, the dry run :func:`pinned_config` describes).

    ``profile:`` names the path; without it a committed profile whose ``api_id``,
    file name or ``aliases`` include the entry's ``id`` is used, as :func:`profile_for_entry` does.
    """
    if worktree:
        return profile_for_entry(repo_root, entry)
    ref, err = policy_source(repo_root)
    if err:
        return Profile(repo_root / str(entry.get("profile") or entry.get("id")), {}, errors=[err])
    if ref is None:
        return profile_for_entry(repo_root, entry)
    sha = full_sha(repo_root, ref) or ref
    rel = entry.get("profile")
    if rel:
        why = profile_rel_problem(repo_root, str(rel))
        if why:
            return Profile(repo_root / str(rel), {}, errors=[why])
        prof = _pinned_at(repo_root, sha, Path(str(rel)).as_posix(), ref)
        return prof.for_id(entry.get("id")) or prof
    paths = _committed_profile_paths(str(repo_root), sha)
    return next((m for path in paths
                 if (m := _pinned_for_id(repo_root, sha, path, ref, entry.get("id")))), None)

