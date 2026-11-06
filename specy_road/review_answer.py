"""The one final-answer reader of a launched reviewer's run (M8.3 A3, strict): its schema, the per-harness
:data:`TURNS` table, and :func:`final_answer`.

Each harness's row in :data:`TURNS` declares how its stream marks the turn and its final answer. From this turn's
output (``review delegate`` and ``prompt --channel cli`` pass the log after the turn's own marker line):

* the **final turn** starts at the last event of the row's ``start`` types (none: at the harness's first event)
  and runs to the end of the output. Every non-blank line inside it must be one JSON object; a line that is not
  (a truncated event, stray text) is a rerun request. A row with an ``end`` type requires it inside the final turn;
* its **last terminal message** is the answer, and the only one: a final turn with none, or whose last one carries
  no answer (``null``, an error result), is a rerun request. An earlier answer is never used instead;
* that message must **end with one complete JSON object**, or the harness's own structured output is one. For a
  text message, text before the last top-level object is ignored and only whitespace may follow it (M21.25):
  empty text, no object, text after the object (a code fence's closing line included), an unfinished object,
  excessive nesting, or anything else is a rerun request; an object nested in another value is never the answer;
* the object must pass :func:`output_schema` (``null`` optional fields removed first), else a rerun request.

An output with none of the row's event types is the ``generic`` row's: the whole output is the one terminal
message (a ``channels.cli`` wrapper, Antigravity's ``agy --output-format json`` envelope, whose
``structured_output`` is the answer).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.runtime_paths import specy_road_package_dir
from specy_road.worker_adapter_base import Adapter
from specy_road.worker_adapter_parsers import loads_untrusted

#: Record fields ``review record`` writes itself; a reviewer's output never carries them.
FILLED_BY_SPECY_ROAD = ("family", "independence", "notes_sha256", "signature", "launch_mode", "sibling_heads",
                        "harness_model", "model_mismatch")
NOTES_DESCRIPTION = ("Your review notes in Markdown: findings with evidence, the commands you re-ran and their "
                     "results, and `## Excess` when it applies. specy-road writes them below the record's front matter.")
RERUN = "rerun requested: "


@cache
def output_schema() -> dict[str, Any]:
    """The review-record schema without the fields specy-road fills, plus the reviewer's ``notes``."""
    base = json.loads((specy_road_package_dir() / "schemas" / "review-record.schema.json").read_text(encoding="utf-8"))
    props = {k: v for k, v in base["properties"].items() if k not in FILLED_BY_SPECY_ROAD}
    props["notes"] = {"type": "string", "minLength": 1, "description": NOTES_DESCRIPTION}
    return {"$schema": base["$schema"], "title": "specy-road reviewer output",
            "description": "One reviewer's verdict as its final message; specy-road files it as REVIEW-<model>.md.",
            "type": "object", "required": [*base["required"], "notes"], "additionalProperties": False,
            "properties": props, "$defs": base["$defs"]}


