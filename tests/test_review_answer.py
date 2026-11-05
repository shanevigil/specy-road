"""M8.3 A1/A3: the one final-answer extractor, per harness and terminal-message shape (design pass, 2026-11-04).

Each case is one harness's native output for one shape of the turn's last message: valid, null, empty, non-JSON,
schema-invalid, several terminal messages, and a stream cut off before its final message. Only the last terminal
message counts; anything but a schema-valid object there is a rerun request, and an earlier answer never stands in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import review_output

from specy_road.review_answer import Rerun, final_answer, text_object
from specy_road.worker_adapters import ADAPTERS

V = review_output("a" * 40, model="m")
VT = json.dumps(V)
BAD = {"verdict": "approve"}                                     # an object, but not the schema's


def _j(**d: object) -> str:
    return json.dumps(d)


def claude(*results: dict, init: bool = True, assistant: bool = True) -> str:
    """A Claude Code (or Cursor) stream-json turn ending in ``results`` (each a ``result`` event's fields)."""
    lines = ([_j(type="system", subtype="init", session_id="s")] if init else []) + \
            ([_j(type="assistant", message={"content": [{"type": "text", "text": VT}]})] if assistant else [])
    return "\n".join(lines + [_j(type="result", subtype="success", **r) for r in results])


def codex(*texts: object, end: str | None = "turn.completed") -> str:
    """A ``codex exec --json`` turn: one ``agent_message`` per text, then ``end`` (``None``: cut off)."""
    lines = [_j(type="thread.started", thread_id="t")]
    lines += [_j(type="item.completed", item={"type": "agent_message", "text": t}) for t in texts]
    return "\n".join(lines + ([_j(type=end)] if end else []))


def agy(structured: object, **extra: object) -> str:
    """Antigravity's ``--output-format json`` envelope (a ``generic`` harness), pretty-printed over many lines."""
    return json.dumps({"conversation_id": "c", "status": "SUCCESS", "response": "", "structured_output": structured,
                       **extra}, indent=2)


NO_FINAL, NULL, EMPTY = "ends without a final message", "carries no answer", "the final message is empty"
NOT_JSON, SCHEMA = "ends with no JSON object", "does not match the review output schema"

# (harness, shape, output, the -o file's text or None, expected: V or a substring of the rerun reason)
CASES = [
    ("claude-code", "valid structured", claude({"structured_output": V, "result": "ok"}), None, V),
    ("claude-code", "valid text", claude({"result": "Verdict:\n" + VT}), None, V),
    ("claude-code", "null", claude({"result": None}), None, NULL),
    ("claude-code", "error result", claude({"result": VT, "is_error": True}), None, NULL),
    ("claude-code", "empty", claude({"result": "  \n"}), None, EMPTY),
    ("claude-code", "non-JSON", claude({"result": "All good, approve."}), None, NOT_JSON),
    ("claude-code", "schema-invalid", claude({"structured_output": BAD}), None, SCHEMA),
    ("claude-code", "multiple: valid then null", claude({"result": VT}, {"result": None}), None, NULL),
    ("claude-code", "multiple: null then valid", claude({"result": None}, {"result": VT}), None, V),
    ("claude-code", "truncated", claude(), None, NO_FINAL),
    ("claude-code", "plain-text wrapper", "Done.\n" + VT, None, V),
    ("codex", "valid -o file", codex("see -o"), VT, V),
    ("codex", "valid message (resume: no -o)", codex(VT), None, V),
    ("codex", "null", codex(None), None, NULL),
    ("codex", "no message in the turn", codex(), None, NULL),
    ("codex", "turn failed", codex(VT, end="turn.failed"), None, NULL),
    ("codex", "empty", codex(""), None, EMPTY),
    ("codex", "empty -o file falls to the message", codex("not json"), "", NOT_JSON),
    ("codex", "non-JSON", codex("approve"), None, NOT_JSON),
    ("codex", "schema-invalid", codex(json.dumps(BAD)), None, SCHEMA),
    ("codex", "multiple: valid then null message", codex(VT, None), None, NULL),
    ("codex", "multiple: valid turn then null turn", codex(VT) + "\n" + codex(None), None, NULL),
    ("codex", "truncated after a valid message", codex(VT, end=None), None, NO_FINAL),
    ("codex", "plain-text wrapper", VT, None, V),
    ("cursor", "valid", claude({"result": VT}), None, V),
    ("cursor", "null", claude({"result": None}), None, NULL),
    ("cursor", "error result", claude({"result": VT, "is_error": True}), None, NULL),
    ("cursor", "empty", claude({"result": ""}), None, EMPTY),
    ("cursor", "non-JSON", claude({"result": "approve"}), None, NOT_JSON),
    ("cursor", "schema-invalid", claude({"result": json.dumps(BAD)}), None, SCHEMA),
    ("cursor", "multiple: valid then error", claude({"result": VT}, {"result": "x", "is_error": True}), None, NULL),
    ("cursor", "truncated", claude(), None, NO_FINAL),
    ("cursor", "plain-text wrapper", VT, None, V),
    ("generic", "antigravity valid", agy(V), None, V),
    ("generic", "antigravity null", agy(None, status="ERROR"), None, NULL),
    ("generic", "antigravity empty output", "", None, EMPTY),
    ("generic", "antigravity non-JSON", "Error: quota exceeded", None, NOT_JSON),
    ("generic", "antigravity schema-invalid", agy(BAD), None, SCHEMA),
    ("generic", "antigravity: valid, then a null envelope", agy(V) + "\n" + agy(None), None, NULL),
    ("generic", "antigravity: valid, then a truncated envelope", agy(V) + "\n" + agy(V)[:40], None, NOT_JSON),
    ("generic", "antigravity truncated", agy(V)[:-3], None, NOT_JSON),
    ("generic", "plain JSON array", json.dumps([V]), None, NOT_JSON),
]


@pytest.mark.parametrize("harness,shape,output,saved,expected", CASES, ids=[f"{c[0]}:{c[1]}" for c in CASES])
def test_the_last_terminal_message_is_the_answer_or_a_rerun(tmp_path: Path, harness: str, shape: str, output: str,
                                                            saved: str | None, expected: object) -> None:
    out = tmp_path / "answer.json"
    if saved is not None:
        out.write_text(saved)
    got = final_answer(ADAPTERS[harness], output, out)
    if expected == V:
        assert got == V, got
    else:
        assert isinstance(got, Rerun) and got.reason.startswith("rerun requested: ") and str(expected) in got.reason


def test_the_answer_file_counts_only_for_a_turn_that_completed(tmp_path: Path) -> None:
    out = tmp_path / "answer.json"
    out.write_text(VT)                                         # a stale or partial -o file
    assert isinstance(final_answer(ADAPTERS["codex"], codex("draft", end=None), out), Rerun)
    assert isinstance(final_answer(ADAPTERS["codex"], codex(VT, end="turn.failed"), out), Rerun)


def test_a_messages_text_must_end_with_one_top_level_json_object() -> None:
    """Moved from tests/test_review_record_write.py (``json_object``); the design pass makes the end strict: nothing
    may follow the object but a closing fence, so a harness trailer or prose after it is a rerun request."""
    assert text_object('Done.\n```json\n{"a": {"b": 1}}\n```\n') == {"a": {"b": 1}}
    assert text_object('{"draft": 1}\nthen\n{"final": 2}') == {"final": 2}
    assert text_object('{\n  "final": {\n    "x": 1\n  }\n}') == {"final": {"x": 1}}     # pretty-printed
    assert text_object('use {x} here, a stray }\n{"final": 2}') == {"final": 2}   # balanced prose, stray brace
    assert text_object('see [the docs](x)\n{"final": 2}') == {"final": 2}       # balanced brackets in prose
    assert text_object('{"final": 2}\ntokens used\n1,234') is None              # a trailer: not the end
    assert text_object('{"final": 2}\n[INFO] done, see [the docs](x)') is None  # prose after the answer
    assert text_object("no object here") is None and text_object("") is None
    assert text_object('{"final": 2}\n{"verdict": ') is None                    # a later object was cut off
    assert text_object('{"final": 2}\n{"x": {"y": 1}') is None                  # not its complete inner object
    assert text_object('{"final": 2}\n[1,') is None and text_object('{"final": 2}\n[]') is None   # a later array
    assert text_object('see {"final": 2}') is None                              # the answer starts its own line
    assert text_object('{"wrapper": "draft",\n{"final": 2}') is None            # nested in an unterminated object
    assert text_object('[\n{"final": 2}') is None and text_object('[\n{"final": 2}\n]') is None   # in an array
    assert text_object("[1, 2]") is None                                        # an array is not an object
    assert text_object('Done\r\n```json\r\n{"final": 2}\r\n```\r\n') == {"final": 2}   # CRLF, fenced
