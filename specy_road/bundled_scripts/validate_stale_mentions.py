"""Line scanning for stale command mentions (used by ``validate_stale_commands``)."""

from __future__ import annotations

import re

from specy_road.bundled_scripts.validate_stale_commands import (
    _MENTION,
    _code_spans,
    _reports,
    _span_command_token,
)

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


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
