"""M8.3 A3 (strict, rescope 2026-11-04): one case per row of :data:`specy_road.review_answer.TURNS` and shape.

Only the final turn's last terminal message counts, and it must be one complete JSON object that passes the schema
(a text message: its last top-level object, which must end it, M21.25).
Missing, empty, null, non-JSON or schema-invalid, or any unparseable line inside the final turn, is a rerun request;
an earlier answer is never used and nothing is salvaged. Sol's F2 (a truncated trailing result line) and F3 (Codex
``turn.started`` after a completed turn) are rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import review_output

from specy_road.review_answer import TURNS, Rerun, final_answer
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


def codex(*texts: object, end: str | None = "turn.completed", start: bool = True) -> str:
    """A ``codex exec --json`` turn: ``turn.started`` (``start``), one ``agent_message`` per text, then ``end``
    (``None``: cut off)."""
    lines = [_j(type="thread.started", thread_id="t")] + ([_j(type="turn.started")] if start else [])
    lines += [_j(type="item.completed", item={"type": "agent_message", "text": t}) for t in texts]
    return "\n".join(lines + ([_j(type=end)] if end else []))


def agy(structured: object, **extra: object) -> str:
    """Antigravity's ``--output-format json`` envelope (a ``generic`` harness), pretty-printed over many lines."""
    return json.dumps({"conversation_id": "c", "status": "SUCCESS", "response": "", "structured_output": structured,
                       **extra}, indent=2)


NO_FINAL, NULL, EMPTY = "ends without a final message", "carries no answer", "the final message is empty"
NOT_ONE, SCHEMA = "is not one complete JSON object", "does not match the review output schema"
NO_OBJECT, NOT_LAST = "the final message holds no JSON object", "the final message does not end with a JSON object"
UNFINISHED, DEEP = "the final message ends inside an unfinished JSON object", "the final message nests JSON too deeply"
CUT, OPEN = "is not one JSON object (a cut-off or stray line)", "the final turn did not complete"
TRUNCATED_RESULT = '{"type":"result","result":'

# (harness, shape, output, the -o file's text or None, expected: V or a substring of the rerun reason)
CASES = [
    ("claude-code", "valid structured", claude({"structured_output": V, "result": "ok"}), None, V),
    ("claude-code", "valid text", claude({"result": VT}), None, V),
    ("claude-code", "missing: no result event", claude(), None, NO_FINAL),
    ("claude-code", "null", claude({"result": None}), None, NULL),
    ("claude-code", "error result", claude({"result": VT, "is_error": True}), None, NULL),
    ("claude-code", "empty", claude({"result": "  \n"}), None, EMPTY),
    ("claude-code", "non-JSON", claude({"result": "All good, approve."}), None, NO_OBJECT),
    ("claude-code", "prose before the object", claude({"result": "Verdict:\n" + VT}), None, V),
    ("claude-code", "fenced object", claude({"result": "```json\n" + VT + "\n```"}), None, NOT_LAST),
    ("claude-code", "two objects", claude({"result": VT + "\n{}"}), None, SCHEMA),
    ("claude-code", "nested: no salvage", claude({"result": json.dumps({"review": V})}), None, SCHEMA),
    ("claude-code", "schema-invalid", claude({"structured_output": BAD}), None, SCHEMA),
    ("claude-code", "multiple: valid then null", claude({"result": VT}, {"result": None}), None, NULL),
    ("claude-code", "multiple: null then valid", claude({"result": None}, {"result": VT}), None, V),
    ("claude-code", "F2: valid then a truncated result line", claude({"result": VT}) + "\n" + TRUNCATED_RESULT,
     None, CUT),
    ("claude-code", "valid then stray text", claude({"result": VT}) + "\nWarning: done", None, CUT),
    ("claude-code", "stray text before the first event", "Warming up\n" + claude({"result": VT}), None, V),
    ("claude-code", "plain-text wrapper: one object", VT, None, V),
    ("claude-code", "plain-text wrapper: prose", "Done.\n" + VT, None, NOT_ONE),
    ("claude-code", "only a truncated result line", TRUNCATED_RESULT, None, NOT_ONE),
    ("codex", "valid -o file", codex("see -o"), VT, V),
    ("codex", "valid message (resume: no -o)", codex(VT), None, V),
    ("codex", "valid, no turn.started", codex(VT, start=False), None, V),
    ("codex", "missing: no message in the turn", codex(), None, NO_FINAL),
    ("codex", "null", codex(None), None, NULL),
    ("codex", "empty", codex(""), None, EMPTY),
    ("codex", "empty -o file falls to the message", codex("not json"), "", NO_OBJECT),
    ("codex", "non-JSON", codex("approve"), None, NO_OBJECT),
    ("codex", "schema-invalid", codex(json.dumps(BAD)), None, SCHEMA),
    ("codex", "multiple: valid then null message", codex(VT, None), None, NULL),
    ("codex", "multiple: valid turn then null turn", codex(VT) + "\n" + codex(None), None, NULL),
    ("codex", "turn failed", codex(VT, end="turn.failed"), None, OPEN),
    ("codex", "cut off after a valid message", codex(VT, end=None), None, OPEN),
    ("codex", "F3: completed turn, then turn.started", codex(VT) + "\n" + _j(type="turn.started"), None, OPEN),
    ("codex", "unparseable line in the final turn", codex(VT).replace('{"type": "turn.completed"}',
                                                                      'oops\n{"type": "turn.completed"}'), None, CUT),
    ("codex", "unparseable line in an earlier turn", "oops\n" + codex(None) + "\n" + codex(VT), None, V),
    ("codex", "plain-text wrapper", VT, None, V),
    ("cursor", "valid", claude({"result": VT}), None, V),
    ("cursor", "missing: no result event", claude(), None, NO_FINAL),
    ("cursor", "null", claude({"result": None}), None, NULL),
    ("cursor", "error result", claude({"result": VT, "is_error": True}), None, NULL),
    ("cursor", "empty", claude({"result": ""}), None, EMPTY),
    ("cursor", "non-JSON", claude({"result": "approve"}), None, NO_OBJECT),
    ("cursor", "schema-invalid", claude({"result": json.dumps(BAD)}), None, SCHEMA),
    ("cursor", "structured_output is not Cursor's", claude({"structured_output": V, "result": "ok"}), None,
     NO_OBJECT),
    ("cursor", "multiple: valid then error", claude({"result": VT}, {"result": "x", "is_error": True}), None, NULL),
    ("cursor", "valid then a truncated result line", claude({"result": VT}) + "\n" + TRUNCATED_RESULT, None, CUT),
    ("cursor", "plain-text wrapper", VT, None, V),
    ("generic", "antigravity valid", agy(V), None, V),
    ("generic", "plain object", VT, None, V),
    ("generic", "antigravity null", agy(None, status="ERROR"), None, NULL),
    ("generic", "empty output", "", None, EMPTY),
    ("generic", "non-JSON", "Error: quota exceeded", None, NOT_ONE),
    ("generic", "antigravity schema-invalid", agy(BAD), None, SCHEMA),
    ("generic", "antigravity: valid, then a null envelope", agy(V) + "\n" + agy(None), None, NOT_ONE),
    ("generic", "antigravity: valid, then a truncated envelope", agy(V) + "\n" + agy(V)[:40], None, NOT_ONE),
    ("generic", "antigravity truncated", agy(V)[:-3], None, NOT_ONE),
    ("generic", "prose then object", "Done.\n" + VT, None, NOT_ONE),
    ("generic", "plain JSON array", json.dumps([V]), None, NOT_ONE),
]


