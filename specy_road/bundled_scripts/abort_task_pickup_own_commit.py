"""Whether the commit ahead of the remote integration branch is pickup's own registration.

A ``--local`` pickup never pushes its claim, so abort drops that one commit
instead of deregistering on the remote. The commit must look exactly like
pickup's: the registration subject, the registry changed only by adding this
claim's row, and otherwise at most the two generated files pickup renders
again in the same commit (:mod:`specy_road.bundled_scripts.do_next_task_register`),
so abort never resets away a commit amended to carry other work.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.registration_pickup_commit import registration_commit_message
from specy_road.bundled_scripts.repo_ops import git_capture
from specy_road.generated_files import GENERATED_COMMITTED
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.registry_yaml import REGISTRY_REL
from specy_road.runtime_paths import project_prefix


def registers_only(root: Path, commit: str, codename: str) -> bool:
    """True when ``commit``'s registry is its parent's plus this claim's row, nothing else.

    Compared parsed: pickup rewrites the file, dropping comments and restyling.
    """
    empty = {"version": 1, "entries": []}
    after = read_registry_at_ref(root, commit, 30.0) or empty
    before = read_registry_at_ref(root, f"{commit}^", 30.0) or empty
    entries = after.get("entries") or []
    rest = [e for e in entries if not (isinstance(e, dict) and e.get("codename") == codename)]
    return len(entries) - len(rest) == 1 and (
        {**after, "entries": rest} == {**before, "entries": before.get("entries") or []}
    )


def only_own_registration_ahead(
    root: Path, remote: str, base: str, codename: str, ref: str, *, capture=git_capture
) -> bool:
    """True when the one commit on ``ref`` missing from ``remote/base`` is this claim's registration.

    ``capture`` is the caller's ``git_capture``, so its git reads stay patchable where they were.
    """
    ahead = capture(root, "rev-list", f"{remote}/{base}..{ref}").split()
    if len(ahead) != 1:
        return False
    subject = capture(root, "log", "-1", "--format=%s", ahead[0])
    paths = capture(root, "diff-tree", "--no-commit-id", "--name-only", "-r", ahead[0]).splitlines()
    prefix = project_prefix(root)   # diff-tree names paths from the repository root
    registry = prefix + REGISTRY_REL.as_posix()
    generated = {prefix + n for n in GENERATED_COMMITTED}
    own = registration_commit_message(codename, include_ci_skip=False)
    return (
        subject.startswith(own)
        and registry in paths
        and set(paths) <= {registry, *generated}
        and registers_only(root, ahead[0], codename)
    )
