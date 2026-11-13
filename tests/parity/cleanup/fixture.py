"""One repo holding every case a cleanup command decides, each under a fixed item id.

| Item | What it is |
| --- | --- |
| ``merged-branch`` | ``feature/rm-merged`` (M1.2): own commit, merged with ``--no-ff``, pushed |
| ``unmerged-branch`` | ``feature/rm-unmerged`` (M1.4): own commit, not merged, pushed |
| ``complete-branch`` | ``feature/rm-done`` (M1.5, Complete): own commit, merged, pushed, no registry row |
| ``claimed-branch`` | ``feature/rm-thing`` (M1.1): a fresh claim, its tip the integration tip, pushed |
| ``live-worktree`` | ``work/.worktrees/thing`` on the claimed branch |
| ``merged-clean-worktree`` | ``work/.worktrees/merged`` on ``feature/rm-merged``, clean |
| ``merged-dirty-worktree`` | ``work/.worktrees/dirty`` on ``feature/rm-dirty`` (M1.3, merged, pushed), with an edit |
| ``row-no-branch`` | registry row ``ghost`` (M1.7, In Progress), its branch nowhere |
| ``row-complete`` | registry row ``settled`` (M1.6, Complete), its branch nowhere |
| ``toolkit-stash`` | a stash whose subject starts ``specy-road:`` |
| ``foreign-stash`` | a stash a person pushed |

A branch is two refs, local and on ``origin``; each ref is its own row (``merged-branch:local``,
``merged-branch:origin``). The dirty worktree's branch is ``merged-dirty-worktree:local`` and
``merged-dirty-worktree:origin``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

TOOLKIT_STASH = "specy-road: temp stash work/ around pickup"
FOREIGN_STASH = "mine"

#: Leaf id, codename and status of each node the fixture adds next to M1.1 ``thing``.
LEAVES = (
    ("M1.2", "merged", "In Progress"),
    ("M1.3", "dirty", "In Progress"),
    ("M1.4", "unmerged", "In Progress"),
    ("M1.5", "done", "Complete"),
    ("M1.6", "settled", "Complete"),
    ("M1.7", "ghost", "In Progress"),
)

#: Each branch ref and worktree, by item id.
BRANCH_ITEMS = {
    "merged-branch": "feature/rm-merged",
    "unmerged-branch": "feature/rm-unmerged",
    "complete-branch": "feature/rm-done",
    "claimed-branch": "feature/rm-thing",
    "merged-dirty-worktree": "feature/rm-dirty",
}
WORKTREE_ITEMS = {
    "live-worktree": "thing",
    "merged-clean-worktree": "merged",
    "merged-dirty-worktree": "dirty",
}
ROW_ITEMS = {"row-no-branch": "ghost", "row-complete": "settled"}
STASH_ITEMS = {"toolkit-stash": TOOLKIT_STASH, "foreign-stash": FOREIGN_STASH}

#: ``worktree prune <ID>`` runs once per fixture worktree.
WORKTREE_LEAVES = {"live-worktree": "M1.1", "merged-clean-worktree": "M1.2",
                   "merged-dirty-worktree": "M1.3"}


def _graph(repo: Path) -> None:
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text(encoding="utf-8"))
    for order, (node_id, codename, status) in enumerate(LEAVES, start=2):
        d = str(order)
        node = {**NODE, "id": node_id, "codename": codename, "status": status,
                "sibling_order": order, "node_key": f"{d * 8}-{d * 4}-5{d * 3}-8{d * 3}-{d * 12}"}
        node.pop("planning_dir")
        doc["nodes"].append(node)
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "graph")
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text(encoding="utf-8"))
    for item, codename in ROW_ITEMS.items():
        node_id = next(n for n, c, _s in LEAVES if c == codename)
        reg["entries"].append({"codename": codename, "node_id": node_id,
                               "branch": f"feature/rm-{codename}", "touch_zones": [item]})
    commit_file(repo, "roadmap/registry.yaml", yaml.safe_dump(reg), "claims")


def _branch(repo: Path, codename: str) -> None:
    git(repo, "checkout", "-q", "-b", f"feature/rm-{codename}", "dev")
    commit_file(repo, f"src/{codename}.py", f"{codename}\n", codename)
    git(repo, "checkout", "-q", "dev")


def build(tmp_path: Path) -> Path:
    """The fixture repo under ``tmp_path`` (its bare ``origin`` beside it); the main checkout on dev."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, ".gitignore", "work/\n", "ignore work/")
    commit_file(repo, "notes.md", "notes\n", "a tracked file to stash")
    _graph(repo)
    for codename in ("merged", "dirty", "unmerged", "done"):
        _branch(repo, codename)
    for codename in ("merged", "dirty", "done"):
        git(repo, "merge", "-q", "--no-ff", "--no-edit", f"feature/rm-{codename}")
    git(repo, "branch", "-q", "-f", "feature/rm-thing", "dev")   # a fresh claim
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "--all")
    git(repo, "fetch", "-q", "origin")
    for item, codename in WORKTREE_ITEMS.items():
        git(repo, "worktree", "add", "-q", str(repo / "work" / ".worktrees" / codename),
            f"feature/rm-{codename}")
    (repo / "work" / ".worktrees" / "dirty" / "src" / "dirty.py").write_text("edit\n", encoding="utf-8")
    for message in (TOOLKIT_STASH, FOREIGN_STASH):
        (repo / "notes.md").write_text(f"{message}\n", encoding="utf-8")
        git(repo, "stash", "push", "-q", "-m", message)
    return repo


def present(repo: Path) -> dict[str, bool]:
    """Whether each item's ref, worktree, registry row or stash still exists, by row id."""
    out: dict[str, bool] = {}
    refs = set(git(repo, "for-each-ref", "--format=%(refname)").splitlines())
    for item, branch in BRANCH_ITEMS.items():
        out[f"{item}:local"] = f"refs/heads/{branch}" in refs
        out[f"{item}:origin"] = bool(git(repo.parent / "remote.git", "for-each-ref",
                                         f"refs/heads/{branch}"))
    for item, codename in WORKTREE_ITEMS.items():
        out[item] = (repo / "work" / ".worktrees" / codename).is_dir()
    git(repo, "fetch", "-q", "origin")
    reg = yaml.safe_load(git(repo, "show", "origin/dev:roadmap/registry.yaml")) or {}
    codenames = {e.get("codename") for e in reg.get("entries") or []}
    for item, codename in ROW_ITEMS.items():
        out[item] = codename in codenames
    subjects = git(repo, "stash", "list", "--format=%gs")
    for item, message in STASH_ITEMS.items():
        out[item] = f": {message}" in subjects
    return out


def content_kept(repo: Path) -> bool:
    """The dirty worktree's edit is still there (an item a removal must never touch)."""
    path = repo / "work" / ".worktrees" / "dirty" / "src" / "dirty.py"
    return path.is_file() and path.read_text(encoding="utf-8") == "edit\n"


def row_of(text: str) -> str | None:
    """The row id a line of a command's output names, or ``None``."""
    for item, branch in BRANCH_ITEMS.items():
        if f"local     {branch}" in text or text.strip() == branch:
            return f"{item}:local"
        if f"origin    {branch}" in text:
            return f"{item}:origin"
    for item, codename in WORKTREE_ITEMS.items():
        if f"work/.worktrees/{codename}" in text:
            return item
    for item, codename in ROW_ITEMS.items():
        if text.lstrip().startswith(f"{codename} ") or text.lstrip().startswith(f"{codename}\t"):
            return item
    for item, message in STASH_ITEMS.items():
        if text.rstrip().endswith(f": {message}"):
            return item
    return None
