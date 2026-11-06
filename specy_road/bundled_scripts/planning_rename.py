"""Rename flat planning ``.md`` when ``planning_dir`` path changes (e.g. codename edit).

Also rewrites prose id references after a renumber (``rename-refs`` and the
move commands' ``--rewrite-refs``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan


def rename_planning_file_if_path_changed(
    repo_root: Path,
    old_rel: str | None,
    new_rel: str | None,
) -> None:
    """If both paths are under ``planning/`` and differ, ``git mv``-style rename on disk."""
    if not old_rel or not new_rel:
        return
    try:
        o = normalize_planning_dir(old_rel.strip())
        n = normalize_planning_dir(new_rel.strip())
    except ValueError:
        return
    if o == n:
        return
    old_p = resolve_planning_path(repo_root, o)
    new_p = resolve_planning_path(repo_root, n)
    if not old_p.is_file():
        return
    new_p.parent.mkdir(parents=True, exist_ok=True)
    if new_p.exists() and new_p != old_p:
        return
    old_p.rename(new_p)


# --- Prose id references (M21.3) -------------------------------------------
#
# A move rewrites ids in chunks, sheet names, claims and touch-zone segments
# but never in prose, so sheets and acceptance text keep citing old ids that
# now name other nodes. ``rename-refs`` and the opt-in ``--rewrite-refs`` on
# the move commands rewrite them through the functions below. Automatic
# rewriting covers live nodes only: each node's planning sheet, title and
# acceptance; never docs/, CHANGELOG.md, work/, the generated roadmap.md or
# git history.

_FENCE = re.compile(r"^\s*`{3,}")
_HISTORICAL = re.compile(r"<!--\s*historical\s*-->.*?(?:<!--\s*/historical\s*-->|\Z)", re.S)


def _protected_spans(text: str) -> list[tuple[int, int]]:
    """Fenced blocks (fence line through the next fence line) and historical blocks.

    An unclosed fence or historical block runs to the end of the text.
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    start: int | None = None
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            if start is None:
                start = pos
            else:
                spans.append((start, pos + len(line)))
                start = None
        pos += len(line)
    if start is not None:
        spans.append((start, len(text)))
    spans.extend(m.span() for m in _HISTORICAL.finditer(text))
    return sorted(spans)


