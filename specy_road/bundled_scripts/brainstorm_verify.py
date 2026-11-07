"""``brainstorm verify``: check that each recorded quote appears on its page.

The one place the CLI touches the network, and it asks first: the URLs are
listed and the user confirms before the first request (``--yes`` answers for
scripts; non-interactive without it fetches nothing). Fetching a known URL
to check a quote is neither a model call nor a search; the guards are the
GUI research module's — public hosts only, a timeout, a size cap. A fetch
that fails records ``blocked``, never "fabricated": a paywall is not a lie.
A 404 or 410 is ``blocked`` when that origin's root is not 200 (or cannot be
fetched) and ``not-found`` when the root is. The root is https, the host as a
URL spells it (an IPv6 literal in brackets), the port when it is not 443,
fetched once per origin per run.
The connection is made to the address the host was checked at, with the
hostname kept for SNI and certificate checking, so a rebinding name cannot
move a hop onto a private address after the check.

A ``repo`` source is checked without the network and without asking: the
quote must appear in the cited file as it stood at the recorded commit
(``git show``), on a span that covers the cited line when one was given.
A search that found nothing has no quote and nothing to check.
"""

from __future__ import annotations

import re
import sys
from bisect import bisect_right
from collections.abc import Callable
from html import unescape
from pathlib import Path
from typing import Any

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlunsplit, urlsplit

from specy_road.bundled_scripts.brainstorm_research import _is_off_host  # noqa: PLC2701 — same guard as the GUI
from specy_road.bundled_scripts.brainstorm_fields import REPO, is_no_result
from specy_road.bundled_scripts.brainstorm_session import BrainstormError, BrainstormSession, Idea
from specy_road.git_subprocess import git_ok, git_stdout, git_text, head_sha
from specy_road.runtime_paths import git_root

