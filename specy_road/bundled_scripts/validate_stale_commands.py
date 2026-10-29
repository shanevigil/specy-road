"""Warn when AGENTS.md or CLAUDE.md names a specy-road command this version does not register."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.cli import REPLACED_COMMANDS, registered_agent_command_names
from specy_road.managed_block import agent_file_lines_outside_block
from specy_road.runtime_paths import git_root

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
# Emphasis directly attached to the product name is markup, so "_" is not a word
# boundary there. A "_" inside an identifier (foo_specy-road) still blocks.
_MENTION = re.compile(
    r"(?:(?<![A-Za-z0-9])[*_]+|(?<![\w/.-]))"
    r"(?:[*_]+)?(specy-road|specyrd)(?:[*_]+)?[ \t]+"
    r"(?:[*_]+)?([a-z][a-z0-9-]*)[*_]*(?!\w)"
)
_PLAIN_WORD = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
_PUNCT_ONLY = re.compile(r"^[\(\)\[\]\{\}.,;:!?…\"'`—–-]+$")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# The product name is a noun phrase when one of these words is the token
# immediately before it, with only whitespace between ("the specy-road toolkit").
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


def _noun_phrase(line: str, start: int) -> bool:
    before = line[:start].rstrip("*_").rstrip(" \t")
    if not before:
        return False
    split_at = len(before)
    while split_at > 0 and not before[split_at - 1].isspace():
        split_at -= 1
    return before[split_at:].strip("*_").lower() in _NOUN_PHRASE


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


def _doc_ref_span_after(line: str, mention_end: int) -> bool:
    pos = mention_end
    while pos < len(line) and line[pos] in " \t":
        pos += 1
    if pos >= len(line) or line[pos] != "`":
        return False
    for span_start, span_end, content in _code_spans(line):
        if span_start == pos:
            return _looks_like_node_id(content.strip())
    return False


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


def _plain_follower(line: str, start: int) -> bool:
    raw = _first_meaningful_follower(line, start)
    if not raw:
        return True
    return _PLAIN_WORD.fullmatch(_strip_prose_punctuation(raw)) is not None


def _reports(line: str, start: int) -> bool:
    if (
        _command_led_list_item(line, start)
        or _run_verb(line, start)
        or _mandatory_follower(line, start)
    ):
        return True
    if _noun_phrase(line, start):
        resolved = _mention_at(line, start)
        if resolved and (
            _plain_follower(line, start)
            or _doc_ref_span_after(line, resolved[2])
        ):
            return False
    return True


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
    for tool, name in _MENTION.findall(line):
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


def _command_mentions(lines: list[tuple[int, str]]):
    open_fence: tuple[str, int] | None = None
    for lineno, line in lines:
        if open_fence is not None:
            if _fence_closes(line, open_fence):
                open_fence = None
                continue
            yield from _mentions_in_fenced_line(lineno, line)
            continue
        marker = _fence_marker(line)
        if marker is not None and not _opening_is_code_span(line):
            open_fence = (marker[0], marker[1])
            continue
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
    one command-shaped token is that token (``specy-road `frob` --flag``). Mandatory
    contexts beat the noun-phrase exclusion; see ``docs/install-and-usage.md``.
    """
    return [
        mention for _, mention in _occurrences(list(enumerate(text.splitlines(), 1)))
    ]


def warn_unregistered_commands(root: Path) -> None:
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
        for lineno, mention in _occurrences(agent_file_lines_outside_block(text)):
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
