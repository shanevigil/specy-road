"""``brainstorm verify``: check that each recorded quote appears on its page.

The one place the CLI touches the network, and it asks first: the URLs are
listed and the user confirms before the first request (``--yes`` answers for
scripts; non-interactive without it fetches nothing). Fetching a known URL
to check a quote is neither a model call nor a search; the guards are the
GUI research module's — public hosts only, a timeout, a size cap. A fetch
that fails records ``blocked``, never "fabricated": a paywall is not a lie.
The connection is made to the address the host was checked at, with the
hostname kept for SNI and certificate checking, so a rebinding name cannot
move a hop onto a private address after the check.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from html import unescape
from typing import Any

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from specy_road.bundled_scripts.brainstorm_research import _is_off_host  # noqa: PLC2701 — same guard as the GUI
from specy_road.bundled_scripts.brainstorm_session import BrainstormSession, Idea

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


def _norm(text: str) -> str:
    text = _TAGS.sub(" ", _INLINE_TAGS.sub("", text))
    return _PUNCT_SPACE.sub("", _WS.sub(" ", unescape(text)).strip().lower())


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


def check_source(source: dict[str, Any], fetch: Fetcher) -> str:
    """The verification state for one source after a fetch."""
    url = str(source.get("url", ""))
    why = _allowed(url)
    if why:
        return "blocked"
    try:
        status, text = fetch(url)
    except Exception:  # noqa: BLE001 — any transport failure is "blocked"
        return "blocked"
    if status != 200:
        return "blocked" if status in (401, 403, 429) else "not-found"
    quote = _norm(str(source.get("quote", "")))
    # No quote, nothing to find: a URL alone is not evidence (docs/brainstorming.md).
    return "retrieved" if quote and quote in _norm(text) else "not-found"


def pending(ideas: list[Idea]) -> list[tuple[Idea, dict[str, Any]]]:
    return [(i, s) for i in ideas for s in i.sources if s.get("verification", "unverified") == "unverified"]


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


def verify_session(session: BrainstormSession, ideas: list[Idea], *, fetch: Fetcher | None = None) -> list[str]:
    """Verify every unverified source on ``ideas``; returns one report line each."""
    fetch = fetch or default_fetch   # resolved at call time so tests can swap it
    lines = []
    for idea, src in pending(ideas):
        src["verification"] = check_source(src, fetch)
        lines.append(f"{idea.id} {src['verification']:<10} {src.get('url')}")
    return lines
