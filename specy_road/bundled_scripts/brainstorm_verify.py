"""``brainstorm verify``: check that each recorded quote appears on its page.

The one place the CLI touches the network, and it asks first: the URLs are
listed and the user confirms before the first request (``--yes`` answers for
scripts; non-interactive without it fetches nothing). Fetching a known URL
to check a quote is neither a model call nor a search; the guards are the
GUI research module's — public hosts only, a timeout, a size cap. A fetch
that fails records ``blocked``, never "fabricated": a paywall is not a lie.

Known limit: the host check resolves the name once and ``requests`` resolves
it again to connect, so a name that answers differently each time (DNS
rebinding) can reach a private address on the second lookup. TLS
certificate checking narrows what such a host can be; pinning the checked
address into the connection would close it and is not done here.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from html import unescape
from typing import Any

from urllib.parse import urlsplit

from specy_road.bundled_scripts.brainstorm_research import _is_off_host  # noqa: PLC2701 — same guard as the GUI
from specy_road.bundled_scripts.brainstorm_session import BrainstormSession, Idea

TIMEOUT_SECONDS = 20
MAX_BYTES = 2_000_000
Fetcher = Callable[[str], tuple[int, str]]
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", unescape(_TAGS.sub(" ", text))).strip().lower()


MAX_REDIRECTS = 5


def default_fetch(url: str) -> tuple[int, str]:
    """``(status, text)``; raises on transport errors.

    Redirects are followed by hand so that every hop passes the same
    public-https check as the first URL: a page the user approved must not
    redirect the fetch onto a private host.
    """
    import requests

    for _hop in range(MAX_REDIRECTS + 1):
        if _allowed(url):
            raise ValueError(f"refusing {url}: {_allowed(url)}")
        r = requests.get(url, timeout=TIMEOUT_SECONDS, stream=True, allow_redirects=False,
                         headers={"User-Agent": "specy-road brainstorm verify"})
        if r.is_redirect or r.is_permanent_redirect or r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("Location")
            if not location:
                return r.status_code, ""
            url = requests.compat.urljoin(url, location)
            continue
        body = b""
        for chunk in r.iter_content(65536):
            if len(body) + len(chunk) > MAX_BYTES:
                raise ValueError(f"page larger than {MAX_BYTES} bytes; not verified")   # → blocked
            body += chunk
        return r.status_code, body.decode(r.encoding or "utf-8", errors="replace")
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
