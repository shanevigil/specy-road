#!/usr/bin/env python3
"""Validate merged roadmap graph (manifest + chunks) and registry.yaml."""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from pathlib import Path

import yaml

from specy_road import __version__
from specy_road.bundled_scripts.refresh_schemas import warn_if_schemas_stale
from specy_road.bundled_scripts.refresh_stubs import MANIFEST_REL, warn_if_stubs_stale
from specy_road.bundled_scripts.roadmap_chunk_utils import discover_manifest_path, load_manifest_mapping
from specy_road.bundled_scripts.roadmap_load import load_roadmap, validate_roadmap_line_limits
from specy_road.registry_yaml import registry_path
from specy_road.agents_md_block import warn_if_agents_md_block_stale, warn_missing_load_order_paths
from specy_road.cli import REPLACED_COMMANDS, _known_commands
from specy_road.generated_files import warn_if_generated_files_ignored
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.managed_block import HTML_COMMENT
from specy_road.orchestration_config import load_orchestration_config
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root, git_root
from specy_road.specyrd_cli import _build_parser as _specyrd_parser
from specy_road.specyrd_init import _load_manifest
from specy_road.bundled_scripts.validate_roadmap_checks import (
    cycle_check,
    load_schema,
    run_validation,
    validate_schema,
    validate_codenames,
    validate_required_planning_dirs,
    validate_unique_title_slugs,
    validate_unique_titles,
    warn_stale_parent_status,
    warn_touch_zones_match_nothing,
)
from specy_road.bundled_scripts.validate_roadmap_gates import validate_gates
from specy_road.bundled_scripts.validate_self_heal import auto_heal_roadmap

__all__ = [
    "cycle_check",
    "pinned_version",
    "run_validation",
    "validate_at",
    "validate_codenames",
    "validate_gates",
    "validate_required_planning_dirs",
    "validate_unique_title_slugs",
    "validate_unique_titles",
    "unregistered_commands",
    "warn_stale_parent_status",
    "warn_if_pin_differs",
    "warn_touch_zones_match_nothing",
    "warn_unregistered_commands",
]


_REQUIREMENT_PIN = re.compile(r"^\s*specy[-_.]road\s*(?:\[[^\]]*\])?\s*==\s*([^\s;#,]+)", re.IGNORECASE)


def pinned_version(start: Path) -> tuple[str, str] | None:
    """``(version, where declared)`` for the specy-road this checkout pins, or None.

    A ``pin`` in ``.specyrd/manifest.json`` wins; otherwise the first
    ``specy-road==`` line in a ``requirements*.txt`` at the checkout root.
    """
    checkout = git_root(start) or start
    pin = _load_manifest(checkout).get("pin")
    if isinstance(pin, str) and pin.strip():
        return pin.strip(), str(MANIFEST_REL)
    for req in sorted(checkout.glob("requirements*.txt")):
        try:
            lines = req.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            m = _REQUIREMENT_PIN.match(line)
            if m:
                return m.group(1), req.name
    return None


def warn_if_pin_differs(start: Path) -> None:
    """One non-fatal line when the running specy-road is not the version the repo pins."""
    found = pinned_version(start)
    if found is None or found[0] == __version__:
        return
    pin, where = found
    print(
        f"specy-road: warning — this repo pins specy-road {pin} ({where}) but {__version__} "
        f"is running. If the upgrade is deliberate, update the pin; otherwise install {pin}.",
        file=sys.stderr,
    )


_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")
_MENTION = re.compile(r"(?<![\w/.-])(specy-road|specyrd)[ \t]+([a-z][a-z0-9-]*)")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# The product name is a noun phrase when one of these words is the last word
# before it on the line ("the specy-road toolkit", "other specy-road formats").
_NOUN_PHRASE = frozenset({
    "the", "a", "an", "this", "that", "these", "those", "other", "any", "all",
    "every", "each", "its", "our", "your", "their", "own", "of", "with", "in",
    "for", "from", "about",
})
_RUN_VERB = frozenset({"run", "exec", "execute", "invoke", "uvx"})


