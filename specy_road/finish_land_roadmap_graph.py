"""Roadmap graph conflicts a landing resolves: the ones the branch only inherited.

``roadmap/manifest.json`` and the JSON chunks under ``roadmap/`` are authored,
not generated, so unlike the registry and the rendered files a conflict in them
is not resolved blindly. A branch whose changes there all came from earlier
merges of the integration branch -- plus finish's own bookkeeping commit -- has
nothing of its own to lose: each conflicted file takes the integration
branch's version, and the bookkeeping commit's one graph edit, the finished
leaf set to Complete (and the ancestors that rolled up with it), is applied
again on top. A branch that did edit a conflicted graph file itself is refused
with the files named; its edit is never silently dropped. Merging two real
roadmap edits is out of scope.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import (
    find_chunk_path,
    load_json_chunk,
    write_json_chunk,
)
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.git_subprocess import git_code, git_ok
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import project_prefix

#: Subject of finish-this-task's bookkeeping commit, by codename.
BOOKKEEPING_SUBJECT = "chore(rm-{codename}): complete, deregister"

#: Reading one blob out of a ref; short, because a hung git must not hang a merge.
_REF_READ_TIMEOUT = 4.0


class GraphResolveError(RuntimeError):
    """A graph path could not be resolved; the caller must abort the merge."""


def is_roadmap_graph_path(rel: str) -> bool:
    """Whether project-relative ``rel`` is part of the roadmap graph (manifest or a JSON chunk)."""
    return rel.startswith("roadmap/") and rel.endswith(".json")


def split_conflicts(
    repo: Path, unmerged: Sequence[str], deterministic: Collection[str]
) -> tuple[list[str], list[str]]:
    """Split git-root-relative conflicted paths into ``(roadmap graph, stray)``.

    ``deterministic`` (project-relative) paths are in neither list. ``stray``
    is everything else: a conflict there is a real one, which the caller
    reports as before.
    """
    prefix = project_prefix(repo)   # git names conflicted paths from the repository root
    graph: list[str] = []
    stray: list[str] = []
    for path in unmerged:
        rel = path[len(prefix):] if path.startswith(prefix) else None
        if rel in deterministic:
            continue
        (graph if rel is not None and is_roadmap_graph_path(rel) else stray).append(path)
    return graph, stray


def branch_roadmap_edits(
    repo: Path, paths: Sequence[str], *, codename: str | None, revs: Sequence[str]
) -> tuple[list[str], str | None]:
    """Which of ``paths`` the branch edited itself, and finish's bookkeeping commit.

    ``revs`` names the branch's own commits (``HEAD..MERGE_HEAD`` for a merge).
    A non-merge commit touching a path is an edit of the branch's own, except
    finish's bookkeeping commit for ``codename``; a merge is one only where its
    result differs from every parent (a hand-made resolution), so what an
    earlier merge of the integration branch brought in does not count. Git's
    default history simplification skips an edit a later merge replaced with
    the integration branch's content: the tip no longer carries it. When git
    cannot answer, every path counts as edited, so nothing is dropped.
    Paths are git-root-relative. Returns ``(edited paths, bookkeeping sha or None)``.
    """
    subject = BOOKKEEPING_SUBJECT.format(codename=codename) if codename else None
    ok, out = git_ok(
        ["log", "-c", "--name-only", "--format=%x01%H %s", *revs, "--",
         *(f":(top){p}" for p in paths)],
        repo,
    )
    if not ok:
        return list(paths), None
    wanted = set(paths)
    edited: set[str] = set()
    bookkeeping: str | None = None
    skipping = False
    for line in out.splitlines():
        if line.startswith("\x01"):
            sha, _, commit_subject = line[1:].partition(" ")
            skipping = subject is not None and commit_subject == subject
            if skipping and bookkeeping is None:
                bookkeeping = sha
        elif line.strip() in wanted and not skipping:
            edited.add(line.strip())
    return [p for p in paths if p in edited], bookkeeping


def own_roadmap_edit_refusal(paths: Sequence[str], branch: str, integration_branch: str) -> str:
    """The one-line reason a landing refuses: the branch edited conflicted graph files itself."""
    return (
        f"{branch} edits roadmap content itself in {', '.join(paths)}, which "
        f"{integration_branch} also changed; finish never drops a branch's own "
        f"roadmap edit. Next: on {branch} run `git merge {integration_branch}`, "
        "resolve those files, commit, then re-run finish"
    )


def take_integration_graph(repo: Path, paths: Sequence[str]) -> list[str]:
    """Resolve each conflicted graph path to HEAD's version. Project-relative paths to stage.

    A path HEAD does not have (the integration branch removed it) is removed
    here too, which also stages the removal.
    """
    prefix = project_prefix(repo)
    staged: list[str] = []
    for path in paths:
        spec = f":(top){path}"
        code, _ = git_code(["cat-file", "-e", f"HEAD:{path}"], repo)
        if code == 0:
            code, out = git_code(["checkout", "HEAD", "--", spec], repo)
            staged.append(path[len(prefix):])
        else:
            code, out = git_code(["rm", "-q", "-f", "--", spec], repo)
        if code != 0:
            raise GraphResolveError(
                f"could not resolve {path} to the integration branch's version: {out}"
            )
    return staged


def _finished_node_id(repo: Path, codename: str | None, bookkeeping: str) -> str | None:
    """The node finish completed: ``codename``'s row in the registry ``bookkeeping`` removed."""
    doc = read_registry_at_ref(repo, f"{bookkeeping}^", _REF_READ_TIMEOUT)
    for entry in (doc or {}).get("entries") or []:
        if isinstance(entry, dict) and entry.get("codename") == codename:
            node_id = entry.get("node_id")
            return node_id if isinstance(node_id, str) else None
    return None


def _complete_again(repo: Path, node_id: str) -> list[str]:
    """Set ``node_id`` Complete in the resolved graph, then its rolled-up ancestors.

    The bookkeeping commit's own graph edit, applied to the integration
    branch's version after resolution took that version. A node the
    integration branch no longer has in its graph (archived, say) is left as
    it is. Project-relative chunk paths that changed.
    """
    chunk = find_chunk_path(repo, node_id)
    if chunk is None or chunk.suffix.lower() != ".json":
        return []
    nodes = load_json_chunk(chunk)
    node = next((n for n in nodes if n.get("id") == node_id), None)
    if node is None or node.get("status") == "Complete":
        return []
    node["status"] = "Complete"
    write_json_chunk(chunk, nodes)
    changed = [chunk.relative_to(repo.resolve()).as_posix()]
    changed += [rel for rel in complete_rolled_up_ancestors(repo, node_id) if rel not in changed]
    return changed


def resolve_graph(
    repo: Path, codename: str | None, paths: Sequence[str], bookkeeping: str | None
) -> list[str]:
    """Take HEAD's version of ``paths``, then apply ``bookkeeping``'s Complete again.

    Returns the project-relative paths to stage.

    ``bookkeeping`` is the sha :func:`branch_roadmap_edits` found, or ``None``
    when the branch has no bookkeeping commit (nothing to apply again).
    """
    if not paths:
        return []
    staged = take_integration_graph(repo, paths)
    node_id = _finished_node_id(repo, codename, bookkeeping) if bookkeeping else None
    if node_id is not None:
        staged.extend(p for p in _complete_again(repo, node_id) if p not in staged)
    return staged
