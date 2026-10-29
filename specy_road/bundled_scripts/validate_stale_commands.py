"""Warn when AGENTS.md or CLAUDE.md names a specy-road command this version does not register."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.cli import REPLACED_COMMANDS, _known_commands
from specy_road.managed_block import HTML_COMMENT
from specy_road.runtime_paths import git_root
from specy_road.specyrd_cli import _build_parser as _specyrd_parser

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
# Emphasis directly attached to the product name is markup, so "_" is not a word
# boundary there. A "_" inside an identifier (foo_specy-road) still blocks.
_MENTION = re.compile(
    r"(?:(?<![A-Za-z0-9])[*_]+|(?<![\w/.-]))"
    r"(specy-road|specyrd)[ \t]+(?:[*_]+)?"
    r"([a-z][a-z0-9-]*)[*_]*"
)
_PLAIN_WORD = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# The product name is a noun phrase when one of these words is the token
# immediately before it, with only whitespace between ("the specy-road toolkit").
_NOUN_PHRASE = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "other",
        "any",
        "all",
        "every",
        "each",
        "its",
        "our",
        "your",
        "their",
        "own",
        "of",
        "with",
        "in",
        "for",
        "from",
        "about",
    }
)
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
    words = re.findall(r"[A-Za-z]+", re.sub(r"[*_`]+", " ", line[mark.end() : start]))
    return not words or (len(words) == 1 and words[0].lower() in _RUN_VERB)


def _run_verb(line: str, start: int) -> bool:
    words = _preceding_words(line, start)
    immediate = words[-1] if words else ""
    earlier = words[-2] if len(words) > 1 else ""
    return immediate in _RUN_VERB or (
        earlier in _RUN_VERB and immediate in _NOUN_PHRASE
    )


def _noun_phrase(line: str, start: int) -> bool:
    """True when the token immediately before the product name is a determiner or preposition.

    Only whitespace, and emphasis markers (``*``, ``_``) attached to the product
    name, may sit between that word and the name (``the **specy-road toolkit**``
    is quiet). Any other token, including a digit or punctuation, cancels the
    exclusion (``the 2 specy-road frob`` reports).
    """
    before = line[:start].rstrip("*_").rstrip(" \t")
    if not before:
        return False
    split_at = len(before)
    while split_at > 0 and not before[split_at - 1].isspace():
        split_at -= 1
    return before[split_at:].lower() in _NOUN_PHRASE


def _next_token(line: str, start: int) -> str:
    match = _MENTION.match(line, start)
    found = re.match(r"[ \t]*(\S+)", line[match.end() :])
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


def _plain_follower(line: str, start: int) -> bool:
    """True when nothing follows the token, or the next token is a plain word.

    A plain word is letters only; a hyphen or apostrophe inside it is still
    plain. Prose punctuation around that word (parentheses, sentence marks)
    does not count (``formats (templates...)``). Anything else cancels the
    exclusion (``the specy-road frob @agent``).
    """
    raw = _next_token(line, start)
    if not raw:
        return True
    word = raw.strip("()[]{}.,;:!?…").strip(".")
    return _PLAIN_WORD.fullmatch(word) is not None


def _reports(line: str, start: int) -> bool:
    """Mandatory contexts first. A noun phrase is the only exclusion."""
    if (
        _command_led_list_item(line, start)
        or _run_verb(line, start)
        or _mandatory_follower(line, start)
    ):
        return True
    if _noun_phrase(line, start) and _plain_follower(line, start):
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


def _fence_marker(line: str) -> tuple[str, int, int] | None:
    """The fence run at the start of a line: character, length, index after the run."""
    match = _FENCE.match(line)
    if match is None:
        return None
    run = match.group(1)
    return run[0], len(run), match.end()


def _fence_closes(line: str, open_fence: tuple[str, int]) -> bool:
    """True when the line ends an open fence (same char, length >= opener, no info string)."""
    marker = _fence_marker(line)
    if marker is None:
        return False
    char, width, end = marker
    if char != open_fence[0] or width < open_fence[1]:
        return False
    return not line[end:].strip()


def _command_mentions(lines: list[tuple[int, str]]):
    """``(line, tool, name)`` for each command-shaped token the rule keeps."""
    open_fence: tuple[str, int] | None = None
    for lineno, line in lines:
        if open_fence is not None:
            if _fence_closes(line, open_fence):
                open_fence = None
                continue
            for tool, name in _MENTION.findall(line):
                yield lineno, tool, name
            continue
        marker = _fence_marker(line)
        if marker is not None:
            open_fence = (marker[0], marker[1])
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
    specyrd = next(
        a
        for a in _specyrd_parser()._actions
        if isinstance(a, argparse._SubParsersAction)
    )
    return {
        "specy-road": {*_known_commands(), "version"},
        "specyrd": set(specyrd.choices),
    }


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

    Scanning is line-based and best-effort. Inline code spans are parsed only when
    they open and close on the same line; code spans that span lines are out of
    scope.

    Every occurrence is returned. The same token on two lines is two entries
    (``specy-road frob`` twice). A registered command is never returned
    (``specy-road validate --strict``).

    Mandatory contexts are decided first and win over a noun phrase: a code
    span (a run of N backticks, N >= 1, closed by the next run of exactly N;
    ``the specy-road frob`` and ```the specy-road frob``` warn, and one
    backtick inside a longer span does not end it), a fenced block (opened by a
    run of backticks or tildes and closed only by a line whose fence uses that
    same character, is at least as long, and has nothing but whitespace after
    the run, so `` ```bash `` does not close and ``` inside a four-backtick fence
    and ~~~ inside a backtick fence stay inside), a command-led list item (the product name is the
    first token after the marker, optionally in code or emphasis, or it is
    preceded only by a run verb: ``- specy-road frob --x``, ``- Run specy-road
    frob``), a run verb (run, exec, execute, invoke, uvx), and a token followed
    by a flag, a path, a quoted argument, an id-like argument, or the word
    command or subcommand (``## the specy-road frob --x``, ``Use the specy-road
    frob M1.2.``, ``Use the specy-road frob command.``). A heading is not
    special (``# Please specy-road frob`` warns). The only exclusion is a noun
    phrase: the token immediately before the product name, with only whitespace
    and emphasis markers attached to the name between them (``the
    **specy-road toolkit** is``), is a determiner, possessive, or preposition — the, a, an, this, that,
    these, those, other, any, all, every, each, its, our, your, their, own,
    of, with, in, for, from, about — and the token is followed by a plain
    word or nothing. A plain word is letters only; a hyphen or apostrophe
    inside it is still plain, and prose punctuation around it (parentheses,
    sentence marks) does not count (``the specy-road toolkit is``, ``other
    specy-road formats (templates...)``, and a prose bullet such as
    ``- **Adoption prompts** are kept aligned with other specy-road formats``).
    Anything else after the token cancels the exclusion (``the specy-road frob
    @agent`` warns). Emphasis
    markers attached to the product name or the token are markup
    (``Run __specy-road frob__ now.`` and ``- __specy-road frob__`` warn). A
    digit or any other token between the determiner and the name cancels it
    (``the 2 specy-road frob`` warns).
    """
    return [
        mention for _, mention in _occurrences(list(enumerate(text.splitlines(), 1)))
    ]


def warn_unregistered_commands(root: Path) -> None:
    """One non-fatal line per occurrence ``AGENTS.md`` / ``CLAUDE.md`` names, with that file's line number.

    Repeated names are not collapsed. The managed block is skipped:
    ``warn_if_agents_md_block_stale`` already reports one written by another
    version.
    """
    root = root.resolve()
    checkout = git_root(root) or root
    paths = dict.fromkeys(
        base / name for base in (root, checkout) for name in ("AGENTS.md", "CLAUDE.md")
    )
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
            advice = (
                f"use `{replacement}`"
                if replacement
                else "it was removed and nothing replaces it"
                if replacement == ""
                else f"see `{mention.split()[0]} --help`"
            )
            print(
                f"agents: warning — {rel}:{lineno} tells agents to run `{mention}`, which is not a "
                f"command in specy-road {__version__}; {advice}.",
                file=sys.stderr,
            )
