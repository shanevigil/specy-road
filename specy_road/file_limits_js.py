"""Function line spans for TypeScript and JavaScript sources (``file-limits``).

Masks comments, strings, templates and regexes, then balances brackets. It
measures ``function`` declarations, ``const`` / ``let`` / ``var`` arrows and
class methods. ``.jsx`` / ``.tsx`` JSX text is blanked first, so ``<p>Don't</p>``
does not open a string. Out of scope (see ``docs/file-limits.md``): non-ASCII
identifiers, and a bodiless overload that has no terminating semicolon.
"""

from __future__ import annotations

import bisect
import re
from pathlib import Path

from specy_road.file_limits_js_mask import _ch, _quoted_end, _ws, mask_source
from specy_road.file_limits_jsx import blank_jsx_text

JS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs"})

_IDENT = r"[A-Za-z_$][\w$]*"
_IDENT_RE = re.compile(_IDENT)
_NOT_AFTER = r"(?<![\w$.#])"
_DECL_RE = re.compile(rf"{_NOT_AFTER}function\b\s*\*?\s*({_IDENT})")
_BINDING_RE = re.compile(rf"{_NOT_AFTER}(?:const|let|var)\s+")
_CLASS_RE = re.compile(rf"{_NOT_AFTER}class\b(?:\s+({_IDENT}))?")
_MEMBER_RE = re.compile(
    r"(?:(?:public|private|protected|static|async|readonly|override|abstract"
    rf"|accessor|get|set)\s+)*(?:\*\s*)?(?:(#?{_IDENT}|\d[\w.]*)|([\[\"]))"
)
_OPTIONAL_RE = re.compile(r"\s*\??\s*")
_ASYNC_RE = re.compile(r"async\b\s*")
# A concise arrow body goes on past a line break when the line ends with, or
# the next one starts with, one of these.
_CONTINUES_AFTER = frozenset("=+-*/%&|^!~<>?:,.")
_CONTINUES_BEFORE = frozenset("=+-*/%&|^<>?:.")
_BRACKET_RE = re.compile(r"[()\[\]{}]")
_WORD_CHAR_RE = re.compile(r"[\w$.#]")
_OPEN = "([{"


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
    """Index of ``stop`` (``=>``, ``=``/``,`` or a body ``{``) after a type annotation at ``j``."""
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
        elif stop == "=" and s[j] in "=,":
            return j  # `,` ends a declarator's annotation that has no initializer
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
    """Where an arrow function's body starts, if the value at ``j`` is one."""
    j = _ws(s, j)
    if m := _ASYNC_RE.match(s, j):
        j = m.end()
    if _ch(s, j) == "<":
        j = _ws(s, _angles_end(s, j))
    if _ch(s, j) == "(":
        # `((x) => body)` is grouped; `(x) => body` is the parameter list.
        close, inner = _close(s, j), _arrow_body(s, j + 1)
        if inner is not None and inner < close and not s.startswith("=>", _ws(s, close + 1)):
            return inner
        j = close + 1
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
    return j if j < len(s) else None


def _type_args_end(s: str, j: int) -> int | None:
    """Index just past the type arguments at ``j`` (``Map<string, number>``); None for a comparison.

    A comparison's ``<`` can pair with a later ``>`` (``a < b, f = () => c > d``).
    That span holds ``=`` outside ``=>``. A type-argument list does not, even when
    it holds a balanced ``{…}`` (``Map<{ id: string }, number>``).
    """
    end = _angles_end(s, j)
    span = s[j:end].replace("=>", "")
    if end >= len(s) or any(c in span for c in ";="):
        return None
    return end


def _body_end(s: str, j: int) -> int:
    """Index of the last character of the expression or function body starting at ``j``."""
    if s[j] == "{":
        return _close(s, j)
    last = j
    while j < len(s):
        c = s[j]
        if c in _OPEN:
            last = j = _close(s, j)
        elif c == "<" and (end := _type_args_end(s, j)) is not None:
            last, j = end - 1, end
            continue
        elif c in ";,)]}":
            break
        elif c == "\n":
            k = _ws(s, j)
            if _ch(s, last) not in _CONTINUES_AFTER and _ch(s, k) not in _CONTINUES_BEFORE:
                break
            j = k
            continue
        elif not c.isspace():
            last = j
        j += 1
    return min(last, len(s) - 1)


