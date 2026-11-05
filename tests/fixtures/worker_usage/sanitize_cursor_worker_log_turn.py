"""Build a sanitized Cursor stream-json turn fixture from a worker ``*.log`` file.

Each line in the turn keeps ``type``, ``subtype``, ``session_id`` (placeholder), and any
``usage`` object with real token numbers. ``assistant`` lines keep ``message.usage`` only.
No prompts, paths, ids or other fields.

Run from the repo root (maintainer-only; output is committed):

    python tests/fixtures/worker_usage/sanitize_cursor_worker_log_turn.py \\
        /path/to/w-0066.log -o tests/fixtures/worker_usage/cursor_multi_segment_turn.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.worker_adapter_cursor import sum_cursor_turn_usage
from specy_road.worker_adapter_parsers import usage_fields

_SESSION = "<session>"


def _json_lines(path: Path) -> list[tuple[int, dict]]:
    out: list[tuple[int, dict]] = []
    for i, raw in enumerate(path.read_text().splitlines(), 1):
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            out.append((i, json.loads(raw)))
        except json.JSONDecodeError:
            continue
    return out


def _turns(lines: list[tuple[int, dict]]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, d in lines:
        if d.get("type") == "system" and d.get("subtype") == "init":
            start = i
        if d.get("type") == "result" and start is not None:
            spans.append((start, i))
            start = None
    return spans


def _raw_usage(d: dict) -> dict | None:
    if isinstance(d.get("usage"), dict):
        return d["usage"]
    msg = d.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
        return msg["usage"]
    return None


def sanitize_line(d: dict) -> dict:
    """One stream line reduced to type, subtype, session_id and usage when present."""
    out: dict = {"type": d["type"], "session_id": _SESSION}
    if d.get("subtype") is not None:
        out["subtype"] = d["subtype"]
    if isinstance(d.get("usage"), dict):
        out["usage"] = dict(d["usage"])
    msg = d.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
        out["message"] = {"usage": dict(msg["usage"])}
    return out


def excerpt_turn(lines: list[tuple[int, dict]], start: int, end: int) -> list[dict]:
    """Every line between init and result, sanitized, in log order."""
    return [sanitize_line(d) for i, d in lines if start <= i <= end]


def usage_parts_from_excerpt(excerpt: list[dict]) -> list[dict]:
    parts: list[dict] = []
    for ln in excerpt:
        raw = _raw_usage(ln)
        if raw is not None:
            parts.append(usage_fields(raw))
    return parts


def expected_output_tokens(excerpt: list[dict]) -> int:
    out = sum_cursor_turn_usage(usage_parts_from_excerpt(excerpt)).get("output_tokens")
    if out is None:
        raise ValueError("turn has no output_tokens")
    return out


def build(path: Path) -> dict:
    lines = _json_lines(path)
    if not lines:
        raise SystemExit(f"no JSON lines in {path}")
    start, end = max(_turns(lines), key=lambda s: s[1] - s[0])
    excerpt = excerpt_turn(lines, start, end)
    usage_lines = sum(1 for ln in excerpt if _raw_usage(ln) is not None)
    return {
        "_provenance": "Sanitized full agent turn from a Composer 2.5 worker log (each line: type, subtype, "
        "session_id, usage when present). Source: a real composer-2.5 turn on this toolkit's own grind.",
        "session_id": _SESSION,
        "usage_bearing_lines": usage_lines,
        "expected_output_tokens": expected_output_tokens(excerpt),
        "lines": excerpt,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", type=Path, help="worker .log file (stream-json lines)")
    p.add_argument("-o", "--output", type=Path, required=True)
    args = p.parse_args(argv)
    spec = build(args.log)
    args.output.write_text(json.dumps(spec, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
