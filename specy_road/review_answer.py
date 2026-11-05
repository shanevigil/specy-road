"""The one final-answer extractor of a launched reviewer's run (M8.3): its schema, and :func:`final_answer`.

Every harness goes through :func:`final_answer`. Its adapter maps the turn's native stream to ordered messages
(:meth:`~specy_road.worker_adapter_base.Adapter.messages`: a body and a terminal flag); an output with none of
the harness's events is one terminal message, the whole output. Then:

* only the **last** message counts, and it must be terminal: a stream that ends after an intermediate message, or
  with none, is a rerun request; an earlier answer is never used instead;
* its body ``None`` (a ``null`` text, an error result), empty text, or text that does not end in one JSON object
  (:func:`text_object`) is a rerun request;
* an object that does not match :func:`output_schema` (``null`` optional fields removed first) is a rerun request.

What passes is the answer :func:`specy_road.review_record_write.file_review` files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.runtime_paths import specy_road_package_dir
from specy_road.worker_adapter_base import Adapter, Message

#: Record fields ``review record`` writes itself; a reviewer's output never carries them.
FILLED_BY_SPECY_ROAD = ("family", "independence", "notes_sha256", "signature", "launch_mode")
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
    """``data`` without the optional fields Codex's strict schema let the reviewer answer ``null``."""
    return {k: v for k, v in data.items() if v is not None or k in output_schema()["required"]}


@dataclass(frozen=True)
class Rerun:
    """No answer to file: ``reason`` says why (it starts ``rerun requested: ``)."""
    reason: str


_FENCE_END = re.compile(r"\n[ \t]*```[ \t]*$")
_LINE_OBJECT = re.compile(r"^[ \t]*(?:```json[ \t]*\n[ \t]*)?\{", re.M)


def text_object(text: str) -> dict[str, Any] | None:
    """The JSON object a message's text ends with, or ``None``. The object must start a line (prose, or a
    ```` ```json ```` fence, may precede it), run to the end of the text (a closing fence aside: nothing may follow
    it, so a later object, array or trailer is no answer), and sit at top level: no ``{`` or ``[`` before it left
    open, so a complete object inside malformed outer JSON or an array is no answer either."""
    body = _FENCE_END.sub("", text.rstrip()).rstrip()   # CRLF text: the \r before a closing fence too
    dec = json.JSONDecoder()
    for m in _LINE_OBJECT.finditer(body):
        start = m.end() - 1
        try:
            obj, end = dec.raw_decode(body, start)
        except ValueError:
            continue
        if end == len(body) and isinstance(obj, dict) and not _open(body[:start]):
            return obj
    return None


def _open(prefix: str) -> bool:
    """Whether ``prefix`` leaves a ``{`` or ``[`` open: each adds one, ``}`` or ``]`` takes one away but never below
    none, so balanced prose (``use {x}``, ``[link](x)``) and a stray closer leave the answer at top level."""
    depth = 0
    for ch in prefix:
        depth = depth + 1 if ch in "{[" else max(0, depth - 1) if ch in "}]" else depth
    return depth > 0


def final_answer(adapter: Adapter, text: str, output: Path | None = None) -> dict[str, Any] | Rerun:
    """The run's answer from this turn's whole output ``text`` (and ``output``, the file a harness writes its
    final message to): the schema-valid object of the last message, or a :class:`Rerun` (module docstring)."""
    msgs = adapter.messages(text.splitlines(), output)
    if msgs is None:
        msgs = [Message(text, True)]
    if not msgs or not msgs[-1].terminal:
        return Rerun(RERUN + "the output ends without a final message (no answer, or the stream was cut off)")
    body = msgs[-1].body
    if isinstance(body, str):
        if not body.strip():
            return Rerun(RERUN + "the final message is empty")
        body = text_object(body)
        if body is None:
            return Rerun(RERUN + "the reviewer's output ends with no JSON object")
    if isinstance(body, dict) and "structured_output" in body:   # a JSON envelope (agy, claude --output-format json)
        body = body["structured_output"]
    if body is None:
        return Rerun(RERUN + "the final message carries no answer (null, or an error result)")
    if not isinstance(body, dict):
        return Rerun(RERUN + "the final message is not a JSON object")
    data = drop_nulls(body)
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in Draft202012Validator(output_schema()).iter_errors(data)]
    if errors:
        return Rerun(RERUN + "the final JSON does not match the review output schema: " + "; ".join(sorted(errors)[:5]))
    return data
