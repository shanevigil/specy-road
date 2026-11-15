"""Suggested prompts name canonical commands and options from the parity inventory.

Invocations are the shell-fence lines and the single-line code spans that begin
with ``specy-road`` or ``specyrd``. Each is tokenised with :func:`shlex.split`,
cut at a shell operator or a bare ``--``, and checked after documented
placeholders are skipped. A command path or option that is not a canonical name
in the M16.1.1 parity inventory fails as ``<file>: <token>``. A name
``tests/parity/command_map.yaml`` retires is not canonical, including a hidden
alias the CLI still accepts.
"""

from __future__ import annotations

import functools
import re
import shlex
from pathlib import Path

import pytest

from tests.parity.command_map import command_map_rows, split_invocation
from tests.parity.help_surface import command_tree, parser_inventory

REPO = Path(__file__).resolve().parent.parent
PROMPTS = REPO / "suggested_prompts"
_OPERATORS = frozenset({"&&", "||", "|", "&", ";", "(", ")", ">", "<", ">>"})
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
_SPAN = re.compile(r"`([^`\n]+)`")
_PROGRAMS = ("specy-road", "specyrd")


def _placeholder(token: str) -> bool:
    """A documented placeholder, not a command word or an option.

    The forms the prompts tell an adopter to replace, and the same template
    tokens the rest of the tree already treats as not a command line: ``[NAME]``,
    ``<NAME>``, a token containing ``…`` or ``...``, and a token containing braces.
    """
    if "…" in token or "..." in token or "{" in token or "}" in token:
        return True
    if re.fullmatch(r"\[[^\]]*\]", token):
        return True
    return re.search(r"<[^>]+>", token) is not None


