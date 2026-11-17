"""Suggested prompts name canonical commands and options from the parity inventory.

Invocations are the shell-fence lines and the single-line code spans that begin
with ``specy-road`` or ``specyrd``. Each is tokenised with :func:`shlex.split`
and cut at an unquoted shell operator or a bare ``--``. An operator
separates commands only outside quotes, longest match first (``&&`` before
``&``, ``||`` before ``|``, ``>>`` before ``>``), so ``validate;`` and
``&&specy-road`` split and ``--title "A; B"`` does not. A documented
placeholder token is skipped, including a ``<NAME>`` glued where a redirect
would be. An option token (it starts with ``-``) is never a placeholder: its
name, the text before ``=``, is checked even when the value is one. A command
path or option that is not a canonical name in the M16.1.1 parity inventory
fails as ``<file>: <token>``. A name ``tests/parity/command_map.yaml`` retires
is not canonical, including a hidden alias the CLI still accepts.
"""

from __future__ import annotations

import functools
import re
import shlex
from pathlib import Path

import pytest

from tests.parity.command_map import command_map_rows, split_invocation
from tests.parity.help_surface import command_tree, parser_inventory

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "suggested_prompts"
_OPERATOR_ORDER = (">>", "&&", "||", "|", "&", ";", "(", ")", ">", "<")
_PLACEHOLDER_TOKEN = re.compile(r"<[^>]+>")
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
_SPAN = re.compile(r"`([^`\n]+)`")
_PROGRAMS = ("specy-road", "specyrd")


def _placeholder(token: str) -> bool:
    """A documented placeholder token, not a command word and not an option.

    One rule. A placeholder is a whole shell token: a whole ``[NAME]``, or a
    token containing ``<NAME>``, ``…``, ``...``, or braces. A token that starts
    with ``-`` is an option, so it is kept and its name is checked; a
    placeholder written after ``=`` is only the value. Limit: the decision is
    that whole token from :func:`shlex.split`, not a second split of the value.
    """
    if token.startswith("-"):
        return False
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


def _quote_ends(text: str, index: int, quote: str) -> bool:
    """True when ``text[index]`` closes ``quote``. A ``"`` closes only if it is not escaped."""
    if text[index] != quote:
        return False
    if quote == "'":
        return True
    slashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 0


def _unquoted_chunk(text: str, index: int) -> tuple[str, str]:
    """``(kind, text)`` outside quotes: a quote mark, an operator, or a literal.

    A literal is one character, a backslash and the character it escapes, or a
    ``<NAME>`` placeholder. Operators are longest-first, so ``&&`` is not two
    ``&``.
    """
    if text[index] in "'\"":
        return "quote", text[index]
    if text[index] == "\\" and index + 1 < len(text):
        return "literal", text[index:index + 2]
    placeholder = _PLACEHOLDER_TOKEN.match(text, index)
    if placeholder:
        return "literal", placeholder.group()
    operator = next((op for op in _OPERATOR_ORDER if text.startswith(op, index)), "")
    if operator:
        return "operator", operator
    return "literal", text[index]


def _command_pieces(text: str) -> list[str]:
    """Pieces of ``text`` between unquoted shell operators.

    One rule. An operator separates commands only outside quotes, and the
    longer form wins (``&&`` before ``&``, ``||`` before ``|``, ``>>`` before
    ``>``). Inside ``'...'`` every character is literal. Inside ``"..."`` a
    quote ends only when it is not escaped. A backslash outside quotes
    escapes the next character, and a ``<NAME>`` placeholder is not a
    redirect. Limit: ``$(...)`` and backticks are not quoting contexts, so an
    unquoted ``(`` still separates.
    """
    pieces: list[str] = []
    buf: list[str] = []
    index = 0
    quote = ""
    while index < len(text):
        if quote:
            buf.append(text[index])
            if _quote_ends(text, index, quote):
                quote = ""
            index += 1
            continue
        kind, chunk = _unquoted_chunk(text, index)
        if kind == "quote":
            quote = chunk
        if kind == "operator":
            pieces.append("".join(buf))
            buf = []
        else:
            buf.append(chunk)
        index += len(chunk)
    pieces.append("".join(buf))
    return pieces


def _begins_with_program(text: str) -> bool:
    """True when ``text`` is an invocation: optional ``$``, then operators, then the program."""
    if text.startswith("$"):
        text = text[1:].lstrip()
    while text and not text.startswith(_PROGRAMS):
        operator = next((op for op in _OPERATOR_ORDER if text.startswith(op)), "")
        if not operator:
            return False
        text = text[len(operator):].lstrip()
    return text.startswith(_PROGRAMS)


def _invocation_tokens(tokens: list[str]) -> list[str]:
    """Words of one piece: placeholders omitted, a bare ``--`` ends it.

    Operators are already removed by :func:`_command_pieces`. A word whose
    text is ``&&`` or ``;`` was quoted, so it stays a word.
    """
    current: list[str] = []
    for token in tokens:
        if token == "--":
            break
        if not _placeholder(token):
            current.append(token)
    if current and current[0] in _PROGRAMS:
        return current
    return []


