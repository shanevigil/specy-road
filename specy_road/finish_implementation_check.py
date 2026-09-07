"""Refuse to close a node on a branch where nothing was implemented.

Finding 32. ``finish-this-task`` validated the graph, wrote bookkeeping,
regenerated the derived files and landed the branch without ever asking whether
the branch contained any work — so a sub-agent that registered a claim, read its
brief and stopped could still produce a node marked **Complete** with no code
behind it. The toolkit already had the human-facing version of this check
(``work/implementation-summary-<NODE_ID>.md`` plus
``mark-implementation-reviewed``), but it is opt-in, and an unattended grind
sails straight past it.

The check keys on **files changed under the node's declared touch zones**,
measured against the branch's merge base with the integration branch, and that
exact shape is chosen for the false-positive it avoids. Plenty of legitimate
leaves are small — a docs-only node whose zone is ``docs/``, a config change —
and every one of them still writes something inside its own zone. "Nothing
changed anywhere in the declared zones" describes only a branch nobody worked on.

Every ambiguity resolves toward **allowing** the finish:

* No touch zones declared (they are optional, F-009) — nothing to check against.
* Git cannot answer — no merge base, not a worktree, an unreadable ref.
* Glob matching is deliberately loose, treating ``*`` as crossing directory
  separators, because a zone that matches too much only costs a missed catch
  while a zone that matches too little breaks a legitimate finish.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.git_workflow_config import require_implementation_before_finish

_GLOB_CHARS = "*?["


def _clean(zone: object) -> str | None:
    if not isinstance(zone, str):
        return None
    cleaned = zone.strip().strip("/")
    return cleaned or None


def zone_matches(zone: str, path: str) -> bool:
    """Whether a changed repo-relative ``path`` falls inside ``zone``.

    A zone without glob characters is a file or a directory prefix; with them it
    is matched by ``fnmatch``, which does not treat ``/`` specially. That makes
    ``src/*`` match ``src/api/routes.py`` — wrong for a shell, right here, where
    the cost of matching too much is far lower than the cost of matching too
    little.
    """
    if any(c in zone for c in _GLOB_CHARS):
        return fnmatch.fnmatch(path, zone) or fnmatch.fnmatch(path, f"{zone}/*")
    return path == zone or path.startswith(f"{zone}/")


def base_ref(repo_root: Path, remote: str, integration_branch: str) -> str | None:
    """The ref to diff against: the remote-tracking branch, else the local one.

    Remote first, because the local integration branch can be arbitrarily stale
    in a clone that has been picking work up for a while, and a stale base
    inflates the diff rather than shrinking it — the safe direction, but noisier.
    """
    for ref in (
        f"refs/remotes/{remote}/{integration_branch}",
        f"refs/heads/{integration_branch}",
    ):
        if git_text(["rev-parse", "--verify", "--quiet", ref], repo_root):
            return ref
    return None


def changed_paths(repo_root: Path, ref: str) -> list[str] | None:
    """Repo-relative paths this branch changed since diverging from ``ref``.

    ``...`` rather than ``..`` so the comparison is against the merge base:
    commits that landed on the integration branch after this one branched are
    not this branch's work.
    """
    out = git_stdout(["diff", "--name-only", f"{ref}...HEAD"], repo_root)
    if out is None:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def implementation_paths(
    repo_root: Path,
    *,
    zones,
    remote: str,
    integration_branch: str,
) -> list[str] | None:
    """Changed paths inside the declared zones, or ``None`` for "cannot tell"."""
    cleaned = [z for z in (_clean(z) for z in (zones or [])) if z]
    if not cleaned:
        return None
    ref = base_ref(repo_root, remote, integration_branch)
    if ref is None:
        return None
    paths = changed_paths(repo_root, ref)
    if paths is None:
        return None
    return [p for p in paths if any(zone_matches(z, p) for z in cleaned)]


def implementation_gate_error(
    repo_root: Path,
    *,
    node_id: str,
    zones,
    remote: str,
    integration_branch: str,
) -> str | None:
    """Error text when the branch implemented nothing, else ``None``."""
    matched = implementation_paths(
        repo_root, zones=zones, remote=remote, integration_branch=integration_branch
    )
    if matched is None or matched:
        return None
    listed = ", ".join(repr(z) for z in zones if _clean(z))
    return (
        f"nothing was implemented for {node_id}: this branch changes no file "
        f"under its declared touch zones ({listed}).\n"
        "  A claim is not an implementation — finishing here would mark the node "
        "Complete with no work behind it.\n"
        "  If the work is real but lives elsewhere, fix the zones:\n"
        f"    specy-road edit-node {node_id} --set touch_zones=<paths>\n"
        "  If the node genuinely needs no code change, pass "
        "--allow-empty-implementation.\n"
        "  To release the claim instead: specy-road abort-task-pickup."
    )


def implementation_or_exit(
    repo_root: Path,
    *,
    node: dict,
    entry: dict,
    node_id: str,
    remote: str,
    integration_branch: str,
    allow_empty: bool,
) -> None:
    """Stop before any bookkeeping when the branch implemented nothing.

    Zones come from the registry row when it has them — that is the claim the
    implementer was actually handed — and fall back to the node, for a row
    registered before its zones were authored.
    """
    if allow_empty or not require_implementation_before_finish(repo_root):
        return
    error = implementation_gate_error(
        repo_root,
        node_id=node_id,
        zones=entry.get("touch_zones") or node.get("touch_zones") or [],
        remote=remote,
        integration_branch=integration_branch,
    )
    if error is None:
        return
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(1)
