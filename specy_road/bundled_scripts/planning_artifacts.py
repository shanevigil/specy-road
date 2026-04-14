"""Planning markdown: one feature sheet per roadmap node (flat ``planning/*.md``).

``planning_dir`` on each node that requires planning is a repo-relative path to a single
``.md`` file under ``planning/``. Filename pattern: ``<id>_<codename_slug>_<node_key>.md``.
See ``planning/README.md`` in the project.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_UNSAFE_PLANNING_DIR = re.compile(r"\.\.|^/|\\\\|^\\")

# planning/M1.1_my-feature_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.md
PLANNING_FILENAME_RE = re.compile(
    r"^(?P<id>M[0-9]+(?:\.[0-9]+)*)_"
    r"(?P<slug>unnamed|[a-z0-9]+(?:-[a-z0-9]+)*)_"
    r"(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"\.md$",
    re.IGNORECASE,
)


def normalize_planning_dir(raw: str) -> str:
    """
    Return a repo-relative POSIX path (no leading/trailing slashes, no ``..``).

    Used for ``planning_dir`` (path to a single ``.md`` file under ``planning/``).

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


def resolve_planning_path(repo_root: Path, planning_dir: str) -> Path:
    """Resolve normalized planning_dir (file path); must stay under repo_root."""
    root = repo_root.resolve()
    rel = normalize_planning_dir(planning_dir)
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as e:
        raise ValueError(f"planning_dir {planning_dir!r} escapes repository root") from e
    return path


def resolve_planning_dir(repo_root: Path, planning_dir: str) -> Path:
    """Backward-compatible alias: ``planning_dir`` is now a file path."""
    return resolve_planning_path(repo_root, planning_dir)


def codename_to_slug(codename: str | None) -> str:
    """Filesystem-friendly slug from milestone/phase codename; ``unnamed`` if missing."""
    if not codename or not str(codename).strip():
        return "unnamed"
    s = str(codename).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s if s else "unnamed"


def planning_filename_for_node(n: dict) -> str:
    """Canonical filename: ``<id>_<slug>_<node_key>.md`` (node_key lowercased)."""
    nid = n["id"]
    slug = codename_to_slug(n.get("codename"))
    nk = str(n["node_key"]).strip().lower()
    return f"{nid}_{slug}_{nk}.md"


