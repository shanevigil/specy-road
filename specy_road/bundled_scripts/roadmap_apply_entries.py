"""``apply`` change-file entries: each one turned into its command's parsed arguments.

Split from ``roadmap_crud_dependency_ops`` (file-limits cap), which runs the
parsed batch. Also :func:`id_map_lines`, the ``--dry-run`` id map.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from specy_road.bundled_scripts.roadmap_layout import natural_id_sort_key

APPLY_OPS = (
    "add-node", "edit-node", "add-dependency",
    "move-node", "group-nodes", "indent", "outdent", "remove-node", "archive",
)
# Restructure ops take only these fields, of the options their command has.
RESTRUCTURE_FIELDS = (
    "node", "nodes", "to_parent", "into_new", "title", "type", "id",
    "fill_gaps", "rewrite_refs",
)
# Node field names read naturally in a change file; the CLI flags are singular.
_OPTION_ALIASES = {"dependencies": "dependency", "touch_zones": "touch-zone"}
# Fields that fill a command's positionals, in order (default: ``node``).
_POSITIONALS = {"add-node": (), "add-dependency": ("node", "dependency"), "group-nodes": ("nodes",)}


def _flag(key: str) -> str:
    return "--" + _OPTION_ALIASES.get(key, key).replace("_", "-")


def _option_argv(flag: str, value: object) -> list[str]:
    if isinstance(value, bool):
        return [flag] if value else []
    if value is None:
        # ``parent_id: null`` / ``to_parent: null`` is the root; any other null
        # leaves the option unset.
        return [flag, "null"] if flag in ("--parent-id", "--to-parent") else []
    items = value if isinstance(value, list) else [value]
    return [part for item in items for part in (flag, str(item))]


def _command(op: str) -> tuple[argparse.ArgumentParser, list[str], set[str]]:
    """The parser ``op`` goes through, the argv prefix naming its subcommand, and its flags.

    ``move-node`` has a parser of its own with no subcommand; ``indent``,
    ``outdent`` and ``group-nodes`` share ``roadmap_outline_group``'s, and
    ``archive`` is ``archive_cli``'s. The rest are ``roadmap_crud``'s. The flags
    are the long options of the command itself, ``--help`` excepted.
    """
    if op == "move-node":
        from specy_road.bundled_scripts.roadmap_move_node import build_parser
    elif op in ("indent", "outdent", "group-nodes"):
        from specy_road.bundled_scripts.roadmap_outline_group import build_parser
    elif op == "archive":
        from specy_road.bundled_scripts.archive_cli import build_parser
    else:
        from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser
    parser = build_parser()
    prefix = [] if op == "move-node" else [op]
    cmd = parser
    if prefix:
        subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        cmd = subs.choices[op]
    flags = {s for s in cmd._option_string_actions if s.startswith("--")} - {"--help"}
    return parser, prefix, flags


def _positional_argv(op: str, rest: dict) -> list[str]:
    argv: list[str] = []
    for key in _POSITIONALS.get(op, ("node",)):
        value = rest.pop(key, None)
        if key == "nodes":
            if not isinstance(value, list) or not value:
                raise ValueError("group-nodes needs nodes: a list of sibling ids")
            argv += [str(x) for x in value]
        elif value in (None, ""):
            raise ValueError(f"{op} needs {key}:")
        else:
            argv.append(str(value))
    if op == "edit-node":
        sets = rest.pop("set", None)
        if not isinstance(sets, dict) or not sets:
            raise ValueError("edit-node needs set: a mapping of field: value")
        for k, v in sets.items():
            for item in v if isinstance(v, list) else [v]:
                argv += ["--set", f"{k}={'' if item is None else item}"]
    return argv


def _parse_entry(entry: object) -> object:
    """One change-file entry as its command's parsed arguments.

    One rule for every field after the positionals: its name must be a long
    option of the entry's own command (and, for the restructure ops, one of
    ``RESTRUCTURE_FIELDS``). It is checked by name before its value is turned
    into argv, so a ``false``, ``null`` or ``[]`` value, which adds no argv,
    cannot slip an unknown field past the parser. The parser then checks values.
    """
    if not isinstance(entry, dict) or entry.get("op") not in APPLY_OPS:
        raise ValueError(f"each change needs op: one of {', '.join(APPLY_OPS)}")
    op = entry["op"]
    parser, argv, flags = _command(op)
    rest = {k: v for k, v in entry.items() if k != "op"}
    argv = argv + _positional_argv(op, rest)
    restructure = APPLY_OPS.index(op) >= APPLY_OPS.index("move-node")
    fields = sorted(k for k in {f[2:].replace("-", "_") for f in flags} | set(_OPTION_ALIASES)
                    if _flag(k) in flags and (not restructure or k in RESTRUCTURE_FIELDS))
    for key, value in rest.items():
        if key not in fields:
            taken = ", ".join(fields) or "none"
            raise ValueError(f"not a valid {op}: no field {key!r} (its options: {taken})")
        argv += _option_argv(_flag(key), value)
    try:
        ns = parser.parse_args(argv)
    except SystemExit:
        raise ValueError(f"not a valid {op} (usage above)") from None
    ns.apply_op = op
    return ns


def parse_change_file(path: Path) -> list[object]:
    """Parse every entry before anything runs, so a malformed one changes nothing.

    Each entry goes through its own command's parser: a field the command
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
            out.append(_parse_entry(entry))
        except ValueError as e:
            raise ValueError(f"change {i}: {e}") from None
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