def test_every_row_of_the_table_has_cases() -> None:
    assert {c[0] for c in CASES} == set(TURNS)


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


# M21.25: a text terminal message's answer is its last top-level object, which must end it.
TEXT_PATHS = {
    "cursor result text": ("cursor", lambda t: (claude({"result": t}), None)),
    "claude result text": ("claude-code", lambda t: (claude({"result": t}), None)),
    "codex agent_message": ("codex", lambda t: (codex(t), None)),
    "codex -o file": ("codex", lambda t: (codex("see -o"), t)),
}
NARRATION = "Reading the reviewer prompt\u2026\n\n\nRunning precondition checks\u2026\n\n\n"
DEEP_TEXT = "Done.\n" + '{"a":' * 100_000 + "1" + "}" * 100_000
TEXT_SHAPES = [
    ("prose then a valid object (rc4 Cursor)", NARRATION + VT, V),
    ("JSON only", VT, V),
    ("JSON plus trailing whitespace", VT + "\n\n  \t", V),
    ("two valid objects gives the last", json.dumps({**V, "verdict": "x"}) + "\n" + VT, V),
    ("prose with a stray brace, then the object", "Checked {a, b} and [1/3].\n" + VT, V),
    ("unfinished outer container around a valid object", '{"x": ' + VT, UNFINISHED),
    ("unfinished outer array around a valid object", "[" + VT, UNFINISHED),
    ("an object only inside an array", json.dumps([V]), NO_OBJECT),
    ("excessive nesting", DEEP_TEXT, DEEP),
    ("object plus trailing prose", VT + "\nLet me know if you need more.", NOT_LAST),
    ("prose plus a truncated object", NARRATION + VT[:-20], UNFINISHED),
    ("valid object then a schema-invalid last object", VT + "\n" + json.dumps(BAD), SCHEMA),
]


@pytest.mark.parametrize("path", TEXT_PATHS)
@pytest.mark.parametrize("shape,text,expected", TEXT_SHAPES, ids=[t[0] for t in TEXT_SHAPES])
def test_a_text_message_answers_with_its_final_object(tmp_path: Path, path: str, shape: str, text: str,
                                                      expected: object) -> None:
    harness, build = TEXT_PATHS[path]
    output, saved = build(text)
    out = tmp_path / "answer.json"
    if saved is not None:
        out.write_text(saved)
    got = final_answer(ADAPTERS[harness], output, out)
    if expected == V:
        assert got == V, got
    else:
        assert isinstance(got, Rerun) and got.reason.startswith("rerun requested: ") and str(expected) in got.reason, got
