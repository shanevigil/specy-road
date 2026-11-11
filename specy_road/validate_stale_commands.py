"""Warn when AGENTS.md or CLAUDE.md names a specy-road command or long flag this version lacks."""

from __future__ import annotations

import argparse
import difflib
import functools
import re
import shlex
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.cli import REPLACED_COMMANDS, command_parsers, registered_agent_command_names
from specy_road.cli_args import subcommand_parsers
from specy_road.git_subprocess import git_root
from specy_road.harness_instruction_files import TEAM_MD
from specy_road.managed_block import agent_file_lines_outside_block

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
# Emphasis directly attached to the product name is markup, so "_" is not a word
# boundary there. A "_" inside an identifier (foo_specy-road) still blocks.
_MENTION = re.compile(
    r"(?:(?<![A-Za-z0-9])[*_]+|(?<![\w/.-]))"
    r"(?:[*_]+)?(specy-road|specyrd)(?:[*_]+)?[ \t]+"
    r"(?:[*_]+)?([a-z][a-z0-9-]*)[*_]*(?!\w)"
)
_PUNCT_ONLY = re.compile(r"^[\(\)\[\]\{\}.,;:!?…\"'`—–-]+$")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# Article before the product name after a run verb ("run the specy-road frob").
_NOUN_PHRASE = frozenset(
    {"the", "a", "an", "this", "that", "these", "those", "other", "any", "all",
     "every", "each", "its", "our", "your", "their", "own", "of", "with", "in",
     "for", "from", "about"}
)
_RUN_VERB = frozenset({"run", "exec", "execute", "invoke", "uvx"})
_PRODUCT = re.compile(
    r"(?:(?<![A-Za-z0-9])[*_]+|(?<![\w/.-]))(?:[*_]+)?(specy-road|specyrd)(?:[*_]+)?"
)


def _preceding_words(text: str, start: int) -> list[str]:
    before = text[:start].rstrip(" \t*_`\"'()[]{}<>|:—–-")
    return [word.lower() for word in re.findall(r"[A-Za-z]+", before)[-2:]]


def _command_led_list_item(line: str, start: int) -> bool:
    mark = _LIST_ITEM.match(line)
    if mark is None or start < mark.end():
        return False
    words = re.findall(r"[A-Za-z]+", re.sub(r"[*_`]+", " ", line[mark.end() : start]))
    return not words or (len(words) == 1 and words[0].lower() in _RUN_VERB)


def _run_verb(line: str, start: int) -> bool:
    words = _preceding_words(line, start)
    immediate = words[-1] if words else ""
    earlier = words[-2] if len(words) > 1 else ""
    return immediate in _RUN_VERB or (
        earlier in _RUN_VERB and immediate in _NOUN_PHRASE
    )


def _product_before_span(line: str, span_start: int) -> tuple[int, str] | None:
    match = re.search(_PRODUCT.pattern + r"[ \t]*$", line[:span_start])
    if match is None:
        return None
    return match.start(), match.group(1)


def _mention_at(line: str, start: int) -> tuple[str, str, int] | None:
    match = _MENTION.match(line, start)
    if match:
        return match.group(1), match.group(2), match.end()
    prefix = re.compile(_PRODUCT.pattern + r"[ \t]*").match(line, start)
    if prefix is None:
        return None
    pos = prefix.end()
    while pos < len(line) and line[pos] in " \t":
        pos += 1
    if pos >= len(line) or line[pos] != "`":
        return None
    for span_start, span_end, content in _code_spans(line):
        if span_start != pos:
            continue
        token = content.strip()
        if re.fullmatch(r"[a-z][a-z0-9-]*", token):
            return prefix.group(1), token, span_end
        return None
    return None


def _span_command_token(line: str, span_start: int, content: str) -> tuple[int, str, str] | None:
    token = content.strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]*", token):
        return None
    product = _product_before_span(line, span_start)
    if product is None:
        return None
    return product[0], product[1], token


def _strip_prose_punctuation(raw: str) -> str:
    if re.fullmatch(r"['\u2019]s", raw, re.IGNORECASE):
        return ""
    word = raw.strip("()[]{}.,;:!?…\"'`").strip(".")
    return word


