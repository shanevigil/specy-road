"""Paths named in a review packet that are missing at the reviewed commit."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road.bundled_scripts.generate_brief import _chain_sheet_paths
from specy_road.git_subprocess import git_ok, git_stdout
from specy_road.review_target import ReviewTarget

UNCOMMITTED_REF_NOTE = ("_The brief, a planning sheet or the implementation summary names these paths, but they "
                        "are not in the tree at the commit under review (untracked or uncommitted). Commit them "
                        "before reviewers start._")
_LINK = re.compile(r"\]\(\s*([^)\s#]+)")
_CODE = re.compile(r"`([^`\n]+)`")
_BRANCH = frozenset({"feature", "fix", "chore", "hotfix", "WIP", "release", "origin", "refs", "heads", "remotes"})
_TOP = frozenset({"roadmap", "planning", "shared", "work", "constitution", "constraints", "specy_road", "tests",
                  "docs", "src", "gui", "scripts", "schemas", "suggested_prompts", ".github", ".cursor", ".specyrd"})
_ROOT = frozenset({"README.md", "CHANGELOG.md", "pyproject.toml", "AGENTS.md", "CLAUDE.md", "roadmap.md",
                   "roadmap-context.md", ".gitignore", ".gitattributes"})


def _named_repo_path(token: str) -> str | None:
    raw = (token or "").strip().replace("\\", "/")
    if not raw or raw.startswith(("http://", "https://", "git@", "mailto:")):
        return None
    raw = raw.split()[0].split("?")[0]
    while raw.startswith("./") or raw.startswith("../"):
        raw = raw[2:] if raw.startswith("./") else raw[3:]
    raw = raw.lstrip("/").rstrip("/")
    if not raw or ".." in raw.split("/"):
        return None
    if "/" not in raw:
        return raw if raw in _ROOT else None
    head, last = raw.split("/", 1)[0], raw.rsplit("/", 1)[-1]
    if head in _BRANCH or head not in _TOP or not last or ("." not in last and last not in _ROOT):
        return None
    return raw


def _named_paths(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in _LINK.findall(text) + _CODE.findall(text):
        rel = _named_repo_path(token)
        if rel is not None and rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _show(root: Path, commit: str, rel: str) -> str | None:
    return git_stdout(["show", f"{commit}:./{rel}"], root)


def uncommitted_refs_section(root: Path, t: ReviewTarget, brief: str, node: dict, by_id: dict[str, dict],
                             computed: str) -> list[str]:
    out = ["## Uncommitted references", ""]
    if not t.commit:
        return out + ["_(cannot compute: no commit under review)_", ""]
    texts = [brief]
    srel = f"work/implementation-summary-{t.node_id}.md"
    summary = _show(root, t.commit, srel)
    if summary is None and (root / srel).is_file():
        summary = (root / srel).read_text(encoding="utf-8")
    if summary:
        texts.append(summary)
    for sheet in _chain_sheet_paths(node, root, by_id):
        rel = sheet.relative_to(root).as_posix()
        body = _show(root, t.commit, rel)
        if body is None and sheet.is_file():
            body = sheet.read_text(encoding="utf-8")
        if body:
            texts.append(body)
    missing: list[str] = []
    for text in texts:
        for rel in _named_paths(text):
            if rel not in missing and not git_ok(["cat-file", "-e", f"{t.commit}:./{rel}"], root)[0]:
                missing.append(rel)
    out += [computed, ""]
    if not missing:
        return out + ["_none_", ""]
    out += [UNCOMMITTED_REF_NOTE, ""]
    for rel in missing:
        out.append(f"- `{rel}`")
        print(f"warning: `{rel}` is named in the packet but not at commit `{t.commit}`", file=sys.stderr)
    return out + [""]
