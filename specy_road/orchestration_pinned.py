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

from functools import cache
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.model_profiles import (
    PROFILES_REL,
    Profile,
    parse_profile,
    profile_for_entry,
    profile_rel_problem,
)
from specy_road.orchestration_config import ORCHESTRATION_REL, effective_config, orchestration_yaml_path
from specy_road.review_policy_ref import integration_name, policy_source
from specy_road.review_target import full_sha


def pinned_config(repo_root: Path) -> tuple[dict[str, Any], str | None]:
    """``(config, error)`` from the integration branch; an unreadable branch is an error, not a fallback."""
    ref, err = policy_source(repo_root)
    if err:
        return {}, err
    return effective_config(repo_root, ref)


def roster_source(repo_root: Path) -> tuple[str | None, str | None]:
    """``(ref, drift)``: the ref :func:`pinned_config` reads the roster from, shortened to
    ``<remote>/<branch>`` or ``<branch>`` (``None`` outside git or when it cannot be read), and a
    sentence when routing ignores a roster the adopter can see: the working-tree
    ``roadmap/orchestration.yaml``, or the local integration branch's, is absent at that ref or differs
    from it. With no roster at the ref and none in the working tree the sentence says so and points at
    the docs, since the default roster has no executor."""
    full, err = policy_source(repo_root)
    if err or full is None:
        return None, None
    ref = full.removeprefix("refs/remotes/").removeprefix("refs/heads/")
    local, rel = orchestration_yaml_path(repo_root), ORCHESTRATION_REL.as_posix()
    try:
        mine = local.read_text(encoding="utf-8") if local.is_file() else None
    except OSError:
        mine = None
    committed = _blob(repo_root, full, rel)
    remote, ib = _integration(repo_root, full, ref)
    fix = f"committed to {ib} and pushed to {remote}" if remote else f"committed to {ib}"
    where = f"{ref}, where the roster is read from"
    if mine is None and committed is None:
        return ref, (f"no {rel} on {where}, nor in the working tree, so routing uses the default roster "
                     "(one human, no executor); see docs/orchestration.md to write and commit one")
    if mine is not None and committed is None:
        return ref, (f"{rel} is not on {where}, so routing uses the default roster (no models) "
                     f"until it is {fix}")
    if mine is not None and committed != mine:
        return ref, (f"{rel} in the working tree differs from {where}; routing uses the copy there "
                     f"until the change is {fix}")
    if remote and _unpushed(repo_root, full, ib) and _blob(repo_root, f"refs/heads/{ib}", rel) not in (None, committed):
        return ref, (f"{rel} on the local {ib} differs from {where}; routing uses the copy there "
                     f"until {ib} is pushed to {remote}")
    return ref, None


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


def pinned_profile_for_entry(repo_root: Path, entry: dict[str, Any]) -> Profile | None:
    """The roster entry's profile as committed on the integration branch (working tree outside git).

    ``profile:`` names the path; without it a committed profile whose ``api_id``,
    file name or ``aliases`` include the entry's ``id`` is used, as :func:`profile_for_entry` does.
    """
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