def _preceding_words(text: str, start: int) -> list[str]:
    before = text[:start].rstrip(" \t*_`\"'()[]{}<>|:—–-")
    return [word.lower() for word in re.findall(r"[A-Za-z]+", before)[-2:]]


def _command_led_list_item(line: str, start: int) -> bool:
    """A list item whose command is the first token, or sits after only a run verb.

    Emphasis and backticks around that token do not count. A prose bullet that
    mentions the product later in the sentence is not command-led.
    """
    mark = _LIST_ITEM.match(line)
    if mark is None or start < mark.end():
        return False
    words = re.findall(r"[A-Za-z]+", re.sub(r"[*_`]+", " ", line[mark.end():start]))
    return not words or (len(words) == 1 and words[0].lower() in _RUN_VERB)


def _run_verb(line: str, start: int) -> bool:
    words = _preceding_words(line, start)
    immediate = words[-1] if words else ""
    earlier = words[-2] if len(words) > 1 else ""
    return immediate in _RUN_VERB or (earlier in _RUN_VERB and immediate in _NOUN_PHRASE)


def _noun_phrase(line: str, start: int) -> bool:
    words = _preceding_words(line, start)
    return bool(words) and words[-1] in _NOUN_PHRASE


def _next_token(line: str, start: int) -> str:
    match = _MENTION.match(line, start)
    found = re.match(r"[ \t]*(\S+)", line[match.end():])
    return "" if found is None else found.group(1)


def _mandatory_follower(line: str, start: int) -> bool:
    """True for a flag, path, quote, id, or the word command/subcommand."""
    raw = _next_token(line, start)
    if not raw:
        return False
    if raw[0] in "\"'":
        return True
    if re.match(r"-{1,2}[A-Za-z0-9]", raw):
        return True
    word = raw.rstrip(".,;:!?)]")
    if word.lower() in {"command", "subcommand"}:
        return True
    if "/" in word or word.startswith(".") or re.search(r"\.[A-Za-z]", word):
        return True
    return bool(re.search(r"\d", word))


def _reports(line: str, start: int) -> bool:
    """Mandatory contexts first. A noun phrase is the only exclusion."""
    if _command_led_list_item(line, start) or _run_verb(line, start) or _mandatory_follower(line, start):
        return True
    if _noun_phrase(line, start):
        return False
    return True


def _backtick_run(line: str, index: int) -> int:
    end = index
    while end < len(line) and line[end] == "`":
        end += 1
    return end


def _code_spans(line: str) -> list[tuple[int, int, str]]:
    """CommonMark code spans: a run of N backticks closed by the next run of N.

    A run of a different length does not close the span, so one backtick inside
    a double-backtick span stays inside it.
    """
    spans: list[tuple[int, int, str]] = []
    index = 0
    length = len(line)
    while index < length:
        if line[index] != "`":
            index += 1
            continue
        opener_end = _backtick_run(line, index)
        width = opener_end - index
        cursor = opener_end
        closer: tuple[int, int] | None = None
        while cursor < length:
            if line[cursor] != "`":
                cursor += 1
                continue
            run_end = _backtick_run(line, cursor)
            if run_end - cursor == width:
                closer = (cursor, run_end)
                break
            cursor = run_end
        if closer is None:
            index = opener_end
            continue
        close_at, close_end = closer
        spans.append((index, close_end, line[opener_end:close_at]))
        index = close_end
    return spans


def _command_mentions(lines: list[tuple[int, str]]):
    """``(line, tool, name)`` for each command-shaped token the rule keeps."""
    in_fence = False
    for lineno, line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            for tool, name in _MENTION.findall(line):
                yield lineno, tool, name
            continue
        spans = _code_spans(line)
        chars = list(line)
        for start, end, content in spans:
            for tool, name in _MENTION.findall(content):
                yield lineno, tool, name
            chars[start:end] = " " * (end - start)
        plain = "".join(chars)
        for match in _MENTION.finditer(plain):
            if _reports(plain, match.start()):
                yield lineno, match.group(1), match.group(2)


