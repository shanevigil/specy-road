"""Function line spans for TypeScript and JavaScript sources (``file-limits``).

The stdlib has no TS/JS parser, so this masks out comments, strings and
template literals, then balances brackets on what is left. It measures three
forms: ``function`` declarations, arrow functions bound by ``const`` / ``let``
/ ``var``, and class methods (arrow-valued class fields included). A function
inside a class or another function is named ``Outer.inner``, as the Python
report does. Regex literals are not masked, so one holding an unpaired quote
or bracket can throw a span off.
"""

from __future__ import annotations

import bisect
import re
from pathlib import Path

JS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs"})

_IDENT = r"[A-Za-z_$][\w$]*"
_IDENT_RE = re.compile(_IDENT)
_NOT_AFTER = r"(?<![\w$.#])"
_DECL_RE = re.compile(rf"{_NOT_AFTER}function\b\s*\*?\s*({_IDENT})")
_BINDING_RE = re.compile(rf"{_NOT_AFTER}(?:const|let|var)\s+({_IDENT})")
_CLASS_RE = re.compile(rf"{_NOT_AFTER}class\b(?:\s+({_IDENT}))?[^{{;]*\{{")
_MEMBER_RE = re.compile(
    r"(?:(?:public|private|protected|static|async|readonly|override|abstract"
    rf"|accessor|get|set)\s+)*(?:\*\s*)?(#?{_IDENT})\s*\??\s*"
)
_ASYNC_RE = re.compile(r"async\b\s*")
_LITERAL_START_RE = re.compile(r"//|/\*|['\"`]")
_BRACKET_RE = re.compile(r"[()\[\]{}]")
_WS_RE = re.compile(r"\s*")
_NOT_NEWLINE_RE = re.compile(r"[^\n]")
_WORD_CHAR_RE = re.compile(r"[\w$.#]")
_OPEN = "([{"


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


def mask_source(src: str) -> str:
    """``src`` with comments, strings and template literals blanked, newlines kept."""
    out: list[str] = []
    i = 0
    while (m := _LITERAL_START_RE.search(src, i)) is not None:
        out.append(src[i : m.start()])
        i = _literal_end(src, m.start())
        out.append(_NOT_NEWLINE_RE.sub(" ", src[m.start() : i]))
    out.append(src[i:])
    return "".join(out)


def _close(s: str, i: int) -> int:
    """Index of the bracket closing the one at ``i`` (``len(s)`` if unbalanced)."""
    depth = 0
    for m in _BRACKET_RE.finditer(s, i):
        depth += 1 if m.group() in _OPEN else -1
        if depth == 0:
            return m.start()
    return len(s)


def _angles_end(s: str, i: int) -> int:
    """Index just past the ``>`` closing the type parameters opened at ``i``."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "<":
            depth += 1
        elif s[j] == ">" and s[j - 1] != "=":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(s)


def _type_end(s: str, j: int, stop: str) -> int | None:
    """Index of ``stop`` (``=>``, ``=`` or a body ``{``) after a type annotation at ``j``."""
    while j < len(s):
        if s.startswith("=>", j):
            if stop == "=>":
                return j
            j += 2
        elif s[j] == "{" and stop == "{":
            # An object type goes on (`{…} | …`, `{…}[]`) or the body follows it.
            k = _ws(s, _close(s, j) + 1)
            if _ch(s, k) not in "{|&" and not s.startswith("[]", k):
                return j
            j = k
        elif s[j] == "=" and stop == "=":
            return j
        elif s[j] in _OPEN:
            j = _close(s, j) + 1
        elif s[j] == "<":
            j = _angles_end(s, j)
        elif s[j] in ";)]}":
            return None
        else:
            j += 1
    return None


def _params_end(s: str, j: int) -> int | None:
    """Index just past the parameter list (after optional type parameters) at ``j``."""
    j = _ws(s, j)
    if _ch(s, j) == "<":
        j = _ws(s, _angles_end(s, j))
    return _close(s, j) + 1 if _ch(s, j) == "(" else None


def _decl_body(s: str, j: int) -> int | None:
    """The ``{`` opening the body after a parameter list ending at ``j``; None if bodiless."""
    j = _ws(s, j)
    if _ch(s, j) == ":":
        return _type_end(s, j + 1, "{")
    return j if _ch(s, j) == "{" else None


def _arrow_body(s: str, j: int) -> int | None:
    """The ``{`` or ``(`` opening an arrow function's body, if the value at ``j`` is one."""
    j = _ws(s, j)
    if m := _ASYNC_RE.match(s, j):
        j = m.end()
    if _ch(s, j) == "<":
        j = _ws(s, _angles_end(s, j))
    if _ch(s, j) == "(":
        j = _close(s, j) + 1
    elif m := _IDENT_RE.match(s, j):
        j = m.end()
    else:
        return None
    j = _ws(s, j)
    if _ch(s, j) == ":" and (j := _type_end(s, j + 1, "=>")) is None:
        return None
    if not s.startswith("=>", j):
        return None
    j = _ws(s, j + 2)
    return j if _ch(s, j) in ("{", "(") else None


def _class_members(s: str, j: int, close: int) -> list[tuple[int, int, str]]:
    """Methods and arrow-valued fields at the top level of a class body."""
    found: list[tuple[int, int, str]] = []
    while j < close:
        if s[j] in _OPEN:
            j = _close(s, j) + 1
            continue
        m = None if _WORD_CHAR_RE.match(_ch(s, j - 1)) else _MEMBER_RE.match(s, j)
        if m is None:
            j += 1
            continue
        k = m.end()
        if _ch(s, k) == "=":
            body = _arrow_body(s, k + 1)
        else:
            p = _params_end(s, k)
            body = None if p is None else _decl_body(s, p)
        if body is None:
            j = k
            continue
        end = _close(s, body)
        found.append((m.start(), end, m.group(1)))
        j = end + 1
    return found


def _spans(s: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """``(start, end, name)`` for every function, and for every named class, in ``s``."""
    funcs: list[tuple[int, int, str]] = []
    classes: list[tuple[int, int, str]] = []
    for m in _DECL_RE.finditer(s):
        p = _params_end(s, m.end())
        body = None if p is None else _decl_body(s, p)
        if body is not None:
            funcs.append((m.start(), _close(s, body), m.group(1)))
    for m in _BINDING_RE.finditer(s):
        j = _ws(s, m.end())
        if _ch(s, j) == ":":
            j = _type_end(s, j + 1, "=")
        body = _arrow_body(s, j + 1) if j is not None and _ch(s, j) == "=" else None
        if body is not None:
            funcs.append((m.start(), _close(s, body), m.group(1)))
    for m in _CLASS_RE.finditer(s):
        close = _close(s, m.end() - 1)
        if m.group(1):
            classes.append((m.start(), close, m.group(1)))
        funcs.extend(_class_members(s, m.end(), close))
    return funcs, classes


def js_function_metrics(path: Path) -> list[tuple[str, int, int]]:
    """Qualified name, first line and line span for each TS/JS function in ``path``."""
    s = mask_source(path.read_text(encoding="utf-8", errors="replace"))
    funcs, classes = _spans(s)
    line_starts = [0, *(m.end() for m in re.finditer("\n", s))]

    def line(pos: int) -> int:
        return bisect.bisect_right(line_starts, pos)

    scopes = sorted(funcs + classes)
    found: list[tuple[str, int, int]] = []
    for start, end, name in sorted(funcs):
        outer = [n for a, b, n in scopes if a < start and end <= b]
        first = line(start)
        found.append((".".join([*outer, name]), first, line(end) - first + 1))
    return found
