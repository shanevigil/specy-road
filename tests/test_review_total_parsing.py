"""M8.3 A3: reading a reviewer's output is total (Sol-low's block at dcdbf3b4).

Reviewer output is untrusted input. Whatever the final message holds (nesting deep enough to exhaust the JSON
decoder's recursion, a huge number, a lone surrogate, a non-object, a wrong-typed field), on every adapter and
whether it sits in the message text or in the event line itself, the result is a rerun request, never an
exception, and ``review delegate --json`` reports it as an incomplete run with no record.
"""

from __future__ import annotations

import json

import pytest

from tests.review_delegate_helpers import delegate_repo, run_review_delegate, set_steps, verdict_step
from tests.review_repo_helpers import review_output

from specy_road import review_files as rf
from specy_road.review_answer import Rerun, events, final_answer
from specy_road.reviewer_run_failure import harness_error_line, turn_capacity_error
from specy_road.worker_adapters import ADAPTERS, Launch

DEPTH = 100_000
V = review_output("a" * 40, model="m")
MESSAGES = {
    "deep arrays": "[" * DEPTH + "]" * DEPTH,
    "deep objects": '{"a":' * DEPTH + "1" + "}" * DEPTH,
    "deep inside the answer": json.dumps({**V, "notes": "x"})[:-1] + ', "extra": ' + "[" * DEPTH + "]" * DEPTH + "}",
    "huge number": "1" * 50_000,
    "huge number field": json.dumps({**V, "date": 1})[:-1].replace('"date": 1', '"date": ' + "9" * 50_000) + "}",
    "lone surrogate": json.dumps({**V, "notes": "fine"}).replace("fine", "\\ud800"),
    "non-object top level": json.dumps([V]),
    "a string top level": json.dumps("approve"),
    "wrong-typed field": json.dumps({**V, "acceptance": ["A1"]}),
}


def _output(harness: str, message: str) -> str:
    """``message`` as ``harness``'s final message, in the message text (the event line itself stays shallow)."""
    if harness in ("claude-code", "cursor"):
        return json.dumps({"type": "result", "subtype": "success", "result": message})
    if harness == "codex":
        return "\n".join(json.dumps(e) for e in ({"type": "turn.started"},
                                                 {"type": "item.completed", "item": {"type": "agent_message",
                                                                                     "text": message}},
                                                 {"type": "turn.completed"}))
    return message


@pytest.mark.parametrize("shape", sorted(MESSAGES))
@pytest.mark.parametrize("harness", sorted(ADAPTERS))
def test_any_final_message_is_an_answer_or_a_rerun_never_an_exception(harness: str, shape: str) -> None:
    got = final_answer(ADAPTERS[harness], _output(harness, MESSAGES[shape]))
    assert isinstance(got, Rerun) and got.reason.startswith("rerun requested: ")


@pytest.mark.parametrize("harness", sorted(ADAPTERS))
def test_a_deeply_nested_event_line_is_unreadable_not_a_crash(harness: str) -> None:
    """The event line itself too deep: the live event parse, the capacity scan and the answer reader all hold."""
    line = '{"type": "result", "result": ' + "[" * DEPTH + "]" * DEPTH + "}"
    got_events = events(ADAPTERS[harness], line, Launch(argv=[]))                 # no exception
    assert all(e.type == "output" for e in got_events)                         # echoed at most, never an answer
    assert ADAPTERS[harness].parse_events(line, Launch(argv=[])) is not None     # the adapter's own parse holds
    assert turn_capacity_error([], [line]) is None
    assert harness_error_line(exit_code=1, errors=[], tail=[line], fallback="x")
    got = final_answer(ADAPTERS[harness], line)
    assert isinstance(got, Rerun) and got.reason.startswith("rerun requested: ")


def test_a_valid_answer_still_passes_the_boundary() -> None:
    assert all(final_answer(ADAPTERS[h], _output(h, json.dumps(V))) == V for h in ADAPTERS)


@pytest.mark.parametrize("shape", ["deep arrays", "deep inside the answer", "lone surrogate"])
def test_review_delegate_json_reports_an_unreadable_final_answer_as_an_incomplete_rerun(tmp_path, capsys,
                                                                                          shape: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    raw = MESSAGES[shape].replace("a" * 40, verdict_step(repo)["answer"]["commit"])   # only the bad part blocks
    set_steps(repo, spec, {"raw": raw})
    capsys.readouterr()
    assert run_review_delegate(repo, "--json") == 1
    out, err = capsys.readouterr()
    run = json.loads(out)
    assert run["state"] == "incomplete" and run["outcome"] == "rerun"
    assert run["reason"].startswith("rerun requested: ") and "Traceback" not in out + err
    assert not rf.review_path(repo, "M1.1", "opus").exists()
