"""Blank JSX text so the TS/JS function scan does not lex it as code.

An apostrophe in ``<p>Don't</p>`` is text, not a string delimiter. Attributes
and ``{…}`` expressions stay code, and JSX inside those expressions is blanked
the same way. Only ``.jsx`` and ``.tsx`` sources are passed here.
"""

from __future__ import annotations

import re

from specy_road.file_limits_js_mask import _NOT_NEWLINE_RE, _ch, _literal_end, _ws

_JSX_WORDS = frozenset({"return", "yield", "throw", "await", "else", "case", "void"})
_JSX_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
_JSX_BEFORE = frozenset("([{=,:;?&|!~+-*%^")


def _jsx_open(src: str, i: int) -> bool:
    """Whether ``<`` at ``i`` starts an element rather than a comparison or a generic."""
    n = _ch(src, i + 1)
    if n != ">" and not (n.isascii() and (n.isalpha() or n in "_$")):
        return False
    j = i - 1
    while j >= 0 and src[j].isspace():
        j -= 1
    if j < 0 or src[j] in _JSX_BEFORE or (src[j] == ">" and _ch(src, j - 1) == "="):
        return True
    k = j
    while k >= 0 and (src[k].isalnum() or src[k] in "_$"):
        k -= 1
    return src[k + 1:j + 1] in _JSX_WORDS


def _code(src: str, i: int, parts: list[str], depth: int) -> int:
    """Copy code from ``i``, blanking JSX text. At ``depth`` > 0, stop after the matching ``}``."""
    while i < len(src):
        if src[i] in "'\"`/" and (end := _literal_end(src, i)):
            parts.append(src[i:end])
            i = end
        elif src[i] == "<" and _jsx_open(src, i) and (got := _jsx_take(src, i)):
            parts.append(got[0])
            i = got[1]
        elif depth and src[i] == "}":
            parts.append("}")
            return i + 1
        elif src[i] == "{":
            parts.append("{")
            i = _code(src, i + 1, parts, depth + 1)
        else:
            parts.append(src[i])
            i += 1
    return i


def _jsx_attrs(src: str, j: int) -> tuple[str, int] | None:
    """Masked attributes from ``j`` through the tag's ``>`` or ``/>``."""
    parts: list[str] = []
    while j < len(src):
        if src[j] in "'\"`/" and (end := _literal_end(src, j)):
            parts.append(src[j:end])
            j = end
        elif src[j] == "{":
            parts.append("{")
            j = _code(src, j + 1, parts, 1)
        elif src.startswith("/>", j):
            parts.append("/>")
            return "".join(parts), j + 2
        elif src[j] == ">":
            parts.append(">")
            return "".join(parts), j + 1
        else:
            parts.append(src[j])
            j += 1
    return None


def _jsx_kids(src: str, j: int, parts: list[str]) -> int:
    """Blank text children and copy nested elements until the closing tag."""
    while j < len(src):
        if src[j] == "{":
            parts.append("{")
            j = _code(src, j + 1, parts, 1)
        elif src.startswith("</", j):
            end = src.find(">", j)
            end = len(src) if end < 0 else end + 1
            parts.append(src[j:end])
            return end
        elif src[j] == "<" and (got := _jsx_take(src, j)):
            parts.append(got[0])
            j = got[1]
        elif src[j] == "<":
            parts.append("<")
            j += 1
        else:
            end = j
            while end < len(src) and src[end] not in "<{":
                end += 1
            parts.append(_NOT_NEWLINE_RE.sub(" ", src[j:end]))
            j = end
    return j


def _jsx_take(src: str, i: int) -> tuple[str, int] | None:
    """Masked element at ``<``, or None when it is a generic (``<T,>``, ``<T extends …>``)."""
    j = i + 1
    if _ch(src, j) == "/":
        return None
    if _ch(src, j) == ">":
        parts = [src[i:j + 1]]
        end = _jsx_kids(src, j + 1, parts)
        return "".join(parts), end
    name = _JSX_NAME_RE.match(src, j)
    if name is None:
        return None
    k = _ws(src, name.end())
    if _ch(src, k) == "," or src.startswith("extends", k):
        return None
    attrs = _jsx_attrs(src, name.end())
    if attrs is None:
        return None
    text, end = attrs
    parts = [src[i:name.end()], text]
    if src.startswith("/>", end - 2):
        return "".join(parts), end
    end = _jsx_kids(src, end, parts)
    return "".join(parts), end


def blank_jsx_text(src: str) -> str:
    """``src`` with JSX text nodes replaced by spaces. Newlines and length stay put."""
    parts: list[str] = []
    _code(src, 0, parts, 0)
    return "".join(parts)