def drop_nulls(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` without the optional fields, and the unplanned-removal acceptance entries, that Codex's strict schema
    let the reviewer answer ``null``."""
    out = {k: v for k, v in data.items() if v is not None or k in output_schema()["required"]}
    if isinstance(out.get("acceptance"), dict):
        out["acceptance"] = {k: v for k, v in out["acceptance"].items() if v is not None}
    return out


@dataclass(frozen=True)
class Rerun:
    """No answer to file: ``reason`` says why (it starts ``rerun requested: ``)."""
    reason: str




#: What a :class:`Turn`'s ``terminal`` returns for an event that is not a terminal message.
NOT_TERMINAL = object()


@dataclass(frozen=True)
class Turn:
    """One harness's row of :data:`TURNS`. ``events``: its event types (an output with none of them is the
    ``generic`` row's); ``start``: the types that open a turn, the final turn starting at the last one (empty: one
    process is one turn, starting at its first event); ``end``: the type that must close the final turn (``""``:
    none); ``terminal``: an event's message body when it is a terminal message (``None``: it carries no answer),
    else :data:`NOT_TERMINAL`; ``output_file``: a non-blank file the harness writes the final message to replaces
    that message's text, once the final turn has completed."""
    events: frozenset[str]
    start: frozenset[str]
    end: str
    terminal: Callable[[dict[str, Any]], Any]
    output_file: bool = False


def _result(structured: bool) -> Callable[[dict[str, Any]], Any]:
    """A ``result`` event: ``None`` when it is an error, else its ``structured_output`` (``structured``: the harness
    validated it against ``--json-schema``) or its ``result`` text."""
    def body(d: dict[str, Any]) -> Any:
        if event_type(d) != "result":
            return NOT_TERMINAL
        if d.get("is_error"):
            return None
        so = d.get("structured_output")
        return so if structured and isinstance(so, dict) else d.get("result")
    return body


def _agent_message(d: dict[str, Any]) -> Any:
    item = d.get("item") or {}
    done = event_type(d) == "item.completed" and isinstance(item, dict) and event_type(item) == "agent_message"
    return item.get("text") if done else NOT_TERMINAL


#: Each harness's turn boundary and terminal message (A3). One row per adapter; tests/test_review_answer.py has a
#: case per row and shape.
TURNS: dict[str, Turn] = {
    # claude -p --output-format stream-json: one process, one turn; its result event is the answer.
    "claude-code": Turn(frozenset({"system", "assistant", "user", "result"}), frozenset(), "", _result(True)),
    # codex exec --json: turn.started opens a turn, turn.completed closes it (turn.failed does not); the last
    # completed agent_message is the answer, or the -o file (--output-schema's) when Codex wrote one.
    "codex": Turn(frozenset({"thread.started", "turn.started", "turn.completed", "turn.failed", "item.started",
                             "item.updated", "item.completed", "error"}),
                  frozenset({"turn.started"}), "turn.completed", _agent_message, output_file=True),
    # agent -p --output-format stream-json: one process, one turn; its result event's text is the answer.
    "cursor": Turn(frozenset({"system", "user", "assistant", "tool_call", "result"}), frozenset(), "", _result(False)),
    # a channels.cli command, Antigravity's agy among them: the whole output is the one terminal message.
    "generic": Turn(frozenset(), frozenset(), "", lambda d: NOT_TERMINAL),
}


def event_type(d: dict[str, Any]) -> str | None:
    """An event object's ``type`` when it is a string, else ``None``: a list, object, number or ``null`` there is no
    event type of any harness (and a list or object would not even hash), so the object is no harness event."""
    t = d.get("type")
    return t if isinstance(t, str) else None


def stream_lines(text: str) -> list[str]:
    """A harness's output as its lines: split on ``\\n`` only, the delimiter of JSON Lines. ``str.splitlines`` also
    splits on U+2028, U+2029, U+0085 and other characters that a JSON string may carry unescaped, which would cut a
    valid event in two. A ``\\r`` before the ``\\n`` is JSON whitespace and stays harmless."""
    return text.split("\n")


def _object(line: str) -> dict[str, Any] | None:
    d = loads_untrusted(line)
    return d if isinstance(d, dict) else None


UNREADABLE_ANSWER = RERUN + "the final JSON does not match the review output schema: it cannot be read ({})"


def final_answer(adapter: Adapter, text: str, output: Path | None = None) -> dict[str, Any] | Rerun:
    """The run's answer from this turn's whole output ``text`` (and ``output``, the file a harness writes its
    final message to): the schema-valid object of the final turn's last terminal message, or a :class:`Rerun`
    (module docstring).

    The one boundary for reviewer output, and **total**: the output is untrusted input, so any exception reading,
    parsing or validating it (``ValueError``, ``RecursionError`` from deep nesting, ``TypeError``, ``KeyError``,
    ``UnicodeError``, …) is the schema-invalid rerun request, never an exception out of ``review delegate`` or
    ``prompt --channel cli``. An interrupt still propagates."""
    try:
        return _final_answer(adapter, text, output)
    except Exception as e:   # total by design (docstring)
        return Rerun(UNREADABLE_ANSWER.format(type(e).__name__))


def events(adapter: Adapter, line: str, launch: Any) -> list[Any]:
    """``adapter.parse_events`` for one line of reviewer output, total like :func:`final_answer`: a line it cannot
    read is no event (it is still in the log, and :func:`final_answer` judges it)."""
    try:
        return adapter.parse_events(line, launch)
    except Exception:   # untrusted output (final_answer)
        return []


def _final_answer(adapter: Adapter, text: str, output: Path | None) -> dict[str, Any] | Rerun:
    row = TURNS.get(adapter.harness, TURNS["generic"])
    lines = stream_lines(text)
    parsed = [_object(line) if line.strip() else None for line in lines]
    native = [i for i, d in enumerate(parsed) if d is not None and event_type(d) in row.events]
    if not native:
        return _answer(text, envelope=True)
    first = max((i for i in native if event_type(parsed[i]) in row.start), default=native[0])
    turn: list[dict[str, Any]] = []
    for n, (line, d) in enumerate(zip(lines[first:], parsed[first:]), first + 1):
        if d is None and line.strip():
            return Rerun(RERUN + f"line {n} of the final turn is not one JSON object (a cut-off or stray line)")
        if d is not None:
            turn.append(d)
    if row.end and not any(event_type(d) == row.end for d in turn):
        return Rerun(RERUN + f"the final turn did not complete (no {row.end})")
    bodies = [b for b in map(row.terminal, turn) if b is not NOT_TERMINAL]
    if not bodies:
        return Rerun(RERUN + "the final turn ends without a final message")
    body = bodies[-1]
    saved = output.read_text(encoding="utf-8", errors="replace") if row.output_file and output and output.is_file() else ""
    return _answer(saved if saved.strip() else body, envelope=False)


_OPENER = re.compile(r"[{\[]")


def _last_object(text: str) -> dict[str, Any] | Rerun:
    """A text message's answer: the last top-level JSON object, followed only by whitespace. The text is scanned left
    to right for complete JSON values, each value's interior skipped (a nested object is never the answer); a ``{``
    or ``[`` that starts no value is prose, one whose decode fails only because the text ends is refused. Nesting
    too deep for the decoder is refused, as :func:`loads_untrusted` refuses it."""
    decoder, i, last, end = json.JSONDecoder(), 0, None, 0
    while (m := _OPENER.search(text, i)) is not None:
        try:
            value, i = decoder.raw_decode(text, m.start())
        except RecursionError:
            return Rerun(RERUN + "the final message nests JSON too deeply to read")
        except json.JSONDecodeError as e:
            if e.pos >= len(text) or e.msg.startswith("Unterminated string"):
                return Rerun(RERUN + "the final message ends inside an unfinished JSON object")
            i = m.start() + 1
            continue
        if isinstance(value, dict):
            last, end = value, i
    if last is None:
        return Rerun(RERUN + "the final message holds no JSON object")
    if text[end:].strip():
        return Rerun(RERUN + "the final message does not end with a JSON object")
    return last


def _answer(body: Any, *, envelope: bool) -> dict[str, Any] | Rerun:
    """``body`` checked as the answer: one complete JSON object (``envelope``: an ``agy`` / ``--output-format json``
    envelope's ``structured_output``; else a text message's last object, :func:`_last_object`) that passes
    :func:`output_schema`."""
    if isinstance(body, str):
        if not body.strip():
            return Rerun(RERUN + "the final message is empty")
        body = _object(body) if envelope else _last_object(body)
        if isinstance(body, Rerun):
            return body
        if body is None:
            return Rerun(RERUN + "the final message is not one complete JSON object")
        if envelope and "structured_output" in body:
            body = body["structured_output"]
    if body is None:
        return Rerun(RERUN + "the final message carries no answer (null, or an error result)")
    if not isinstance(body, dict):
        return Rerun(RERUN + "the final message is not one complete JSON object")
    data = drop_nulls(body)
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in Draft202012Validator(output_schema()).iter_errors(data)]
    if errors:
        return Rerun(RERUN + "the final JSON does not match the review output schema: " + "; ".join(sorted(errors)[:5]))
    json.dumps(data, ensure_ascii=False).encode("utf-8")   # a lone surrogate cannot be filed: UnicodeEncodeError
    return data
