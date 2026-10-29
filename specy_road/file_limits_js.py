"""Function line spans for TypeScript and JavaScript sources (``file-limits``).

The stdlib has no TS/JS parser, so this masks out comments, strings, template
literals and regex literals, then balances brackets on what is left. It
measures three forms: ``function`` declarations, arrow functions bound by
``const`` / ``let`` / ``var``, and class methods (arrow-valued class fields
included). A concise arrow body runs to its terminating ``;``, ``,`` or
closing bracket, or to a line break the next line does not continue. A
function inside a class or another function is named ``Outer.inner``, as the
Python report does.
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
_BINDING_RE = re.compile(rf"{_NOT_AFTER}(?:const|let|var)\s+")
_CLASS_RE = re.compile(rf"{_NOT_AFTER}class\b(?:\s+({_IDENT}))?")
_MEMBER_RE = re.compile(
    r"(?:(?:public|private|protected|static|async|readonly|override|abstract"
    rf"|accessor|get|set)\s+)*(?:\*\s*)?(#?{_IDENT})\s*\??\s*"
)
_ASYNC_RE = re.compile(r"async\b\s*")
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
# A concise arrow body goes on past a line break when the line ends with, or
# the next one starts with, one of these.
_CONTINUES_AFTER = frozenset("=+-*/%&|^!~<>?:,.")
_CONTINUES_BEFORE = frozenset("=+-*/%&|^<>?:.")
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
    return j if j < len(s) else None


def _body_end(s: str, j: int) -> int:
    """Index of the last character of the function body starting at ``j``."""
    if s[j] == "{":
        return _close(s, j)
    last = j
    while j < len(s):
        c = s[j]
        if c in _OPEN:
            last = j = _close(s, j)
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
            body = _arrow_body(s, k + 1)
            start = _ws(s, k + 1) if body is None else body
            if start >= len(s):
                break
            end = _body_end(s, start)
            if body is not None and name is not None:
                found.append((name.start(), end, name.group()))
            k = _ws(s, end + 1)
        if _ch(s, k) != ",":
            break
        j = _ws(s, k + 1)
    return found


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
        end = _body_end(s, body)
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
        funcs.extend(_declarators(s, m.end()))
    for m in _CLASS_RE.finditer(s):
        # Past type parameters (`<T extends { id: string }>`) and the heritage clause.
        if (body := _type_end(s, m.end(), "{")) is None:
            continue
        close = _close(s, body)
        if m.group(1):
            classes.append((m.start(), close, m.group(1)))
        funcs.extend(_class_members(s, body + 1, close))
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
