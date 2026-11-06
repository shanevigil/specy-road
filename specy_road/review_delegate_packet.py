"""``review delegate`` builds the review packet it needs (M15.17).

``prompt --role reviewer`` reads ``work/reviews/<NODE_ID>/PACKET.md`` and refuses when it is missing. Before
starting a reviewer, :func:`ensure_packet` builds that packet (``review-packet <NODE_ID>``, :func:`build_packet`) when
it is missing or names another commit under review, prints its path and size, and lets the run proceed. A packet
that names no commit is left as it is: nothing says it is for another commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road.bundled_scripts.review_packet import build_packet
from specy_road.managed_block import refused_link
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.review_target import ReviewTarget, ReviewTargetError, same_commit

_COMMIT = re.compile(r"\*\*Commit under review:\*\*\s*`([0-9a-fA-F]{7,64})`")


def packet_commit(text: str) -> str | None:
    """The commit a packet's header names as under review, or ``None``."""
    m = _COMMIT.search(text)
    return m.group(1) if m else None


def ensure_packet(repo_root: Path, t: ReviewTarget, ref: str | None) -> Path | None:
    """Build ``PACKET.md`` for ``t``'s commit when it is missing or was built for another commit; returns the path
    built, else ``None``."""
    path = reviews_dir(repo_root, t.node_id) / PACKET_NAME
    why = refused_link(path.parent, path, any_link=True)
    if why:
        raise ReviewTargetError(f"{why}; nothing was launched")
    if path.is_file():
        named = packet_commit(path.read_text(encoding="utf-8", errors="replace"))
        if named is None or same_commit(repo_root, named, t.commit):
            return None
        why = f"was built for {named[:12]}, not {str(t.commit)[:12]}"
    else:
        why = "is missing"
    text = build_packet(repo_root, t.node_id, ref=ref, verify_cmds=[])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"review packet {why}: built {path} ({path.stat().st_size} bytes) for {str(t.commit)[:12]}",
          file=sys.stderr)
    return path