def _registered_names() -> dict[str, set[str]]:
    specyrd = next(a for a in _specyrd_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return {"specy-road": {*_known_commands(), "version"}, "specyrd": set(specyrd.choices)}


def _occurrences(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    registered = _registered_names()
    found: list[tuple[int, str]] = []
    for lineno, tool, name in _command_mentions(lines):
        if name not in registered[tool]:
            found.append((lineno, f"{tool} {name}"))
    return found


def _lines_outside_block(text: str) -> list[tuple[int, str]]:
    """File lines that are not inside the managed block, with their file line numbers."""
    start = text.find(HTML_COMMENT.start)
    if start < 0:
        stop = -1
    else:
        end = text.find(HTML_COMMENT.end, start)
        stop = len(text) if end < 0 else end + len(HTML_COMMENT.end)
    kept: list[tuple[int, str]] = []
    offset = 0
    for number, raw in enumerate(text.splitlines(keepends=True), 1):
        line_end = offset + len(raw)
        inside = start >= 0 and offset < stop and line_end > start
        if not inside:
            kept.append((number, raw.rstrip("\r\n")))
        offset = line_end
    return kept


def unregistered_commands(text: str) -> list[str]:
    """Each ``specy-road <name>`` / ``specyrd <name>`` that Markdown ``text`` names and no CLI registers, in order.

    Every occurrence is returned. The same token on two lines is two entries
    (``specy-road frob`` twice). A registered command is never returned
    (``specy-road validate --strict``).

    Mandatory contexts are decided first and win over a noun phrase: a code
    span (a run of N backticks, N >= 1, closed by the next run of exactly N;
    ``the specy-road frob`` and ```the specy-road frob``` warn, and one
    backtick inside a longer span does not end it), a fenced block, a command-led list item (the product name is the
    first token after the marker, optionally in code or emphasis, or it is
    preceded only by a run verb: ``- specy-road frob --x``, ``- Run specy-road
    frob``), a run verb (run, exec, execute, invoke, uvx), and a token followed
    by a flag, a path, a quoted argument, an id-like argument, or the word
    command or subcommand (``## the specy-road frob --x``, ``Use the specy-road
    frob M1.2.``, ``Use the specy-road frob command.``). A heading is not
    special (``# Please specy-road frob`` warns). The only exclusion is a noun
    phrase: the product name preceded on the same line (ignoring whitespace)
    by a determiner, possessive, or preposition — the, a, an, this, that,
    these, those, other, any, all, every, each, its, our, your, their, own,
    of, with, in, for, from, about — when the token is followed by a plain
    word or nothing (``the specy-road toolkit is``, ``other specy-road
    formats``, and a prose bullet such as ``- **Adoption prompts** are kept
    aligned with other specy-road formats``).
    """
    return [mention for _, mention in _occurrences(list(enumerate(text.splitlines(), 1)))]


def warn_unregistered_commands(root: Path) -> None:
    """One non-fatal line per occurrence ``AGENTS.md`` / ``CLAUDE.md`` names, with that file's line number.

    Repeated names are not collapsed. The managed block is skipped:
    ``warn_if_agents_md_block_stale`` already reports one written by another
    version.
    """
    root = root.resolve()
    checkout = git_root(root) or root
    paths = dict.fromkeys(base / name for base in (root, checkout) for name in ("AGENTS.md", "CLAUDE.md"))
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(checkout)
        for lineno, mention in _occurrences(_lines_outside_block(text)):
            replacement = REPLACED_COMMANDS.get(mention)
            advice = (f"use `{replacement}`" if replacement
                      else "it was removed and nothing replaces it" if replacement == ""
                      else f"see `{mention.split()[0]} --help`")
            print(f"agents: warning — {rel}:{lineno} tells agents to run `{mention}`, which is not a "
                  f"command in specy-road {__version__}; {advice}.", file=sys.stderr)


def validate_git_workflow_contract(root: Path) -> None:
    """Validate ``roadmap/git-workflow.yaml`` if present.

    F-005: do NOT warn about missing remote-tracking refs for the
    integration branch. specy-road only cares that ``integration_branch`` is
    declared. How the application team organises branches (and what their
    local clone has fetched) is outside specy-road's scope.
    """
    gw = root / "roadmap" / "git-workflow.yaml"
    if not gw.is_file():
        print(
            "warning: missing roadmap/git-workflow.yaml — add the template "
            "from `specy-road init project` so CLI and PM GUI share your "
            "integration branch.",
            file=sys.stderr,
        )
        return
    _data, err = load_git_workflow_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)


def validate_orchestration_contract(root: Path) -> None:
    """Validate ``roadmap/orchestration.yaml`` if present.

    A missing file is not a warning: it means the default review policy
    (one reviewer, any family), which is the scaffolded template's content.
    """
    _data, err = load_orchestration_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)