def rewrite_id_refs(text: str, id_map: dict[str, str]) -> tuple[str, int]:
    """Substitute every whole-id key of ``id_map`` in one pass; return (text, count).

    One pass over the original text, so swaps and chains are safe. A key
    matches only when the preceding character is absent or outside
    ``[A-Za-z0-9_.]`` and the next text is neither a digit nor ``.`` plus a
    digit: ``M16.1`` never matches ``M16.10`` or ``M16.1.2`` but does match
    ``M16.1_codename``. Fenced and historical blocks are left as they are.
    """
    renamed = {o: n for o, n in id_map.items() if o and o != n}
    if not renamed or not text:
        return text, 0
    keys = "|".join(re.escape(k) for k in sorted(renamed, key=len, reverse=True))
    pattern = re.compile(rf"(?<![A-Za-z0-9_.])(?:{keys})(?!\d|\.\d)")
    count = 0

    def sub(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return renamed[m.group(0)]

    out: list[str] = []
    pos = 0
    for start, end in _protected_spans(text):
        if end <= pos:
            continue
        start = max(start, pos)
        out.append(pattern.sub(sub, text[pos:start]))
        out.append(text[start:end])
        pos = end
    out.append(pattern.sub(sub, text[pos:]))
    return "".join(out), count


def _rewrite_node_strings(node: dict, id_map: dict[str, str]) -> int:
    """Rewrite ``title`` and each ``acceptance`` string in place; return the count."""
    count = 0
    title = node.get("title")
    if isinstance(title, str):
        node["title"], n = rewrite_id_refs(title, id_map)
        count += n
    acceptance = node.get("acceptance")
    if isinstance(acceptance, list):
        new: list = []
        for item in acceptance:
            if isinstance(item, str):
                item, n = rewrite_id_refs(item, id_map)
                count += n
            new.append(item)
        node["acceptance"] = new
    return count


def _sheet_text(plan: AtomicWritePlan, path: Path) -> str | None:
    """The sheet's text once the plan is written: staged text, else what is on disk."""
    if path in plan.pending:
        return plan.pending[path]
    if path in plan.deletions or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def stage_prose_refs(
    plan: AtomicWritePlan, root: Path, nodes: list[dict], id_map: dict[str, str]
) -> dict[str, int]:
    """Rewrite ids in every node's title, acceptance and planning sheet.

    Titles and acceptance are rewritten in ``nodes`` in place (the caller
    stages the chunks); changed sheets are staged into ``plan`` over any
    rename already staged there. Returns the count per sheet path and per
    ``<id> title/acceptance``, changed entries only.
    """
    counts: dict[str, int] = {}
    for node in nodes:
        n = _rewrite_node_strings(node, id_map)
        if n:
            counts[f"{node.get('id')} title/acceptance"] = n
        pd = node.get("planning_dir")
        if not isinstance(pd, str) or not pd.strip():
            continue
        try:
            path = resolve_planning_path(root, pd.strip())
        except ValueError:
            continue
        text = _sheet_text(plan, path)
        if text is None:
            continue
        new, n = rewrite_id_refs(text, id_map)
        if n:
            plan.stage_text(path, new)
            counts[normalize_planning_dir(pd.strip())] = n
    return counts


def _load_id_map(path: Path) -> dict[str, str]:
    """A JSON object of old id -> new id; anything else is a ``ValueError``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read id map {path}: {e}") from e
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and k and isinstance(v, str) and v for k, v in data.items()
    ):
        raise ValueError(
            f"id map {path} must be a JSON object of non-empty old id -> new id strings"
        )
    return data


def rename_refs(root: Path, id_map: dict[str, str], *, dry_run: bool = False) -> dict[str, int]:
    """Rewrite prose id references across live nodes in one validated transaction."""
    from specy_road.bundled_scripts.roadmap_crud_ops import run_validate_raise
    from specy_road.bundled_scripts.roadmap_id_rewrite_staging import _stage_merged_nodes
    from specy_road.bundled_scripts.roadmap_load import load_roadmap

    nodes = list(load_roadmap(root)["nodes"])
    plan = AtomicWritePlan(root)
    counts = stage_prose_refs(plan, root, nodes, id_map)
    if counts and not dry_run:
        _stage_merged_nodes(plan, root, nodes)
        plan.commit(lambda: run_validate_raise(root))
    return counts


def print_ref_counts(counts: dict[str, int]) -> None:
    """Print one line per changed sheet or node, then the total."""
    for label, n in sorted(counts.items()):
        print(f"  {label}: {n}")
    print(f"{sum(counts.values())} id reference(s) in {len(counts)} place(s)")


def add_rewrite_refs_arg(p: argparse.ArgumentParser) -> None:
    """``--rewrite-refs``, shared by move-node, indent, outdent and group-nodes."""
    p.add_argument(
        "--rewrite-refs",
        action="store_true",
        help=(
            "Also rewrite the changed ids where prose cites them: every live "
            "node's planning sheet, title and acceptance, as `rename-refs` does "
            "with this move's old -> new map, in the same transaction. Without "
            "it no prose changes."
        ),
    )


def print_rewrite_refs_note(rewrite_refs: bool) -> None:
    """Say where the id map was applied beyond chunks, sheets, claims and zones."""
    if rewrite_refs:
        print(
            "Prose id references (planning sheets, titles, acceptance) were "
            "rewritten with the same map (--rewrite-refs)."
        )
    else:
        print(
            "Prose citing the old ids was not changed; pass --rewrite-refs, or "
            "run `specy-road rename-refs`, to rewrite it."
        )


def main(argv: list[str] | None = None) -> None:
    from specy_road.bundled_scripts.roadmap_crud_ops import repo_root
    from specy_road.runtime_paths import add_repo_root_arg

    p = argparse.ArgumentParser(
        prog="specy-road rename-refs",
        description=(
            "Rewrite display ids cited in prose: each live node's planning sheet, "
            "title and acceptance. Every key of the map is replaced in one pass "
            "(swaps and chains are safe), as a whole id only: M16.1 never matches "
            "M16.10 or M16.1.2. Fenced code blocks and text between "
            "<!-- historical --> and <!-- /historical --> are left alone. docs/, "
            "CHANGELOG.md, work/, roadmap.md and git history are never touched."
        ),
    )
    p.add_argument("id_map", metavar="ID_MAP_JSON", help='JSON file: {"OLD_ID": "NEW_ID", ...}.')
    p.add_argument("--dry-run", action="store_true", help="Print the counts; write nothing.")
    add_repo_root_arg(p)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = repo_root(args)
    try:
        counts = rename_refs(root, _load_id_map(Path(args.id_map)), dry_run=args.dry_run)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    print_ref_counts(counts)
    if args.dry_run:
        print("(dry run: nothing written)")


if __name__ == "__main__":
    main()
