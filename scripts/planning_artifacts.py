"""Optional planning markdown under per-node ``planning_dir`` (hybrid roadmap).

Validates ``overview.md`` / ``plan.md``, optional ``tasks.md``, and ``tasks/**/*.md``
frontmatter. See ``planning/README.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_UNSAFE_PLANNING_DIR = re.compile(r"\.\.|^/|\\\\|^\\")


def normalize_planning_dir(raw: str) -> str:
    """
    Return a repo-relative POSIX path (no leading/trailing slashes, no ``..``).

    Raises:
        ValueError: if empty, unsafe, or absolute-looking.
    """
    s = (raw or "").strip().replace("\\", "/").strip("/")
    if not s:
        raise ValueError("planning_dir must be non-empty when set")
    if _UNSAFE_PLANNING_DIR.search(raw.strip()) or s.startswith("/"):
        raise ValueError(f"planning_dir must be a relative repo path, got {raw!r}")
    for part in s.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"invalid planning_dir segment in {raw!r}")
    return s


def resolve_planning_dir(repo_root: Path, planning_dir: str) -> Path:
    """Resolve normalized planning_dir; must stay under repo_root."""
    root = repo_root.resolve()
    rel = normalize_planning_dir(planning_dir)
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as e:
        raise ValueError(f"planning_dir {planning_dir!r} escapes repository root") from e
    return path


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """
    Parse a leading YAML frontmatter block (``---`` … ``---``).

    Returns ``({}, body)`` if no valid frontmatter.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    if not block.strip():
        return {}, body
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(block)
    except Exception:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, body


def _owner_allows_node_id(owner_id: str, task_nid: str) -> bool:
    return task_nid == owner_id or task_nid.startswith(owner_id + ".")


def _append_tasks_md_frontmatter_errors(
    tasks_md: Path,
    owner_id: str,
    root: Path,
    by_id: dict[str, dict],
    errors: list[str],
) -> None:
    fm, _ = split_frontmatter(tasks_md.read_text(encoding="utf-8"))
    fm_nid = fm.get("node_id")
    if not fm_nid:
        errors.append(
            f"roadmap: {tasks_md.relative_to(root)}: "
            "YAML frontmatter must set node_id (owner roadmap id)",
        )
        return
    tid = str(fm_nid).strip()
    if tid not in by_id:
        errors.append(
            f"roadmap: {tasks_md.relative_to(root)}: unknown node_id {tid!r}",
        )
    elif not _owner_allows_node_id(owner_id, tid):
        errors.append(
            f"roadmap: {tasks_md.relative_to(root)}: "
            f"node_id {tid!r} must equal {owner_id!r} or be a descendant id",
        )


def _append_tasks_subdir_errors(
    tasks_sub: Path,
    owner_id: str,
    root: Path,
    by_id: dict[str, dict],
    errors: list[str],
) -> None:
    for md in sorted(tasks_sub.rglob("*.md")):
        fm, _ = split_frontmatter(md.read_text(encoding="utf-8"))
        rel = md.relative_to(root)
        tnid = fm.get("node_id")
        if not tnid:
            errors.append(f"roadmap: {rel}: YAML frontmatter must set node_id")
            continue
        ts = str(tnid).strip()
        if ts not in by_id:
            errors.append(f"roadmap: {rel}: unknown node_id {ts!r}")
            continue
        if not _owner_allows_node_id(owner_id, ts):
            errors.append(
                f"roadmap: {rel}: node_id {ts!r} must be "
                f"{owner_id!r} or a descendant (prefix {owner_id!r}.)",
            )


def _append_orphan_planning_task_errors(
    root: Path,
    planning_dirs: dict[str, str],
    errors: list[str],
) -> None:
    planning_root = root / "planning"
    if not planning_root.is_dir():
        return
    for md in sorted(planning_root.rglob("*.md")):
        try:
            rel_sp = md.relative_to(planning_root)
        except ValueError:
            continue
        parts = rel_sp.parts
        if "tasks" not in parts:
            continue
        t_idx = parts.index("tasks")
        if t_idx >= len(parts) - 1:
            continue
        plan_parts = Path("planning").parts + rel_sp.parts[:t_idx]
        plan_rel = "/".join(plan_parts)
        if plan_rel not in planning_dirs:
            errors.append(
                f"roadmap: orphan task markdown {md.relative_to(root)}: "
                f"no node declares planning_dir {plan_rel!r}",
            )


def _process_node_planning_dir(
    n: dict,
    repo_root: Path,
    root: Path,
    by_id: dict[str, dict],
    planning_dirs: dict[str, str],
    errors: list[str],
) -> None:
    pd = n.get("planning_dir")
    if not pd:
        return
    if not isinstance(pd, str) or not str(pd).strip():
        errors.append(
            f"roadmap: node {n['id']}: planning_dir must be a string when set",
        )
        return
    try:
        norm = normalize_planning_dir(str(pd).strip())
    except ValueError as e:
        errors.append(f"roadmap: node {n['id']}: {e}")
        return
    if norm in planning_dirs:
        errors.append(
            f"roadmap: duplicate planning_dir {norm!r} on {planning_dirs[norm]} and {n['id']}",
        )
        return
    planning_dirs[norm] = n["id"]
    try:
        abs_dir = resolve_planning_dir(repo_root, norm)
    except ValueError as e:
        errors.append(f"roadmap: node {n['id']}: {e}")
        return
    if not abs_dir.is_dir():
        errors.append(
            f"roadmap: node {n['id']}: planning_dir is not a directory: {norm}",
        )
        return
    for name in ("overview.md", "plan.md"):
        p = abs_dir / name
        if not p.is_file():
            errors.append(f"roadmap: node {n['id']}: missing {name} under {norm}/")
    tasks_md = abs_dir / "tasks.md"
    if tasks_md.is_file():
        _append_tasks_md_frontmatter_errors(tasks_md, n["id"], root, by_id, errors)
    tasks_sub = abs_dir / "tasks"
    if tasks_sub.is_dir():
        _append_tasks_subdir_errors(tasks_sub, n["id"], root, by_id, errors)


def collect_planning_artifact_errors(repo_root: Path, nodes: list[dict]) -> list[str]:
    """
    Return fatal validation messages for ``planning_dir`` trees and global ``planning/`` hygiene.
    """
    errors: list[str] = []
    by_id = {n["id"]: n for n in nodes}
    root = repo_root.resolve()
    planning_dirs: dict[str, str] = {}
    for n in nodes:
        _process_node_planning_dir(n, repo_root, root, by_id, planning_dirs, errors)
    _append_orphan_planning_task_errors(root, planning_dirs, errors)
    return errors


def collect_planning_artifact_warnings(repo_root: Path, nodes: list[dict]) -> list[str]:
    """Non-fatal hints (currently unused; reserved for future checks)."""
    _ = (repo_root, nodes)
    return []


def planning_artifact_paths(repo_root: Path, planning_dir_norm: str) -> dict[str, Path]:
    """Resolved paths for the standard artifact filenames under planning_dir."""
    base = resolve_planning_dir(repo_root, planning_dir_norm)
    return {
        "dir": base,
        "overview": base / "overview.md",
        "plan": base / "plan.md",
        "tasks_md": base / "tasks.md",
        "tasks_dir": base / "tasks",
    }
