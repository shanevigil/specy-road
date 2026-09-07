"""Resolve the three files a landing merge must never 3-way-merge.

``roadmap/registry.yaml`` is a **keyed collection** -- one row per active claim
-- and ``roadmap.md`` / ``roadmap-context.md`` are generated in full from the
graph. Git merges all three as free text, which fails two ways once more than
one lane finishes against a single integration branch:

* it **conflicts**, and the finish is left half-done -- the feature branch
  pushed with its bookkeeping commit, never merged, the claim never cleared
  from shared truth;
* or it **succeeds and is wrong**. A line-based diff has no notion of "this row
  must be gone", so an unrelated nearby edit that shifts line context can
  retain a row both lanes removed. No conflict markers, no error, wrong shared
  state. The absence of a conflict is not evidence of a correct result.

The post-merge content of these three paths is never actually ambiguous.
``do-next-available-task`` registers every claim **on the integration branch**
and pushes it immediately, so integration's committed registry is current for
every claim except the one now finishing. The only safe post-condition is
therefore one computed from integration's own content:

    integration's registry at fetch time, minus the finishing node's row

-- independent of the feature branch's necessarily-stale copy -- with the two
generated files re-rendered from the merged graph.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.export_roadmap_md import reexport_roadmap_md
from specy_road.bundled_scripts.roadmap_chunk_utils import discover_manifest_path
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.generated_files import GENERATED_COMMITTED, unstageable_generated_files
from specy_road.git_subprocess import git_code, git_ok
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.registry_yaml import REGISTRY_REL, registry_path, write_registry

#: Branch prefix a roadmap leaf's work lives on.
FEATURE_RM_PREFIX = "feature/rm-"

#: Paths whose landed content is a function of the integration branch plus the
#: merged graph, never of a line-based 3-way merge.
DETERMINISTIC_PATHS: tuple[str, ...] = (REGISTRY_REL.as_posix(), *GENERATED_COMMITTED)

#: Reading one blob out of a ref; short, because a hung git must not hang a merge.
_REF_READ_TIMEOUT = 4.0


class DeterministicResolveError(RuntimeError):
    """Resolution could not complete; the caller must abort the merge."""


def codename_from_branch(branch: str) -> str | None:
    """``feature/rm-x`` -> ``x``; anything else -> ``None``."""
    if not branch.startswith(FEATURE_RM_PREFIX):
        return None
    return branch[len(FEATURE_RM_PREFIX):] or None


def unmerged_paths(repo: Path) -> list[str]:
    """Repo-relative paths git left conflicted, or ``[]`` when it cannot say."""
    ok, out = git_ok(["diff", "--name-only", "--diff-filter=U"], repo)
    if not ok:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def merge_in_progress(repo: Path) -> bool:
    """Whether a merge is actually staged and waiting for its commit.

    ``git merge --no-commit`` of an ancestor prints "Already up to date.",
    exits 0 and writes no ``MERGE_HEAD``. Committing then would fabricate a
    stray non-merge commit on the shared branch, so the caller checks first.
    """
    code, _ = git_code(["rev-parse", "-q", "--verify", "MERGE_HEAD"], repo)
    return code == 0


def _has_roadmap_graph(repo: Path) -> bool:
    """Whether this repo has a roadmap manifest to render from at all.

    A repo can legitimately have none -- a consumer that has not run
    ``init project`` yet, or the toolkit's own tests -- and such a repo must
    still be able to land a merge.
    """
    try:
        discover_manifest_path(repo)
    except FileNotFoundError:
        return False
    return True


def _resolve_registry(repo: Path, codename: str | None) -> str | None:
    """Write integration's registry minus ``codename``. Rel path, or ``None``.

    ``None`` means this repo has no registry on either side of the merge -- a
    repo without roadmap bookkeeping still merges, it just has nothing here to
    resolve.

    Read from the refs rather than the worktree: mid-merge the working copy may
    hold conflict markers, and ``git show`` is the only view of either side
    that is guaranteed clean.
    """
    head = read_registry_at_ref(repo, "HEAD", _REF_READ_TIMEOUT)
    theirs = read_registry_at_ref(repo, "MERGE_HEAD", _REF_READ_TIMEOUT)
    if head is None and theirs is None:
        return None
    rel = REGISTRY_REL.as_posix()
    doc = head if head is not None else theirs
    entries = [e for e in (doc.get("entries") or []) if isinstance(e, dict)]
    if codename is not None and any(e.get("codename") == codename for e in entries):
        doc["entries"] = [e for e in entries if e.get("codename") != codename]
        write_registry(registry_path(repo), doc)
    elif head is not None:
        # Nothing to remove: restore integration's blob byte for byte rather
        # than re-dumping it. write_registry normalises YAML and drops
        # comments, and the scaffolded registry ships with a header comment.
        # This also clears any conflict stage for the path.
        git_code(["checkout", "HEAD", "--", rel], repo)
    else:
        # The registry exists only on the feature side; HEAD has no blob to
        # restore, so write the parsed document out.
        write_registry(registry_path(repo), doc)
    return rel


def _regenerate_generated_files(repo: Path) -> list[str]:
    """Re-render ``roadmap.md`` and ``roadmap-context.md``. Paths to stage.

    ``[]`` when the repo has no roadmap graph at all. Both renderers reach the
    roadmap loader, which reports a malformed graph by raising ``SystemExit``
    rather than returning -- hence the unusual except clause. This function is
    the one place in the landing path that can fail loudly, and its caller
    turns that into an aborted merge rather than a traceback.
    """
    if not _has_roadmap_graph(repo):
        return []
    try:
        reexport_roadmap_md(repo)
        (repo / DEFAULT_OUTPUT).write_text(render_digest(repo), encoding="utf-8")
    except (Exception, SystemExit) as exc:
        raise DeterministicResolveError(
            f"could not regenerate {', '.join(GENERATED_COMMITTED)} from the "
            f"merged roadmap graph: {exc}"
        ) from exc
    refused = set(unstageable_generated_files(repo))
    for name in sorted(refused):
        print(
            f"[warn] not staging {name}: it is gitignored and untracked, so "
            f"`git add` would refuse it and abort this merge commit. "
            f"Track it once with: git add -f {name}"
        )
    return [n for n in GENERATED_COMMITTED if n not in refused]


def resolve_deterministic_paths(repo: Path, *, codename: str | None) -> list[str]:
    """Resolve all three paths in the staged merge. Returns paths to stage.

    Registry first, then the derived files: ``render_digest`` reads the
    registry from the **worktree** to list claims still in flight, so the
    digest must be rendered after the row is gone. Reordering these two lines
    silently reintroduces the drift.
    """
    staged: list[str] = []
    rel = _resolve_registry(repo, codename)
    if rel is not None:
        staged.append(rel)
    staged.extend(_regenerate_generated_files(repo))
    return staged


def _failed(
    repo: Path, integration_branch: str, feature_branch: str, detail: str
) -> tuple[bool, str]:
    """Abort the staged merge and report in the caller's established wording."""
    git_code(["merge", "--abort"], repo)
    return (
        False,
        f"git merge {feature_branch} into {integration_branch} failed: {detail}",
    )


