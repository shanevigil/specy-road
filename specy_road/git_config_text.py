"""git config files read as git reads them, without running git (M21.7).

The post-run check reads a worker's git config before any post-turn git command may run (a changed
``core.fsmonitor`` would run under it), so it parses the files itself. The rule is git-config(1)'s syntax: an optional
UTF-8 byte-order mark first, ``[section]``, ``[section "subsection"]`` (backslash escapes, case kept) and the deprecated ``[section.sub]``
(folded); key names folded to lower case; a key with no ``=`` is ``true``; in a value, surrounding whitespace is
dropped and inner whitespace kept, ``"`` toggles quoting, ``#`` and ``;`` start a comment outside quotes, ``\\``
escapes ``"``, ``\\``, ``n``, ``t`` and ``b`` and joins a line it ends. ``include.path`` and every
``includeIf.<condition>.path`` are followed, conditions not evaluated, to git's depth of 10; a relative path is
relative to the including file, ``~`` is expanded. A malformed line is skipped, where git would refuse the file.

The parser is not what decides coverage. At the turn's start, before the executor acts, :func:`git_reads` asks git
itself which hooks directory it uses and which config files it reads (includes and their conditions evaluated);
those are watched whatever this parser makes of the files. After the turn only files are read: each watched config
file's change is reported by the digest of its bytes, and the parser only adds candidates (the default hooks
directories, every ``core.hooksPath`` value and every include it finds). Its limit: a directory or file git would
use only because of a change made during the turn is not watched itself; that change is, by its file's digest.

Split from :mod:`specy_road.steering_paths` for the file limit.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from specy_road.git_subprocess import run
from specy_road.runtime_paths import git_path

#: git's own include depth limit.
MAX_INCLUDE_DEPTH = 10
_ESCAPES = {"n": "\n", "t": "\t", "b": "\b"}


def _eol(text: str, i: int) -> int:
    j = text.find("\n", i)
    return len(text) if j < 0 else j + 1


def _section(text: str, i: int) -> tuple[str, int]:
    """The section header starting after ``[`` at ``i``: its folded name and the index after ``]``."""
    n, j = len(text), i
    while j < n and text[j] not in ' \t"]\n':
        j += 1
    name, sub = text[i:j].lower(), None
    while j < n and text[j] in " \t":
        j += 1
    if j < n and text[j] == '"':
        buf, j = [], j + 1
        while j < n and text[j] not in '"\n':
            j += text[j] == "\\" and j + 1 < n
            buf.append(text[j])
            j += 1
        sub = "".join(buf)
    end = text.find("]", j)
    return (f"{name}.{sub}" if sub is not None else name), (n if end < 0 else end + 1)


def _value(text: str, i: int) -> tuple[str, int]:
    """The value starting at ``i`` (after ``=``) and the index after its line."""
    buf: list[str] = []
    quote, space, n = False, 0, len(text)
    while i < n and text[i] != "\n":
        c = text[i]
        if not quote and c in "#;":
            break
        if not quote and c in " \t\r":
            space += bool(buf)
            i += 1
            continue
        buf.append(" " * space)
        space = 0
        if c == "\\" and i + 1 < n:
            nxt = text[i + 1]
            buf.append("" if nxt == "\n" else _ESCAPES.get(nxt, nxt))
            i += 2
        else:
            quote ^= c == '"'
            buf.append("" if c == '"' else c)
            i += 1
    return "".join(buf), _eol(text, i)


def parse_config(text: str) -> list[tuple[str, str]]:
    """``(key, value)`` per variable, in file order; ``key`` is ``section[.subsection].name``."""
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")   # git skips a UTF-8 BOM and reads CRLF as LF
    out: list[tuple[str, str]] = []
    section, i, n = "", 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "#;":
            i = _eol(text, i)
        elif c == "[":
            section, i = _section(text, i + 1)
        else:
            j = i
            while j < n and (text[j].isalnum() or text[j] == "-"):
                j += 1
            k = j
            while k < n and text[k] in " \t":
                k += 1
            name = text[i:j].lower()
            value, i = _value(text, k + 1) if k < n and text[k] == "=" else ("true", _eol(text, k))
            if name:
                out.append((f"{section}.{name}", value))
    return out


def _includes(pairs: list[tuple[str, str]]) -> list[str]:
    return [v for k, v in pairs if k == "include.path" or (k.startswith("includeif.") and k.endswith(".path"))]


def read_chain(path: Path, read: Callable[[Path], bytes] = Path.read_bytes,
               depth: int = 0) -> list[tuple[Path, bytes | Exception, list[tuple[str, str]]]]:
    """``(file, bytes, pairs)`` for ``path`` and every file it includes, depth first. A file that does not exist
    is left out, as git leaves out a missing include; one that cannot be read is listed with the exception in
    place of its bytes (the caller reports it), and the rest of the chain is still read."""
    try:
        data = read(path)
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001 — reported by the caller, never fatal
        return [(path, e, [])]
    pairs = parse_config(data.decode("utf-8", "replace"))
    out: list[tuple[Path, bytes | Exception, list[tuple[str, str]]]] = [(path, data, pairs)]
    if depth < MAX_INCLUDE_DEPTH:
        for inc in _includes(pairs):
            out += read_chain(path.parent / os.path.expanduser(inc), read, depth + 1)
    return out


def git_reads(top: Path) -> tuple[list[Path], list[Path]]:
    """``(hooks directories, config files)`` git uses in the checkout at ``top``, asked of git itself: run only
    at a turn's start, before the executor acts (``rev-parse --git-path hooks``; ``config --list --show-origin
    --includes``, whose origins are the files read, global and system ones included)."""
    hooks = git_path(["rev-parse", "--path-format=absolute", "--git-path", "hooks"], top)
    r = run(["config", "--list", "--show-origin", "--includes", "--name-only", "-z"], top)
    origins = r.out.split("\0")[0::2] if r.ok else []
    files = [top / os.path.expanduser(o.removeprefix("file:")) for o in origins if o.startswith("file:")]
    return ([hooks] if hooks else []), list(dict.fromkeys(files))