def _declarators(s: str, j: int) -> list[tuple[int, int, str]]:
    """Arrow-valued declarators of the ``const`` / ``let`` / ``var`` list starting at ``j``."""
    found: list[tuple[int, int, str]] = []
    while True:
        name = None
        if _ch(s, j) in "[{":  # a destructuring pattern names no function
            k = _ws(s, _close(s, j) + 1)
        elif name := _IDENT_RE.match(s, j):
            k = _ws(s, name.end())
        else:
            break
        if _ch(s, k) == ":" and (k := _type_end(s, k + 1, "=")) is None:
            break
        if _ch(s, k) == "=":
            init = _ws(s, k + 1)
            body = _arrow_body(s, init)
            start = init if body is None else body
            if start >= len(s):
                break
            end = _body_end(s, start)
            if body is not None and name is not None:
                found.append((name.start(), end, name.group()))
            k = _ws(s, end + 1)
            # `(x => x + 1), next`: the body ends at the group, the comma is after it.
            # `(x) => x + 1, next` is a parameter list; its body starts past that `(`.
            if body is not None and _ch(s, init) == "(" and body < _close(s, init):
                k = _ws(s, _close(s, init) + 1)
        if _ch(s, k) != ",":
            break
        j = _ws(s, k + 1)
    return found


def _class_members(s: str, src: str, j: int, close: int) -> list[tuple[int, int, str]]:
    """Methods and arrow-valued fields at the top level of a class body.

    A computed or string name (``[Symbol.iterator]``, ``'my-key'``) is reported as
    its source text on one line.
    """
    found: list[tuple[int, int, str]] = []
    while j < close:
        m = None if _WORD_CHAR_RE.match(_ch(s, j - 1)) else _MEMBER_RE.match(s, j)
        if m is None:
            j = _close(s, j) + 1 if s[j] in _OPEN else j + 1
            continue
        if m.group(1):
            name, k = m.group(1), m.end()
        else:
            a = m.start(2)
            k = _close(s, a) + 1 if s[a] == "[" else _quoted_end(src, a)
            name = " ".join(src[a:k].split())
        k = _OPTIONAL_RE.match(s, k).end()
        if _ch(s, k) == ":":  # `name: (x) => T = (x) => …` keeps `name`, not `T`
            k = _type_end(s, k + 1, "=") or k
        if _ch(s, k) == "=":
            body = _arrow_body(s, k + 1)
        else:
            p = _params_end(s, k)
            body = None if p is None else _decl_body(s, p)
        if body is None:
            j = k
            continue
        end = _body_end(s, body)
        found.append((m.start(), end, name))
        j = end + 1
    return found


def _spans(s: str, src: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """``(start, end, name)`` for every function, and every named class, in ``s`` (masked ``src``)."""
    funcs: list[tuple[int, int, str]] = []
    classes: list[tuple[int, int, str]] = []
    for m in _DECL_RE.finditer(s):
        p = _params_end(s, m.end())
        body = None if p is None else _decl_body(s, p)
        if body is not None:
            funcs.append((m.start(), _close(s, body), m.group(1)))
    for m in _BINDING_RE.finditer(s):
        funcs.extend(_declarators(s, m.end()))
    for m in _CLASS_RE.finditer(s):
        # Past type parameters (`<T extends { id: string }>`) and the heritage clause.
        if (body := _type_end(s, m.end(), "{")) is None:
            continue
        close = _close(s, body)
        if m.group(1):
            classes.append((m.start(), close, m.group(1)))
        funcs.extend(_class_members(s, src, body + 1, close))
    return funcs, classes


def js_function_metrics(path: Path) -> list[tuple[str, int, int]]:
    """Qualified name, first line and line span for each TS/JS function in ``path``."""
    src = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix in {".jsx", ".tsx"}:
        src = blank_jsx_text(src)
    s = mask_source(src)
    funcs, classes = _spans(s, src)
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
