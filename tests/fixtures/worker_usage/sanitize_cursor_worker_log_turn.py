"""Build a sanitized Cursor stream-json turn fixture from a worker ``*.log`` file.

Keeps each line's ``type``, ``subtype``, ``session_id`` placeholder, and any ``usage`` object
with its real token numbers. Drops prompts, thinking text, tool arguments, paths and ids.

Run from the repo root (maintainer-only; output is committed):

    python tests/fixtures/worker_usage/sanitize_cursor_worker_log_turn.py \\
        /path/to/w-0066.log -o tests/fixtures/worker_usage/cursor_multi_segment_turn.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.worker_adapter_parsers import usage_fields

_SESSION = "<session>"
_KEEP_TYPES = frozenset({"system", "tool_call", "usage", "result"})


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


def _sanitize(d: dict) -> dict | None:
    t = d.get("type")
    if t not in _KEEP_TYPES:
        return None
    out: dict = {"type": t, "session_id": _SESSION}
    if d.get("subtype") is not None:
        out["subtype"] = d["subtype"]
    if isinstance(d.get("usage"), dict):
        out["usage"] = dict(d["usage"])
    return out


def _sample_tool_calls(lines: list[tuple[int, dict]], start: int, end: int, *, max_lines: int = 8) -> list[dict]:
    tools = [(i, d) for i, d in lines if start <= i <= end and d.get("type") == "tool_call"]
    if len(tools) <= max_lines:
        picked = tools
    else:
        step = max(1, len(tools) // max_lines)
        picked = tools[::step][:max_lines]
    return [s for i, d in picked if (s := _sanitize(d))]


def excerpt_turn(lines: list[tuple[int, dict]], start: int, end: int) -> list[dict]:
    init = next(d for i, d in lines if i == start)
    result = next(d for i, d in lines if i == end)
    body = [_sanitize(init), *_sample_tool_calls(lines, start, end), _sanitize(result)]
    return [ln for ln in body if ln]


def expected_output_tokens(excerpt: list[dict]) -> int:
    result = next(ln for ln in excerpt if ln.get("type") == "result")
    fields = usage_fields(result.get("usage"))
    out = fields.get("output_tokens")
    if out is None:
        raise ValueError("result line has no output_tokens")
    return out


def build(path: Path) -> dict:
    lines = _json_lines(path)
    if not lines:
        raise SystemExit(f"no JSON lines in {path}")
    start, end = max(_turns(lines), key=lambda s: s[1] - s[0])
    excerpt = excerpt_turn(lines, start, end)
    return {
        "_provenance": "Sanitized excerpt of one agent turn from a Composer 2.5 worker log "
        "(type, subtype, session_id, usage only). Source: a real composer-2.5 turn on this toolkit's own grind.",
        "session_id": _SESSION,
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