def _invocations_on_line(lineno: int, line: str) -> list[tuple[int, list[str]]]:
    text = line.strip()
    if not _begins_with_program(text):
        return []
    if text.startswith("$"):
        text = text[1:].strip()
    found: list[tuple[int, list[str]]] = []
    for piece in _command_pieces(text):
        if not piece.strip():
            continue
        try:
            tokens = shlex.split(piece, comments=True, posix=True)
        except ValueError:
            return [(lineno, ["<unclosed-quote>"])]
        words = _invocation_tokens(tokens)
        if words:
            found.append((lineno, words))
    return found


def prompt_invocations(text: str) -> list[tuple[int, list[str]]]:
    """``(line, tokens)`` for each ``specy-road`` / ``specyrd`` invocation in ``text``.

    Shell fences contribute each logical line that begins with the program (a
    leading ``$`` is the prompt, not a token). Outside fences, only a single-line
    code span whose content begins with the program counts. Unquoted shell
    operators are cut out of the line first, quotes still in place, and each
    piece is tokenised with :func:`shlex.split`. A quoted ``&`` or ``;`` stays
    inside its word, so an option after ``--title "A; B"`` is still checked.
    A bare ``--`` ends the piece. A documented placeholder token is omitted,
    so an option that follows one is still checked. An option token is kept
    whole, placeholder value included. A line that begins with operators and
    then the program is still an invocation.
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


@pytest.mark.repo
def test_suggested_prompts_name_only_canonical_commands() -> None:
    problems = []
    for path in sorted(PROMPTS.glob("*.md")):
        problems.extend(command_problems(path))
    assert problems == []


@pytest.mark.parametrize(
    ("body", "tokens"),
    [
        ("`specy-road validate --no-such-flag`\n", ["--no-such-flag"]),
        ("```bash\nspecy-road refresh-stubs\n```\n", ["refresh-stubs"]),
        ("`specy-road validate <NODE_ID> --dry-run`\n", ["--dry-run"]),
        ("`specy-road validate --no-such-flag=<VALUE>`\n", ["--no-such-flag"]),
        ("`specy-road validate --no-such-flag=...`\n", ["--no-such-flag"]),
        ("`specy-road validate --no-such-flag=…`\n", ["--no-such-flag"]),
        ("`specy-road validate --no-such-flag={VALUE}`\n", ["--no-such-flag"]),
        (
            "`specy-road validate --no-such-flag=<VALUE> --also-bad=...`\n",
            ["--no-such-flag", "--also-bad"],
        ),
        ("`specy-road validate --repo-root=<PATH>`\n", []),
        ("`specy-road validate --repo-root=...`\n", []),
        ("`specy-road validate --strict={on}`\n", []),
        ("`specy-road validate;`\n", []),
        ("`specy-road validate &&specy-road refresh-stubs`\n", ["refresh-stubs"]),
        ("`specy-road validate;specy-road refresh-stubs`\n", ["refresh-stubs"]),
        ("`specy-road validate||specy-road refresh-stubs`\n", ["refresh-stubs"]),
        ("`specy-road validate&specy-road refresh-stubs`\n", ["refresh-stubs"]),
        ("`specy-road validate>>out`\n", []),
        ("`(specy-road refresh-stubs)`\n", ["refresh-stubs"]),
        (
            '`specy-road brainstorm start --topic "costs & benefits" --no-such-flag`\n',
            ["--no-such-flag"],
        ),
        (
            '`specy-road add-node --title "A; B" --no-such-flag`\n',
            ["--no-such-flag"],
        ),
        (
            "`specy-road add-node --title 'A; B' --no-such-flag`\n",
            ["--no-such-flag"],
        ),
        (
            '`specy-road add-node --title "A;B" --no-such-flag`\n',
            ["--no-such-flag"],
        ),
        (
            '`specy-road add-node --title "&&" --no-such-flag`\n',
            ["--no-such-flag"],
        ),
    ],
)
def test_a_bad_token_fails_naming_the_file_and_the_token(
    tmp_path: Path, body: str, tokens: list[str]
) -> None:
    """Each clause of the placeholder and operator rules, named by file and token.

    An unknown option, a retired alias, and an option after a separate
    placeholder fail. So does an option whose value is a placeholder
    (``<VALUE>``, ``...``, ``…``, braces), including two such options on one
    line. A canonical option with those values is not a problem. A canonical
    command with ``;`` or ``>>`` glued on passes. A retired command after
    ``&&``, ``;``, ``||`` or ``&``, including one wrapped in ``()``, fails.
    An option after a quoted ``&``, ``;`` or ``&&`` fails too.
    """
    path = tmp_path / "prompt.md"
    path.write_text(body, encoding="utf-8")
    assert command_problems(path) == [f"{path}: {token}" for token in tokens]
