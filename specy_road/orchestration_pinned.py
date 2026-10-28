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
there is.
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
from specy_road.orchestration_config import effective_config
from specy_road.review_policy_ref import policy_source
from specy_road.review_target import full_sha


def pinned_config(repo_root: Path) -> tuple[dict[str, Any], str | None]:
    """``(config, error)`` from the integration branch; an unreadable branch is an error, not a fallback."""
    ref, err = policy_source(repo_root)
    if err:
        return {}, err
    return effective_config(repo_root, ref)


def _blob(repo_root: Path, sha: str, rel: str) -> str | None:
    """The committed text, or ``None`` when absent; a symlink in the tree counts as absent."""
    mode = git_text(["ls-tree", sha, "--", rel], repo_root) or ""
    if not mode or mode.startswith("120000"):
        return None
    return git_stdout(["show", f"{sha}:{rel}"], repo_root)


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


def pinned_profile_for_entry(repo_root: Path, entry: dict[str, Any]) -> Profile | None:
    """The roster entry's profile as committed on the integration branch (working tree outside git).

    ``profile:`` names the path; without it a committed profile whose ``api_id``
    or file name is the entry's ``id`` is used, as :func:`profile_for_entry` does.
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
        return _pinned_at(repo_root, sha, Path(str(rel)).as_posix(), ref)
    for path in _committed_profile_paths(str(repo_root), sha):
        prof = _pinned_at(repo_root, sha, path, ref)
        if prof.api_id == entry.get("id") or prof.path.stem == entry.get("id"):
            return prof
    return None