def _followers_after(line: str, mention_end: int):
    pos = mention_end
    while pos < len(line):
        while pos < len(line) and line[pos] in " \t":
            pos += 1
        if pos >= len(line):
            return
        if line[pos] == "`":
            advanced = False
            for span_start, span_end, content in _code_spans(line):
                if span_start == pos:
                    yield content.strip()
                    pos = span_end
                    advanced = True
                    break
            if not advanced:
                return
            continue
        found = re.match(r"(\S+)", line[pos:])
        if not found:
            return
        yield found.group(1)
        pos += found.end()


def _looks_like_node_id(raw: str) -> bool:
    word = _strip_prose_punctuation(raw)
    return bool(re.match(r"M\d", word))


def _first_meaningful_follower(line: str, start: int) -> str:
    resolved = _mention_at(line, start)
    if resolved is None:
        return ""
    for raw in _followers_after(line, resolved[2]):
        if _PUNCT_ONLY.match(raw) or not _strip_prose_punctuation(raw):
            continue
        return raw
    return ""


def _mandatory_follower(line: str, start: int) -> bool:
    resolved = _mention_at(line, start)
    if resolved is None:
        return False
    raw = _first_meaningful_follower(line, start)
    if not raw:
        return False
    pos = resolved[2]
    while pos < len(line) and line[pos] in " \t":
        pos += 1
    if pos < len(line) and line[pos] == "`" and _looks_like_node_id(raw):
        return False
    word = _strip_prose_punctuation(raw)
    if raw[0] in "\"'" or re.match(r"-{1,2}[A-Za-z0-9]", raw):
        return True
    if word.lower() in {"command", "subcommand"}:
        return True
    if "/" in word or word.startswith(".") or re.search(r"\.[A-Za-z]", word):
        return True
    return bool(re.search(r"\d", word))


def _reports(line: str, start: int) -> bool:
    return (
        _command_led_list_item(line, start)
        or _run_verb(line, start)
        or _mandatory_follower(line, start)
    )


def _backtick_run(line: str, index: int) -> int:
    end = index
    while end < len(line) and line[end] == "`":
        end += 1
    return end


def _code_spans(line: str) -> list[tuple[int, int, str]]:
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


def _fence_marker(line: str) -> tuple[str, int, int] | None:
    match = _FENCE.match(line)
    if match is None:
        return None
    run = match.group(1)
    return run[0], len(run), match.end()


def _opening_is_code_span(line: str) -> bool:
    lead = len(line) - len(line.lstrip(" \t"))
    if lead >= len(line) or line[lead] != "`":
        return False
    for start, end, _content in _code_spans(line):
        if start == lead:
            return True
    return False


def _fence_closes(line: str, open_fence: tuple[str, int]) -> bool:
    marker = _fence_marker(line)
    if marker is None:
        return False
    char, width, end = marker
    if char != open_fence[0] or width < open_fence[1]:
        return False
    return not line[end:].strip()


def _inside_span(index: int, spans: list[tuple[int, int, str]]) -> bool:
    return any(start <= index < end for start, end, _ in spans)


def _mentions_in_fenced_line(lineno: int, line: str):
    found = [(match.start(), match.group(1), match.group(2)) for match in _MENTION.finditer(line)]
    for span_start, _, content in _code_spans(line):
        parsed = _span_command_token(line, span_start, content)
        if parsed is not None:
            found.append(parsed)
    for _, tool, name in sorted(found, key=lambda mention: mention[0]):
        yield lineno, tool, name


def _mentions_on_open_line(lineno: int, line: str):
    spans = _code_spans(line)
    for span_start, _, content in spans:
        parsed = _span_command_token(line, span_start, content)
        if parsed is not None:
            product_start, tool, token = parsed
            if _reports(line, product_start):
                yield lineno, tool, token
        else:
            for tool, name in _MENTION.findall(content):
                yield lineno, tool, name
    for match in _MENTION.finditer(line):
        if _inside_span(match.start(), spans):
            continue
        if _reports(line, match.start()):
            yield lineno, match.group(1), match.group(2)