def _reconcile_digest(repo: Path) -> bool:
    """Re-render the digest now that the merge commit exists. True when amended.

    ``roadmap-context.md`` lists dependency edges that were added and later
    removed, and that section comes from a ``git log --first-parent`` walk of
    **HEAD**. Rendered before the merge commit exists, the walk cannot reach
    the feature branch's commits at all -- under ``--first-parent`` they only
    become visible as the merge's own step -- so a leaf that dropped an edge
    would land a digest missing that line and hand CI the ``digest --check``
    drift this toolkit tells people to gate on.

    One pass converges: the amend only ever touches the registry and the two
    generated files, and the event feed is built from ``roadmap/*.json`` and
    ``planning/*.md`` alone, so nothing it rewrites can change the feed.
    """
    if not _has_roadmap_graph(repo):
        return False
    target = repo / DEFAULT_OUTPUT
    fresh = render_digest(repo)
    if target.is_file() and target.read_text(encoding="utf-8") == fresh:
        return False
    target.write_text(fresh, encoding="utf-8")
    if DEFAULT_OUTPUT in set(unstageable_generated_files(repo)):
        return False
    git_code(["add", "--", DEFAULT_OUTPUT], repo)
    git_code(["commit", "--amend", "--no-edit"], repo)
    return True


def _commit_message(feature_branch: str, integration_branch: str, codename: str | None) -> list[str]:
    """Subject and body for the resolved merge commit."""
    subject = f"Merge branch '{feature_branch}' into {integration_branch}"
    minus = f" minus rm-{codename}" if codename else ""
    body = (
        f"roadmap/registry.yaml resolved to {integration_branch}{minus}; "
        "roadmap.md and roadmap-context.md regenerated from the merged graph. "
        "These three files are keyed or generated, not mergeable: a line-based "
        "3-way merge can retain a row both lanes removed."
    )
    return ["-m", subject, "-m", body]