TIMEOUT_SECONDS = 20
MAX_BYTES = 2_000_000
Fetcher = Callable[[str], tuple[int, str]]
#: Inline elements sit inside running text, so removing one must not put a
#: space into a word or before the punctuation that follows it; other tags
#: (paragraphs, cells, line breaks) do separate words.
_INLINE_TAGS = re.compile(
    r"</?(?:a|abbr|b|bdi|bdo|cite|code|data|del|dfn|em|font|i|ins|kbd|mark|q|s|samp|small"
    r"|span|strong|sub|sup|time|u|var)(?:\s[^>]*)?/?>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
#: A space before closing or after opening punctuation, dropped on both sides alike.
_PUNCT_SPACE = re.compile(r" (?=[.,;:!?)\]])|(?<=[(\[]) ")
#: A page's reference markers ("restudying[43] while"), which an agent's copy of the sentence leaves out.
_CITATION = re.compile(r"\[(?:\d+|[a-z]|note \d+|citation needed)\]", re.IGNORECASE)
#: Typographic quotes, dashes and spaces to their ASCII form; soft hyphens and zero-width characters removed.
_FOLD = str.maketrans({
    **dict.fromkeys("\u2018\u2019\u201a\u2032", "'"),
    **dict.fromkeys("\u201c\u201d\u201e\u2033", '"'),
    **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"),
    **dict.fromkeys("\u00a0\u202f\u2009", " "),
    **dict.fromkeys("\u00ad\u200b\u200c\u200d\u2060\ufeff"),
})


def _norm(text: str) -> str:
    text = unescape(_TAGS.sub(" ", _INLINE_TAGS.sub("", text)))
    text = _CITATION.sub("", text).translate(_FOLD)
    return _PUNCT_SPACE.sub("", _WS.sub(" ", text).strip().lower())


MAX_REDIRECTS = 5


def _public_address(host: str) -> str | None:
    """One public address ``host`` resolves to, or ``None`` when any answer is off-host.

    The address returned is the one the connection is made to: the name is
    not resolved a second time, so a name that answers differently on the
    next lookup (DNS rebinding) cannot move the fetch onto a private host.
    """
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return None
    addrs = []
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return None
        if not addr.is_global:
            return None
        addrs.append(str(addr))
    return addrs[0] if addrs else None


class _PinnedHTTPS(http.client.HTTPSConnection):
    """TLS to a chosen address, with the hostname kept for SNI and certificate checking."""

    def __init__(self, host: str, address: str, port: int) -> None:
        super().__init__(host, port, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
        self._pinned = address

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _fetch_once(url: str) -> tuple[int, str | None, bytes]:
    """``(status, redirect location, body)`` for one request to the address the host was checked at."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    address = _public_address(host)
    if address is None:
        raise ValueError(f"refusing {url}: not a public host")
    conn = _PinnedHTTPS(host, address, parts.port or 443)
    try:
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        conn.request("GET", path, headers={"User-Agent": "specy-road brainstorm verify", "Host": host})
        r = conn.getresponse()
        body = b""
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            if len(body) + len(chunk) > MAX_BYTES:
                raise ValueError(f"page larger than {MAX_BYTES} bytes; not verified")   # → blocked
            body += chunk
        return r.status, r.getheader("Location"), body
    finally:
        conn.close()


def default_fetch(url: str) -> tuple[int, str]:
    """``(status, text)``; raises on transport errors.

    Redirects are followed by hand so that every hop passes the same
    public-https check as the first URL, and each hop connects to the
    address it was checked at: a page the user approved must not redirect
    or re-resolve the fetch onto a private host.
    """
    for _hop in range(MAX_REDIRECTS + 1):
        if _allowed(url):
            raise ValueError(f"refusing {url}: {_allowed(url)}")
        status, location, body = _fetch_once(url)
        if status in (301, 302, 303, 307, 308):
            if not location:
                return status, ""
            url = urljoin(url, location)
            continue
        return status, body.decode("utf-8", errors="replace")
    raise ValueError("too many redirects")


def _allowed(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        return "not https"
    if not parts.hostname or _is_off_host(parts.hostname):
        return "not a public host"
    return None


def split_path(cited: str) -> tuple[str, int | None]:
    """``file:line`` -> ``(file, line)``; a path with no line number cites the whole file."""
    path, sep, line = cited.strip().rpartition(":")
    return (path, int(line)) if sep and path and line.isdigit() and int(line) > 0 else (cited.strip(), None)


def _blob(root: Path, commit: str, path: str) -> tuple[Path, str]:
    """Where to run git, and the object name, for ``path`` at ``commit``.

    A repo source's path is relative to the **git** root, which in a nested
    layout (a project under ``sr/``) sits above the project root, so a file
    outside the project can be cited. Git runs there and the name carries no
    ``./``, which git would resolve against its working directory instead.
    """
    return git_root(root) or root, f"{commit}:{path.removeprefix('./')}"


def repo_commit(root: Path, cited: str) -> str:
    """The ``HEAD`` commit a repo source records; refuses a path that commit does not hold as a file."""
    path, _line = split_path(cited)
    commit = head_sha(root)
    if not path or commit is None:
        raise BrainstormError("--path FILE[:LINE] needs a git checkout with a commit to cite")
    top, name = _blob(root, commit, path)
    kind = git_text(["cat-file", "-t", name], top)
    if kind is None:
        raise BrainstormError(f"--path {path}: not in the HEAD commit {commit[:12]}; "
                              "commit it first so verify can check the quote against it (the path is "
                              "relative to the git root)")
    if kind != "blob":
        raise BrainstormError(f"--path {path}: a {kind} in the HEAD commit, not a file; cite a file")
    return commit


def quote_in_file(text: str, quote: str, line: int | None) -> bool:
    """Whether ``quote`` (whitespace collapsed) appears in ``text`` on a span that covers ``line``."""
    # Non-blank lines joined by one space (a quote may span a blank line), with each one's offset and number.
    kept = [(n, flat) for n, raw in enumerate(text.splitlines(), 1) if (flat := _WS.sub(" ", raw).strip())]
    starts, pos = [], 0
    for _n, flat in kept:
        starts.append(pos)
        pos += len(flat) + 1
    numbers = [n for n, _flat in kept]
    joined, want = " ".join(flat for _n, flat in kept), _WS.sub(" ", quote).strip()
    at = joined.find(want) if want else -1
    while at >= 0:
        first = numbers[bisect_right(starts, at) - 1]
        last = numbers[bisect_right(starts, at + len(want) - 1) - 1]
        if line is None or first <= line <= last:
            return True
        at = joined.find(want, at + 1)
    return False


def check_repo_source(source: dict[str, Any], root: Path | None) -> str:
    """A repo source's state, read from its commit with no network.

    ``not-found`` when the commit holds no file at the path (a directory is not
    one); ``blocked`` when the commit is gone or the file cannot be read as text.
    """
    path, line = split_path(str(source.get("path", "")))
    commit = str(source.get("commit", ""))
    if root is None or not commit or not git_ok(["cat-file", "-e", f"{commit}^{{commit}}"], root)[0]:
        return "blocked"
    top, name = _blob(root, commit, path)
    if git_text(["cat-file", "-t", name], top) != "blob":
        return "not-found"
    text = git_stdout(["cat-file", "blob", name], top)
    if text is None:   # the file is there but did not read, e.g. not UTF-8: not evidence against the quote
        return "blocked"
    return "matched" if quote_in_file(text, str(source.get("quote", "")), line) else "not-found"


def is_local(source: dict[str, Any]) -> bool:
    """A source verify checks in this repository, without asking or fetching."""
    return source.get("source_type") == REPO


def _root_url(url: str) -> str:
    """Origin root of ``url``: https, the host as a URL spells it, effective port, path ``/``.

    A hostname containing ``:`` is an IPv6 literal and is written in brackets; any other host is
    written as itself. Port 443 is omitted, so an explicit ``:443`` is the same origin as none.
    Userinfo, query and fragment are dropped. A zone id in the hostname is retained, so
    ``https://[fe80::1%25eth0]/a`` has root ``https://[fe80::1%25eth0]/``.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    host = f"[{host}]" if ":" in host else host
    port = parts.port
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return urlunsplit(("https", netloc, "/", "", ""))


_ASK_ROOT = frozenset({404, 410})
_BLOCKED_STATUS = frozenset({401, 403, 429})


def _non_200(status: int, url: str, fetch: Fetcher, roots: dict[str, bool] | None) -> str:
    """State for a page that is not 200. 404 and 410 follow the origin root; 401, 403 and 429 are blocked."""
    if status in _ASK_ROOT:
        cache = roots if roots is not None else {}
        return "not-found" if host_answers(url, fetch, cache) else "blocked"
    return "blocked" if status in _BLOCKED_STATUS else "not-found"


def host_answers(url: str, fetch: Fetcher, roots: dict[str, bool]) -> bool:
    """Whether ``url``'s origin returns 200 for ``/``; one fetch per origin, stored in ``roots``.

    The origin is ``_root_url``. Any status but 200, or a fetch that fails, means the host refuses verify.
    """
    root = _root_url(url)
    if root not in roots:
        try:
            status, _text = fetch(root)
        except Exception:  # noqa: BLE001 — a root that cannot be fetched was not checked
            roots[root] = False
        else:
            roots[root] = status == 200
    return roots[root]


def check_source(source: dict[str, Any], fetch: Fetcher, *, root: Path | None = None,
                 roots: dict[str, bool] | None = None) -> str:
    """The verification state for one source after a fetch, or after a local read of a repo source.

    ``roots`` remembers, for one verify run, whether each origin answered 200 at ``/``.
    """
    if is_local(source):
        return check_repo_source(source, root)
    url = str(source.get("url", ""))
    why = _allowed(url)
    if why:
        return "blocked"
    try:
        status, text = fetch(url)
    except Exception:  # noqa: BLE001 — any transport failure is "blocked"
        return "blocked"
    if status != 200:
        return _non_200(status, url, fetch, roots)
    quote = _norm(str(source.get("quote", "")))
    # No quote, nothing to find: a URL alone is not evidence (docs/brainstorming.md).
    return "matched" if quote and quote in _norm(text) else "not-found"


def pending(ideas: list[Idea]) -> list[tuple[Idea, dict[str, Any]]]:
    """Unverified sources; a search that found nothing has no quote to check, so it is never pending."""
    return [(i, s) for i in ideas for s in i.sources
            if s.get("verification", "unverified") == "unverified" and not is_no_result(s)]


def confirm(urls: list[str], *, yes: bool, stdin=None, out=None) -> bool:
    """List the URLs and ask; the CLI's only network call is always a visible one."""
    out = out or sys.stdout
    stdin = stdin or sys.stdin
    print(f"verify would fetch {len(urls)} URL(s):", file=out)
    for u in urls:
        print(f"  {u}", file=out)
    if yes:
        return True
    if not stdin.isatty():
        print("not a terminal: pass --yes to allow the fetch; nothing was fetched", file=out)
        return False
    answer = input("Fetch them now? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def verify_session(session: BrainstormSession, ideas: list[Idea], *, fetch: Fetcher | None = None,
                   root: Path | None = None, web: bool = True) -> list[str]:
    """Verify every unverified source on ``ideas`` (only the repo ones unless ``web``); one report line each."""
    fetch = fetch or default_fetch   # resolved at call time so tests can swap it
    roots: dict[str, bool] = {}
    lines = []
    for idea, src in pending(ideas):
        if not (web or is_local(src)):
            continue
        src["verification"] = check_source(src, fetch, root=root, roots=roots)
        lines.append(f"{idea.id} {src['verification']:<10} {src.get('url')}")
    return lines