def expected_planning_rel(n: dict) -> str:
    """Repo-relative path ``planning/<filename>`` for a node."""
    return f"planning/{planning_filename_for_node(n)}"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """
    Parse a leading YAML frontmatter block (``---`` … ``---``).

    Returns ``({}, body)`` if no valid frontmatter.
    Identity for validation remains filename + roadmap JSON; frontmatter is optional and not checked.
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


def ancestor_chain_ids(node_id: str, by_id: dict[str, dict]) -> list[str]:
    """Root-to-parent order of ids walking ``parent_id`` (excludes ``node_id``)."""
    chain: list[str] = []
    cur = by_id.get(node_id)
    if not cur:
        return chain
    pid = cur.get("parent_id")
    while pid is not None:
        chain.append(pid)
        cur = by_id.get(pid)
        if not cur:
            break
        pid = cur.get("parent_id")
    return list(reversed(chain))


def ancestor_planning_paths(
    node_id: str,
    by_id: dict[str, dict],
    repo_root: Path,
) -> list[tuple[str, Path]]:
    """
    Ordered list of (repo-relative path, absolute Path) for ancestors that have
    ``planning_dir`` set. Vision → phase → … → immediate parent.
    """
    out: list[tuple[str, Path]] = []
    for aid in ancestor_chain_ids(node_id, by_id):
        an = by_id.get(aid)
        if not an:
            continue
        pd = an.get("planning_dir")
        if not isinstance(pd, str) or not pd.strip():
            continue
        try:
            norm = normalize_planning_dir(pd.strip())
            p = resolve_planning_path(repo_root, norm)
        except ValueError:
            continue
        out.append((norm, p))
    return out


def _append_orphan_planning_files(
    root: Path,
    referenced_paths: set[str],
    errors: list[str],
) -> None:
    planning_root = root / "planning"
    if not planning_root.is_dir():
        return
    for p in sorted(planning_root.iterdir()):
        if p.name.startswith("."):
            continue
        if p.is_dir():
            errors.append(
                f"roadmap: planning subdirectory not allowed: "
                f"{p.relative_to(root)} (use flat planning/*.md only)",
            )
    for md in sorted(planning_root.rglob("*.md")):
        if md.name.lower() == "readme.md":
            continue
        try:
            rel = str(md.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        if md.parent != planning_root:
            errors.append(
                f"roadmap: nested planning markdown not allowed: {rel} "
                f"(use only flat planning/*.md)",
            )
            continue
        if rel not in referenced_paths:
            errors.append(
                f"roadmap: orphan planning file {rel}: "
                f"no node has planning_dir {rel!r}",
            )


def _append_planning_filename_errors(n: dict, abs_path: Path, errors: list[str]) -> None:
    """Identity is encoded in the filename; body may be plain Markdown (no YAML required)."""
    fname = abs_path.name
    if not PLANNING_FILENAME_RE.match(fname):
        errors.append(
            f"roadmap: node {n['id']}: planning file name must match "
            f"<id>_<codename_slug>_<node_key>.md, got {fname!r}",
        )
        return
    exp = planning_filename_for_node(n)
    if fname != exp:
        errors.append(
            f"roadmap: node {n['id']}: planning file should be named {exp!r}, got {fname!r}",
        )


def _process_node_planning_dir(
    n: dict,
    repo_root: Path,
    root: Path,
    by_id: dict[str, dict],
    planning_dirs: dict[str, str],
    errors: list[str],
) -> None:
    _ = (by_id,)  # reserved for future cross-node checks
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
    if not norm.startswith("planning/"):
        errors.append(
            f"roadmap: node {n['id']}: planning_dir must be under planning/, got {norm!r}",
        )
        return
    if not norm.endswith(".md"):
        errors.append(
            f"roadmap: node {n['id']}: planning_dir must end with .md, got {norm!r}",
        )
        return
    try:
        abs_path = resolve_planning_path(repo_root, norm)
    except ValueError as e:
        errors.append(f"roadmap: node {n['id']}: {e}")
        return
    if abs_path.is_dir():
        errors.append(
            f"roadmap: node {n['id']}: planning_dir must be a file, not a directory: {norm}",
        )
        return
    if not abs_path.is_file():
        errors.append(
            f"roadmap: node {n['id']}: planning file missing: {norm}",
        )
        return
    _append_planning_filename_errors(n, abs_path, errors)


def collect_planning_artifact_errors(repo_root: Path, nodes: list[dict]) -> list[str]:
    """
    Return fatal validation messages for ``planning_dir`` files and ``planning/`` hygiene.
    """
    errors: list[str] = []
    by_id = {n["id"]: n for n in nodes}
    root = repo_root.resolve()
    planning_dirs: dict[str, str] = {}
    for n in nodes:
        _process_node_planning_dir(n, repo_root, root, by_id, planning_dirs, errors)
    referenced = set(planning_dirs.keys())
    _append_orphan_planning_files(root, referenced, errors)
    return errors


def planning_artifact_paths(repo_root: Path, planning_dir_norm: str) -> dict[str, Path]:
    """
    Resolved paths for the PM API: single feature sheet file.

    Keys ``overview`` / ``plan`` / ``tasks_md`` duplicate ``sheet`` for older UI clients.
    """
    p = resolve_planning_path(repo_root, planning_dir_norm)
    return {
        "dir": p.parent,
        "sheet": p,
        "overview": p,
        "plan": p,
        "tasks_md": p,
        "tasks_dir": p.parent,
    }
