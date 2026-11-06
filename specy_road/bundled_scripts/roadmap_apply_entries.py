"""``apply`` change-file entries: each one turned into its command's parsed arguments.

Split from ``roadmap_crud_dependency_ops`` (file-limits cap), which runs the
parsed batch. Also :func:`id_map_lines`, the ``--dry-run`` id map.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from specy_road.bundled_scripts.roadmap_layout import natural_id_sort_key

APPLY_OPS = (
    "add-node", "edit-node", "add-dependency",
    "move-node", "group-nodes", "indent", "outdent", "remove-node", "archive",
)
# Restructure ops take only these fields; each command's parser then refuses
# the ones it does not take (``to_parent`` on ``indent``, say).
RESTRUCTURE_FIELDS = (
    "node", "nodes", "to_parent", "into_new", "title", "type", "id",
    "fill_gaps", "rewrite_refs",
)
# Node field names read naturally in a change file; the CLI flags are singular.
_OPTION_ALIASES = {"dependencies": "dependency", "touch_zones": "touch-zone"}


def _option_argv(key: str, value: object) -> list[str]:
    flag = "--" + _OPTION_ALIASES.get(key, key).replace("_", "-")
    if isinstance(value, bool):
        return [flag] if value else []
    if value is None:
        # ``parent_id: null`` / ``to_parent: null`` is the root; any other null
        # leaves the option unset.
        return [flag, "null"] if flag in ("--parent-id", "--to-parent") else []
    items = value if isinstance(value, list) else [value]
    return [part for item in items for part in (flag, str(item))]


def _restructure_argv(op: str, rest: dict) -> list[str]:
    """Positionals and options for a move, group, removal or archive entry."""
    unknown = sorted(set(rest) - set(RESTRUCTURE_FIELDS))
    if unknown:
        raise ValueError(
            f"{op} does not take {', '.join(unknown)} "
            f"(fields: {', '.join(RESTRUCTURE_FIELDS)})"
        )
    if op == "group-nodes":
        ids = rest.pop("nodes", None)
        if not isinstance(ids, list) or not ids:
            raise ValueError("group-nodes needs nodes: a list of sibling ids")
        argv = [str(x) for x in ids]
    else:
        if rest.get("node") in (None, ""):
            raise ValueError(f"{op} needs node:")
        argv = [str(rest.pop("node"))]
    for k, v in rest.items():
        argv += _option_argv(k, v)
    return argv


def _crud_argv(op: str, rest: dict) -> list[str]:
    """Positionals and options for an ``add-node``, ``edit-node`` or ``add-dependency`` entry."""
    argv: list[str] = []
    if op != "add-node":
        positional = ["node"] + (["dependency"] if op == "add-dependency" else [])
        for key in positional:
            if rest.get(key) in (None, ""):
                raise ValueError(f"{op} needs {key}:")
            argv.append(str(rest.pop(key)))
    if op == "edit-node":
        sets = rest.pop("set", None)
        if not isinstance(sets, dict) or not sets:
            raise ValueError("edit-node needs set: a mapping of field: value")
        for k, v in sets.items():
            for item in v if isinstance(v, list) else [v]:
                argv += ["--set", f"{k}={'' if item is None else item}"]
    for k, v in rest.items():
        argv += _option_argv(k, v)
    return argv


def _entry_argv(entry: object) -> list[str]:
    """The command line one change-file entry stands for, subcommand first."""
    if not isinstance(entry, dict) or entry.get("op") not in APPLY_OPS:
        raise ValueError(f"each change needs op: one of {', '.join(APPLY_OPS)}")
    op = entry["op"]
    rest = {k: v for k, v in entry.items() if k != "op"}
    if APPLY_OPS.index(op) >= APPLY_OPS.index("move-node"):
        return [op, *_restructure_argv(op, rest)]
    return [op, *_crud_argv(op, rest)]


def _parse_entry(argv: list[str]) -> object:
    """``argv`` through the parser of the command it names.

    ``move-node`` has a parser of its own with no subcommand; ``indent``,
    ``outdent`` and ``group-nodes`` share ``roadmap_outline_group``'s, and
    ``archive`` is ``archive_cli``'s. The rest are ``roadmap_crud``'s.
    """
    op = argv[0]
    if op == "move-node":
        from specy_road.bundled_scripts.roadmap_move_node import build_parser

        ns = build_parser().parse_args(argv[1:])
    else:
        if op in ("indent", "outdent", "group-nodes"):
            from specy_road.bundled_scripts.roadmap_outline_group import build_parser
        elif op == "archive":
            from specy_road.bundled_scripts.archive_cli import build_parser
        else:
            from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser
        ns = build_parser().parse_args(argv)
    ns.apply_op = op
    return ns


def parse_change_file(path: Path) -> list[object]:
    """Parse every entry before anything runs, so a malformed one changes nothing.

    Each entry goes through its own command's parser: an option the command
    does not take, a bad ``type``, a missing ``title`` are refused here.
    """
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"cannot read {path}: {e}") from None
    entries = doc.get("changes") if isinstance(doc, dict) else doc
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}: expected a list of changes (or changes: [...])")
    out: list[object] = []
    for i, entry in enumerate(entries, 1):
        try:
            argv = _entry_argv(entry)
            out.append(_parse_entry(argv))
        except ValueError as e:
            raise ValueError(f"change {i}: {e}") from None
        except SystemExit:
            raise ValueError(f"change {i}: not a valid {argv[0]} (usage above)") from None
    return out


def id_map_lines(before: list[dict], after: list[dict]) -> list[str]:
    """``old -> new`` for each pre-batch node still present whose id changed.

    Composed by ``node_key`` from the graphs before and after the whole batch,
    so a node moved twice shows its first and last id, never a transient one.
    """
    final = {n.get("node_key"): n.get("id") for n in after}
    changed = [
        (n["id"], final[n.get("node_key")])
        for n in before
        if n.get("node_key") in final and final[n.get("node_key")] != n["id"]
    ]
    changed.sort(key=lambda pair: natural_id_sort_key(pair[0]))
    if not changed:
        return []
    return ["Display ids changed (old -> new):"] + [f"  {o} -> {n}" for o, n in changed]
