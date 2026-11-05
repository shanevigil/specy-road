"""Roadmap graph conflicts a landing resolves: the ones the branch only inherited.

``roadmap/manifest.json`` and the JSON chunks under ``roadmap/`` are authored,
not generated, so unlike the registry and the rendered files a conflict in them
is not resolved blindly. A branch whose changes there all came from earlier
merges of the integration branch -- plus finish's own bookkeeping commit -- has
nothing of its own to lose: each conflicted file takes the integration
branch's version, and the bookkeeping commit's one graph edit, the finished
leaf set to Complete (and the ancestors that rolled up with it), is applied
again on top, found by ``node_key`` because the integration branch may have
moved or renumbered it. Provenance comes from the branch's first-parent
history (:func:`branch_roadmap_edits`). A branch that authored an edit to a
conflicted graph file is refused with the files named; its edit is never
silently dropped. Merging two real roadmap edits, and the milestone-rollup
landing, are out of scope.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Sequence
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import (
    build_node_chunk_map,
    load_json_chunk,
    write_json_chunk,
)
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.git_subprocess import git_code, git_ok
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import project_prefix

#: Subject of finish-this-task's bookkeeping commit, by codename.
BOOKKEEPING_SUBJECT = "chore(rm-{codename}): complete, deregister"

#: git's empty tree: what a root commit is compared against.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

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


def _blob(repo: Path, rev: str, path: str) -> str | None:
    """The blob id of git-root-relative ``path`` at ``rev``; ``None`` when it is absent there."""
    ok, out = git_ok(["rev-parse", "-q", "--verify", f"{rev}:{path}"], repo)
    return out if ok else None


def _changed(repo: Path, old: str, new: str, paths: Sequence[str]) -> set[str]:
    """Which of ``paths`` differ between ``old`` and ``new``; all of them when git cannot say."""
    ok, out = git_ok(
        ["diff-tree", "-r", "--name-only", "--no-commit-id", old, new, "--",
         *(f":(top){p}" for p in paths)],
        repo,
    )
    return {line.strip() for line in out.splitlines()} & set(paths) if ok else set(paths)


def _authored_in(
    repo: Path, sha: str, parents: Sequence[str], paths: Sequence[str], integration: str
) -> set[str]:
    """Which of ``paths`` commit ``sha`` on the branch's first-parent line authored.

    An ordinary commit authors every path it changes. A merge authors a path
    it changes against its first parent unless the result -- blob or deletion
    -- matches an integration parent's (one ``integration`` contains): that
    content was inherited. Any other merge result is a hand-made resolution.
    """
    changed = _changed(repo, parents[0] if parents else _EMPTY_TREE, sha, paths)
    inherited_from = [
        p for p in parents[1:]
        if git_code(["merge-base", "--is-ancestor", p, integration], repo)[0] == 0
    ]
    return {
        path for path in changed
        if not any(_blob(repo, sha, path) == _blob(repo, p, path) for p in inherited_from)
    }


def branch_roadmap_edits(
    repo: Path, paths: Sequence[str], *, codename: str | None,
    tip: str = "MERGE_HEAD", integration: str = "HEAD",
) -> tuple[list[str], str | None]:
    """Which of ``paths`` the branch authored, and this run's bookkeeping commit.

    Walks the branch's first-parent history from where it left ``integration``
    (:func:`_authored_in` classifies each commit). The tip, when it is
    finish's bookkeeping commit for ``codename``, is set aside first: its
    status edits are finish's, not the branch's, and are applied again after
    resolution. When git cannot list the history, every path counts as
    authored, so nothing is dropped. Paths are git-root-relative. Returns
    ``(authored paths, bookkeeping sha or None)``.
    """
    ok, out = git_ok(
        ["log", "--first-parent", "--format=%H %P%x01%s", f"{integration}..{tip}"], repo
    )
    if not ok:
        return list(paths), None
    commits = [line.partition("\x01") for line in out.splitlines() if line.strip()]
    bookkeeping: str | None = None
    if codename and commits and commits[0][2] == BOOKKEEPING_SUBJECT.format(codename=codename):
        bookkeeping = commits.pop(0)[0].split()[0]
    authored: set[str] = set()
    for shas, _, _subject in commits:
        sha, *parents = shas.split()
        authored |= _authored_in(repo, sha, parents, paths, integration)
    return [p for p in paths if p in authored], bookkeeping


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


def _finished_node_key(repo: Path, codename: str | None, bookkeeping: str) -> str | None:
    """The ``node_key`` of the node ``bookkeeping`` completed, or ``None`` when it cannot be found.

    The node id is ``codename``'s row in the registry the bookkeeping commit
    removed; the key comes from the graph file the commit wrote that node to.
    The key, not the id, names the node again: the integration branch may have
    moved or renumbered it.
    """
    doc = read_registry_at_ref(repo, f"{bookkeeping}^", _REF_READ_TIMEOUT) or {}
    rows = [e for e in doc.get("entries") or [] if isinstance(e, dict)]
    node_id = next((e.get("node_id") for e in rows if e.get("codename") == codename), None)
    if not isinstance(node_id, str):
        return None
    for path in _changed_graph_paths(repo, bookkeeping):
        ok, text = git_ok(["show", f"{bookkeeping}:{path}"], repo)
        node = next((n for n in _nodes_in(text) if n.get("id") == node_id), None) if ok else None
        if node is not None and isinstance(node.get("node_key"), str):
            return node["node_key"]
    return None


def _changed_graph_paths(repo: Path, commit: str) -> list[str]:
    """Git-root-relative roadmap graph paths ``commit`` changed against its first parent."""
    prefix = project_prefix(repo)
    ok, out = git_ok(
        ["diff-tree", "-r", "--name-only", "--no-commit-id", f"{commit}^", commit], repo
    )
    names = [line.strip() for line in out.splitlines()] if ok else []
    return [n for n in names if n.startswith(prefix) and is_roadmap_graph_path(n[len(prefix):])]


def _nodes_in(text: str) -> list[dict]:
    """The node objects in a chunk's JSON text; ``[]`` when it is not a chunk."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    nodes = data.get("nodes") if isinstance(data, dict) else data
    return [n for n in nodes if isinstance(n, dict)] if isinstance(nodes, list) else []


def _complete_again(repo: Path, node_key: str) -> list[str]:
    """Set the node keyed ``node_key`` Complete in the resolved graph; recompute its ancestors.

    The bookkeeping commit's own graph edit, applied to the integration
    branch's version after resolution took that version. A node the
    integration branch no longer has in its graph (archived, say) is left as
    it is. Project-relative chunk paths that changed.
    """
    for chunk in sorted(set(build_node_chunk_map(repo).values())):
        nodes = load_json_chunk(chunk)
        node = next((n for n in nodes if n.get("node_key") == node_key), None)
        if node is None:
            continue
        if node.get("status") == "Complete":
            return []
        node["status"] = "Complete"
        write_json_chunk(chunk, nodes)
        changed = [chunk.relative_to(repo.resolve()).as_posix()]
        ancestors = complete_rolled_up_ancestors(repo, node["id"])
        return changed + [rel for rel in ancestors if rel not in changed]
    return []


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
    node_key = _finished_node_key(repo, codename, bookkeeping) if bookkeeping else None
    if node_key is not None:
        staged.extend(p for p in _complete_again(repo, node_key) if p not in staged)
    return staged