def merge_feature_deterministically(
    repo: Path,
    *,
    integration_branch: str,
    feature_branch: str,
) -> tuple[bool, str]:
    """Merge ``feature_branch`` into the checked-out integration branch.

    The merge is staged rather than committed so the three deterministic paths
    can be recomputed from the integration branch plus the merged graph before
    the commit exists. Conflicts confined to those paths are resolved and the
    merge lands; a conflict anywhere else aborts and reports exactly as before.

    Returns ``(True, "")``, or ``(False, message)`` with the merge aborted and
    the integration branch unchanged. Never raises: the caller's whole contract
    is that it can report a failure and check the feature branch back out.
    """
    codename = codename_from_branch(feature_branch)
    ok, pre_sha = git_ok(["rev-parse", "HEAD"], repo)
    if not ok:
        return False, f"could not read {integration_branch} HEAD before merging"

    code, out = git_code(["merge", "--no-commit", "--no-ff", feature_branch], repo)
    if code != 0:
        unmerged = unmerged_paths(repo)
        stray = [p for p in unmerged if p not in DETERMINISTIC_PATHS]
        if not unmerged or stray:
            # Either not a content conflict at all, or a real one in the
            # source. Both are the caller's existing hard failure.
            return _failed(repo, integration_branch, feature_branch, out)
        print(
            "[ok] resolving generated bookkeeping conflict in "
            f"{', '.join(unmerged)} from {integration_branch}"
        )

    if not merge_in_progress(repo):
        return True, ""  # already up to date; its bookkeeping is already here

    try:
        staged = resolve_deterministic_paths(repo, codename=codename)
    except DeterministicResolveError as exc:
        return _failed(repo, integration_branch, feature_branch, str(exc))

    if staged:
        code, out = git_code(["add", "--", *staged], repo)
        if code != 0:
            return _failed(
                repo, integration_branch, feature_branch,
                f"staging {', '.join(staged)} failed: {out}",
            )

    code, out = git_code(
        ["commit", *_commit_message(feature_branch, integration_branch, codename)],
        repo,
    )
    if code != 0:
        return _failed(repo, integration_branch, feature_branch, f"commit: {out}")

    try:
        if _reconcile_digest(repo):
            print(f"[ok] {DEFAULT_OUTPUT} reconciled against the merge commit")
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - see module docstring
        git_code(["reset", "--hard", pre_sha], repo)  # nothing pushed yet
        return (
            False,
            f"git merge {feature_branch} into {integration_branch} failed while "
            f"reconciling {DEFAULT_OUTPUT}: {exc}",
        )
    return True, ""