def _classified_lines(lines: list[tuple[int, str]]):
    """``(line, text, fenced)`` for each numbered line that is not a fence marker."""
    open_fence: tuple[str, int] | None = None
    for lineno, line in lines:
        if open_fence is not None:
            if _fence_closes(line, open_fence):
                open_fence = None
                continue
            yield lineno, line, True
            continue
        marker = _fence_marker(line)
        if marker is not None and not _opening_is_code_span(line):
            open_fence = (marker[0], marker[1])
            continue
        yield lineno, line, False


def _command_mentions(lines: list[tuple[int, str]]):
    for lineno, line, fenced in _classified_lines(lines):
        if fenced:
            yield from _mentions_in_fenced_line(lineno, line)
        else:
            yield from _mentions_on_open_line(lineno, line)


def _occurrences(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    registered = registered_agent_command_names()
    found: list[tuple[int, str]] = []
    for lineno, tool, name in _command_mentions(lines):
        if name not in registered[tool]:
            found.append((lineno, f"{tool} {name}"))
    return found


def unregistered_commands(text: str) -> list[str]:
    """Return each unregistered ``specy-road <name>`` / ``specyrd <name>`` in ``text``, in order.

    Line-based, best-effort scanning (same-line inline code spans only; multi-line spans
    out of scope). A one-line span immediately after the product name whose content is
    one command-shaped token is that token (``specy-road `frob` --flag``). Open-line
    mentions warn only in mandatory contexts; see ``docs/install-and-usage.md``.
    """
    return [
        mention for _, mention in _occurrences(list(enumerate(text.splitlines(), 1)))
    ]


def agent_files(root: Path) -> list[Path]:
    """The agent files ``validate`` checks: ``AGENTS.md`` and ``CLAUDE.md`` at the project and git roots, and the team file."""
    root = root.resolve()
    checkout = git_root(root) or root
    return list(dict.fromkeys(
        [*(base / name for base in (root, checkout) for name in ("AGENTS.md", "CLAUDE.md")), root / TEAM_MD]
    ))


def _lines_outside_block(path: Path) -> list[tuple[int, str]]:
    """``path``'s numbered lines outside its managed block; none when it is missing or not UTF-8."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    return agent_file_lines_outside_block(text)


def file_unregistered_commands(path: Path) -> list[tuple[int, str]]:
    """``(line, mention)`` per unregistered command ``path`` names outside its managed block; none when unreadable.

    The scanner ``validate`` runs over :func:`agent_files` and ``chore garden`` runs over those and ``docs/``.
    """
    return _occurrences(_lines_outside_block(path))


def line_unregistered_commands(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """``(line, mention)`` per unregistered command in numbered ``lines``: the scanner, for a caller's own line source."""
    return _occurrences(lines)


def stale_command_advice(mention: str) -> str:
    """What to do about ``mention``: its replacement, that nothing replaces it, or where to look."""
    replacement = REPLACED_COMMANDS.get(mention)
    return (
        f"use `{replacement}`"
        if replacement
        else "it was removed and nothing replaces it"
        if replacement == ""
        else f"see `{mention.split()[0]} --help`"
    )


_INVOKED = re.compile(r"(?<![\w/.-])specy-road(?=[ \t])")
_OPERATOR = re.compile(r"[();<>|&]+")
#: An invocation holding one of these is a template (``specy-road <cmd> --x``), not a command line.
_PLACEHOLDER = re.compile(r"<[^<>\s]+>|\.\.\.|…|[{}]")


def _code_texts(lines: list[tuple[int, str]]):
    """``(line, text)``: each fenced line whole, and each code span's content on an open line."""
    for lineno, line, fenced in _classified_lines(lines):
        if fenced:
            yield lineno, line
        else:
            yield from ((lineno, content) for _start, _end, content in _code_spans(line))


def _invocation_words(text: str) -> list[str] | None:
    """The shell words of ``text`` up to a shell operator or a bare ``--``.

    ``None`` when ``shlex`` cannot split it or it holds a placeholder: neither is a command line.
    """
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return None
    end = next((i for i, w in enumerate(words) if w == "--" or _OPERATOR.fullmatch(w)), len(words))
    return None if _PLACEHOLDER.search(" ".join(words[:end])) else words[:end]


@functools.cache
def _parsers(name: str) -> tuple[argparse.ArgumentParser, ...]:
    return tuple(command_parsers(name))


def _command_chain(words: list[str]) -> tuple[str, list[argparse.ArgumentParser], list[str]] | None:
    """``(command words, parsers outermost first, the words after them)`` for a registered command.

    The words name each subcommand down to a parser with none. ``None`` when the first word is not a
    command with a parser, or a word in a subcommand's place is not one of that parser's.
    """
    if not words or words[0] not in registered_agent_command_names()["specy-road"] - {"version"}:
        return None
    chain, rest = list(_parsers(words[0])), words[1:]
    named = [words[0]]
    while subs := subcommand_parsers(chain[-1]):
        if not rest or rest[0] not in subs:
            return None
        chain.append(subs[rest[0]])
        named.append(rest.pop(0))
    return " ".join(named), chain, rest


def invocation_unknown_flags(
    words: list[str], parsers: list[argparse.ArgumentParser]
) -> list[tuple[str, str]]:
    """``(flag, closest valid long flag)`` per ``--long`` flag in ``words`` that ``parsers`` refuse.

    ``parsers`` is a command's chain, outermost first (:func:`specy_road.cli.command_parsers`):
    an option declared on an outer parser is accepted too. Short options are not checked, and
    nothing is reported for a parser that passes its words through (``argparse.REMAINDER``).
    """
    if any(action.nargs == argparse.REMAINDER for action in parsers[-1]._actions):
        return []
    valid = {option for parser in parsers for a in parser._actions for option in a.option_strings}
    longs = sorted(option for option in valid if option.startswith("--"))
    flags = (word.split("=", 1)[0] for word in words if word.startswith("--"))
    return [
        (flag, difflib.get_close_matches(flag, longs, n=1, cutoff=0)[0])
        for flag in flags
        if flag not in valid
    ]


def line_unknown_flags(lines: list[tuple[int, str]]) -> list[tuple[int, str, str, str]]:
    """``(line, command, flag, closest)`` per long flag its command refuses, in numbered ``lines``.

    Only ``specy-road <cmd> [<sub>] --flag`` invocations inside a code span or a fenced block are
    read; one that cannot be split, or holds a placeholder, is skipped. The flag scan ``validate``
    runs over :func:`agent_files` and ``chore garden`` over those and ``docs/``.
    """
    found = []
    for lineno, text in _code_texts(lines):
        for match in _INVOKED.finditer(text):
            words = _invocation_words(text[match.end() :])
            # Only an invocation passing a long flag builds its command's parsers (and imports it).
            has_flag = words is not None and any(w.startswith("--") for w in words)
            resolved = _command_chain(words) if has_flag else None
            if resolved is not None:
                command, chain, rest = resolved
                found += [
                    (lineno, f"specy-road {command}", flag, closest)
                    for flag, closest in invocation_unknown_flags(rest, chain)
                ]
    return found


def unknown_flag_advice(command: str, flag: str, closest: str) -> str:
    """That ``command`` refuses ``flag`` in this version, and the flag it most resembles."""
    return f"`{command}` has no `{flag}` in specy-road {__version__}; closest: `{closest}`"


def warn_unregistered_commands(root: Path) -> None:
    """``validate``'s agent-file warnings: unregistered commands, then unknown long flags."""
    root = root.resolve()
    checkout = git_root(root) or root
    for path in agent_files(root):
        _warn_agent_file(path.relative_to(checkout), _lines_outside_block(path))


def _warn_agent_file(rel: Path, lines: list[tuple[int, str]]) -> None:
    for lineno, mention in _occurrences(lines):
        print(
            f"agents: warning — {rel}:{lineno} tells agents to run `{mention}`, which is not a "
            f"command in specy-road {__version__}; {stale_command_advice(mention)}.",
            file=sys.stderr,
        )
    for lineno, command, flag, closest in line_unknown_flags(lines):
        print(
            f"agents: warning — {rel}:{lineno}: {unknown_flag_advice(command, flag, closest)}.",
            file=sys.stderr,
        )