def validate_at(
    root: Path,
    *,
    no_overlap_warn: bool = False,
    require_registry: bool = True,
    auto_heal: bool = True,
    show_all: bool = False,
) -> None:
    """Validate roadmap + registry under ``root`` (repo root containing ``roadmap/``).

    F-006/F-008: self-heal pass runs first (silent fixes for missing
    codenames, deprecated fields). Pass ``auto_heal=False`` to disable,
    e.g. in a read-only CI drift check. ``show_all`` lists every unauthored
    leaf instead of the first ten.
    """
    reg_path = registry_path(root)
    if require_registry and not reg_path.is_file():
        print(f"missing {reg_path}", file=sys.stderr)
        raise SystemExit(1)

    validate_roadmap_line_limits(root)
    discover_manifest_path(root)
    validate_git_workflow_contract(root)
    validate_orchestration_contract(root)
    warn_if_pin_differs(root)
    warn_if_schemas_stale(root)
    warn_if_stubs_stale(root)
    warn_if_agents_md_block_stale(root)
    warn_missing_load_order_paths(root)
    warn_unregistered_commands(root)
    warn_if_generated_files_ignored(root)

    if auto_heal:
        changed, _logs = auto_heal_roadmap(root)
        if changed:
            # Re-check line limits after healing in case a chunk grew.
            validate_roadmap_line_limits(root)

    mdoc = load_manifest_mapping(root)
    mschema = root / "schemas" / "manifest.schema.json"
    validate_schema(mdoc, load_schema(mschema), "manifest.schema")
    roadmap = load_roadmap(root)
    if reg_path.is_file():
        with reg_path.open(encoding="utf-8") as f:
            registry = yaml.safe_load(f)
    else:
        registry = {"version": 1, "entries": []}

    run_validation(
        roadmap,
        registry,
        no_overlap_warn,
        repo_root=root,
        show_all=show_all,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overlap-warn",
        action="store_true",
        help="suppress touch-zone overlap warnings",
    )
    parser.add_argument(
        "--no-phase-status-warn",
        action="store_true",
        help=(
            "Deprecated. Ignored. A parent status that disagrees with the F-013 "
            "rollup on Complete is reported as a warning (it never fails validation), "
            "because the authored chunk value is what a reviewer reads."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when validation passes with warnings (or self-heal notes), "
        "e.g. as a CI gate once an upgrade window closes.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="List every open leaf with a placeholder planning sheet and no acceptance "
        "(do-next-available-task skips them), not just the first ten.",
    )
    add_repo_root_arg(parser)
    args = parser.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()
    with _counting_stderr() as stderr:
        validate_at(
            root,
            no_overlap_warn=args.no_overlap_warn,
            require_registry=True,
            show_all=args.all,
        )
    if args.strict and stderr.lines:
        sys.stdout.flush()   # the OK line first, then why it does not count
        print(f"FAILED (--strict): validation passed with {stderr.lines} line(s) of warnings above.",
              file=sys.stderr)
        raise SystemExit(1)


class _CountingStderr:
    """Pass writes through to the real stderr and count the lines.

    Every warning ``validate`` emits goes to stderr and every error exits, so a
    validation that returns having written to stderr is one that warned. One
    count here is the whole of ``--strict``, rather than a registry each of the
    dozen warning sites would have to remember to use.
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self.lines = 0

    def write(self, text: str) -> int:
        self.lines += text.count("\n")
        return self.inner.write(text)

    def flush(self) -> None:
        self.inner.flush()


@contextlib.contextmanager
def _counting_stderr():
    counter = _CountingStderr(sys.stderr)
    with contextlib.redirect_stderr(counter):
        yield counter


if __name__ == "__main__":
    main()