def _logical_lines(block: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join a fence's ``\\`` continuations the way the shell does, keeping the first line number."""
    joined: list[tuple[int, str]] = []
    number: int | None = None
    text = ""
    for lineno, line in block:
        if number is None:
            number, text = lineno, line
        else:
            text = f"{text} {line.strip()}"
        if text.endswith("\\"):
            text = text[:-1].rstrip()
            continue
        joined.append((number, text))
        number, text = None, ""
    if number is not None:
        joined.append((number, text))
    return joined


def _segments(tokens: list[str]) -> list[list[str]]:
    """Invocations in one tokenised line, each cut at an operator or a bare ``--``."""
    found: list[list[str]] = []
    current: list[str] = []
    stopped = False
    for token in tokens:
        if token in _OPERATORS:
            if current:
                found.append(current)
            current, stopped = [], False
            continue
        if stopped or token == "--":
            stopped = True
            continue
        if not _placeholder(token):
            current.append(token)
    if current:
        found.append(current)
    return [segment for segment in found if segment[0] in _PROGRAMS]


def _invocations_on_line(lineno: int, line: str) -> list[tuple[int, list[str]]]:
    text = line.strip()
    if text.startswith("$"):
        text = text[1:].strip()
    if not text.startswith(_PROGRAMS):
        return []
    try:
        tokens = shlex.split(text, comments=True, posix=True)
    except ValueError:
        return [(lineno, ["<unclosed-quote>"])]
    return [(lineno, segment) for segment in _segments(tokens)]


def prompt_invocations(text: str) -> list[tuple[int, list[str]]]:
    """``(line, tokens)`` for each ``specy-road`` / ``specyrd`` invocation in ``text``.

    Shell fences contribute each logical line that begins with the program (a
    leading ``$`` is the prompt, not a token). Outside fences, only a single-line
    code span whose content begins with the program counts. Tokens come from
    :func:`shlex.split`. A shell operator or a bare ``--`` ends the invocation;
    the command after an operator is its own invocation. Documented placeholders
    are omitted, so an option that follows one is still checked.
    """
    lines = text.splitlines()
    in_fence: set[int] = set()
    found: list[tuple[int, list[str]]] = []
    index = 0
    while index < len(lines):
        if not _FENCE_OPEN.match(lines[index]):
            index += 1
            continue
        index += 1
        block: list[tuple[int, str]] = []
        while index < len(lines) and not _FENCE_CLOSE.match(lines[index]):
            in_fence.add(index)
            block.append((index, lines[index]))
            index += 1
        for lineno, logical in _logical_lines(block):
            found.extend(_invocations_on_line(lineno + 1, logical))
        index += 1
    for index, line in enumerate(lines):
        if index in in_fence:
            continue
        for span in _SPAN.findall(line):
            found.extend(_invocations_on_line(index + 1, span))
    return found


def parser_surface() -> dict[str, dict[str, set[str]]]:
    """Every live command path with the subcommands and options its parser lists."""
    surface: dict[str, dict[str, set[str]]] = {}
    for path, parser in command_tree():
        if parser is None:
            entry = {"subcommands": set(), "options": set()}
        else:
            raw = parser_inventory(path, parser)
            entry = {"subcommands": set(raw["subcommands"]), "options": set(raw["options"])}
        surface[" ".join(path)] = entry
    for key in list(surface):
        parent, sep, name = key.rpartition(" ")
        if sep:
            surface[parent]["subcommands"].add(name)
    return surface


def command_row_is_retired(old: str, old_options: set[str], new: str) -> bool:
    """True when a command_map row replaces ``old`` with a different command.

    An option-only row retires flags, not the command. A row whose new command
    sits under the old one renames a child, not the parent.
    """
    if not old or old_options or not new or new == old:
        return False
    return not new.startswith(old + " ")


def drop_retired(surface: dict[str, dict[str, set[str]]]) -> None:
    """Drop retired command paths and retired options from ``surface`` in place."""
    retired: set[str] = set()
    for row in command_map_rows():
        old, old_options = split_invocation(row.get("old"))
        new = split_invocation(row.get("new"))[0]
        if old and old_options and old in surface:
            surface[old]["options"] -= old_options
        if command_row_is_retired(old, old_options, new):
            retired.add(old)
    for command in retired:
        parent, sep, name = command.rpartition(" ")
        if sep and parent in surface:
            surface[parent]["subcommands"].discard(name)
        surface.pop(command, None)


@functools.lru_cache(maxsize=1)
def canonical_surface() -> dict[str, dict[str, frozenset[str]]]:
    """Command paths and option strings that are canonical in the parity inventory.

    The live parsers are the inventory M16.1.1 records (its golden plus the
    ``command_map.yaml`` rows). A row whose old command is a different command
    retires that path, hidden alias included. A row whose old side names options
    retires those options on that command.
    """
    surface = parser_surface()
    drop_retired(surface)
    return {
        key: {
            "subcommands": frozenset(entry["subcommands"]),
            "options": frozenset(entry["options"]),
        }
        for key, entry in surface.items()
    }


def noncanonical_tokens(
    tokens: list[str], surface: dict[str, dict[str, frozenset[str]]]
) -> list[str]:
    """Command words and options in ``tokens`` that are not canonical names."""
    if not tokens:
        return []
    if tokens[0] not in surface:
        return [tokens[0]]
    path = tokens[0]
    index = 1
    while index < len(tokens) and not tokens[index].startswith("-"):
        word = tokens[index]
        nxt = f"{path} {word}"
        if nxt in surface:
            path, index = nxt, index + 1
            continue
        if surface[path]["subcommands"]:
            return [word]
        break
    options = surface[path]["options"]
    bad = []
    for word in tokens[index:]:
        if not word.startswith("-"):
            continue
        flag = word.split("=", 1)[0]
        if flag not in options:
            bad.append(flag)
    return bad


def command_problems(path: Path) -> list[str]:
    """``<file>: <token>`` for each non-canonical command path or option in ``path``."""
    surface = canonical_surface()
    problems = []
    for _lineno, tokens in prompt_invocations(path.read_text(encoding="utf-8")):
        problems.extend(f"{path}: {token}" for token in noncanonical_tokens(tokens, surface))
    return problems


def test_suggested_prompts_name_only_canonical_commands() -> None:
    problems = []
    for path in sorted(PROMPTS.glob("*.md")):
        problems.extend(command_problems(path))
    assert problems == []


@pytest.mark.parametrize(
    ("body", "token"),
    [
        ("`specy-road validate --no-such-flag`\n", "--no-such-flag"),
        ("```bash\nspecy-road refresh-stubs\n```\n", "refresh-stubs"),
        ("`specy-road validate <NODE_ID> --dry-run`\n", "--dry-run"),
    ],
)
def test_a_bad_token_fails_naming_the_file_and_the_token(
    tmp_path: Path, body: str, token: str
) -> None:
    """Unknown option, retired alias, and a real option after a placeholder each fail."""
    path = tmp_path / "prompt.md"
    path.write_text(body, encoding="utf-8")
    assert command_problems(path) == [f"{path}: {token}"]
