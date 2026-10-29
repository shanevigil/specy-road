"""Literal masking for the TS/JS function scan (``file-limits``).

Comments are blanked and strings, template literals and regex literals are
reduced to ``"`` so their brackets are not counted. Every literal keeps its
length and newlines, so offsets and line numbers still match the source.
"""

from __future__ import annotations

import re

_LITERAL_START_RE = re.compile(r"[/'\"`]")
# A `/` starts a regex after these, not a division. `<` is left out so a JSX
# closing tag (`</div>`) is not read as one.
_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%>~^")
_REGEX_AFTER_WORDS = frozenset(
    {"return", "typeof", "instanceof", "case", "do", "else", "in", "of", "new",
     "delete", "void", "throw", "yield", "await"}
)
_TRAILING_WORD_RE = re.compile(r"[\w$]+$")
_REGEX_FLAGS_RE = re.compile(r"[A-Za-z]*")
_WS_RE = re.compile(r"\s*")
_NOT_NEWLINE_RE = re.compile(r"[^\n]")


def _ch(s: str, j: int) -> str:
    return s[j] if 0 <= j < len(s) else "\0"


def _ws(s: str, j: int) -> int:
    return _WS_RE.match(s, min(j, len(s))).end()


def _literal_end(src: str, i: int) -> int | None:
    """End of the comment, string or template literal starting at ``i``, if one does."""
    if src.startswith("//", i):
        j = src.find("\n", i)
        return len(src) if j < 0 else j
    if src.startswith("/*", i):
        j = src.find("*/", i + 2)
        return len(src) if j < 0 else j + 2
    if src[i] in "'\"":
        return _quoted_end(src, i)
    if src[i] == "`":
        return _template_end(src, i)
    return None


def _quoted_end(src: str, i: int) -> int:
    j = i + 1
    while j < len(src):
        if src[j] == "\\":
            j += 2
        elif src[j] == src[i]:
            return j + 1
        elif src[j] == "\n":  # unterminated: stop at the line end
            return j
        else:
            j += 1
    return len(src)


def _template_end(src: str, i: int) -> int:
    j = i + 1
    while j < len(src):
        if src[j] == "\\":
            j += 2
        elif src[j] == "`":
            return j + 1
        elif src.startswith("${", j):
            j = _expr_end(src, j + 1)
        else:
            j += 1
    return len(src)


def _expr_end(src: str, i: int) -> int:
    """Index just past the ``}`` closing the ``${`` expression whose ``{`` is at ``i``."""
    depth = 0
    j = i
    while j < len(src):
        end = _literal_end(src, j)
        if end is not None:
            j = end
            continue
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(src)


def _regex_allowed(src: str, prev: int, i: int) -> bool:
    """Whether the ``/`` at ``i`` opens a regex, ``prev`` being the last significant code index."""
    if _ch(src, i + 1) == ">":  # `/>` closes a JSX tag
        return False
    if prev < 0 or "\n" in src[prev:i] or src[prev] in _REGEX_AFTER:
        return True
    word = _TRAILING_WORD_RE.search(src, max(0, prev - 11), prev + 1)
    return word is not None and word.group() in _REGEX_AFTER_WORDS


def _regex_end(src: str, i: int) -> int | None:
    """End of the regex literal at ``i`` (flags included); None if the line ends first."""
    j = i + 1
    in_class = False
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "\n":
            return None
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "/":
            return _REGEX_FLAGS_RE.match(src, j + 1).end()
        j += 1
    return None


def mask_source(src: str) -> str:
    """``src`` with comments blanked and strings, templates and regexes reduced to ``"``.

    Every literal keeps its length and newlines, so offsets and line numbers
    still match ``src``.
    """
    out: list[str] = []
    i = 0
    prev = -1  # last significant code index; comments do not count
    while (m := _LITERAL_START_RE.search(src, i)) is not None:
        start = m.start()
        code = src[i:start]
        if code.strip():
            prev = i + len(code.rstrip()) - 1
        out.append(code)
        end = _literal_end(src, start)
        if end is None and _regex_allowed(src, prev, start):
            end = _regex_end(src, start)
        if end is None:  # a division
            out.append("/")
            prev, i = start, start + 1
            continue
        blank = _NOT_NEWLINE_RE.sub(" ", src[start:end])
        if not src.startswith(("//", "/*"), start):
            # A `"` stands in for the literal, so it still reads as an operand.
            blank = '"' + blank[1:]
            prev = end - 1
        out.append(blank)
        i = end
    out.append(src[i:])
    return "".join(out)
