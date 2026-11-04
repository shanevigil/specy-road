"""A worker turn's accounting, from the 0.3.1rc3 sandbox replay (§5): Codex usage per turn on a resume (F3),
a killed turn in the post-run check (F5), and the model-mismatch note's name comparison (F6)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.test_cursor_usage_cost import _api_id_for, _codex_repo
from tests.worker_repo_helpers import make_worker_repo

from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli_render as wcr
from specy_road.orchestration_config import roster_entry
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.worker_adapter_parsers import estimate_usage_cost, mtok_rates
from specy_road.worker_adapters import Launch
from specy_road.worker_models import mismatch_note
from specy_road.worker_usage_delta import turn_usage

ECHO = "import json, sys\nfor line in json.loads(open(sys.argv[1]).read()):\n    print(json.dumps(line), flush=True)\n"


def _codex_turn(usage: dict) -> dict:
    return {"type": "turn.completed", "usage": usage}


def test_a_resumed_codex_turn_counts_its_own_tokens_not_the_thread_total(tmp_path: Path) -> None:
    """`codex exec resume` reports the thread's running total: the usage event keeps it as session_usage and
    records the difference, so `worker usage` sums to the thread's total instead of counting turn 1 twice."""
    repo = _codex_repo(tmp_path)
    api_id = _api_id_for(repo, "priced")
    script = tmp_path / "echo.py"
    script.write_text(ECHO)
    rec = ws.create_record(repo, "M1.1", "codex", "priced", repo)
    first = {"input_tokens": 336311, "cached_input_tokens": 300000, "output_tokens": 5000, "reasoning_output_tokens": 1000}
    total = {"input_tokens": 367453, "cached_input_tokens": 330000, "output_tokens": 5400, "reasoning_output_tokens": 1100}
    for i, usage in enumerate((first, total)):
        spec = tmp_path / f"turn{i}.json"
        spec.write_text(json.dumps([{"type": "thread.started", "thread_id": "t-1"}, _codex_turn(usage)]))
        wr.run(repo, rec.worker_id, Launch([sys.executable, str(script), str(spec), "-m", api_id, "-C", str(repo)]),
               resumed=bool(i))
    events = [e.to_dict() for e in ws.events_since(repo, rec.worker_id)]
    turns = [e["detail"] for e in events if e["type"] == "usage"]
    assert [(t["input_tokens"], t["cached_input_tokens"], t["output_tokens"], t["reasoning_tokens"]) for t in turns] == [
        (336311, 300000, 5000, 1000), (31142, 30000, 400, 100)]
    assert turns[1]["session_usage"] == {"input_tokens": 367453, "cached_input_tokens": 330000,
                                         "output_tokens": 5400, "reasoning_tokens": 1100}
    config, _err = pinned_config(repo)
    rates = mtok_rates(pinned_profile_for_entry(repo, roster_entry(config, "priced")).data)   # the profile's list prices
    assert abs(turns[1]["cost_usd"] - estimate_usage_cost(turns[1], rates)) < 1e-5 and turns[1]["cost_is_estimate"]
    summed = wcr.usage([(ws.load_record(repo, rec.worker_id), events)])["total"]
    assert summed["input_tokens"] == 367453 and summed["output_tokens"] == 5400
    assert abs(summed["cost_usd"] - estimate_usage_cost({**total, "reasoning_tokens": 1100}, rates)) < 1e-5
    for e in events:
        assert ws.schema_errors(e, "worker-event.schema.json") == []


def test_a_session_total_lower_than_the_last_counts_whole() -> None:
    """A new session (a custom command without one) restarts the total: nothing is subtracted, nothing goes negative."""
    prev = ws.WorkerEvent(seq=1, worker_id="w-0001", at="t", type="usage", source="worker", authority="worker_suggestion",
                          summary="usage", epoch=0, detail={"session_usage": {"input_tokens": 900, "output_tokens": 50}})
    now = {"input_tokens": 100, "output_tokens": 70, "session_usage": {"input_tokens": 100, "output_tokens": 70}}
    assert turn_usage(now, [prev])["input_tokens"] == 100 and turn_usage(now, [prev])["output_tokens"] == 70
    grown = {"input_tokens": 1000, "output_tokens": 80, "session_usage": {"input_tokens": 1000, "output_tokens": 80}}
    assert (turn_usage(grown, [prev])["input_tokens"], turn_usage(grown, [prev])["output_tokens"]) == (100, 30)
    assert turn_usage(grown, [])["input_tokens"] == 1000   # the first turn is the session's whole total


def test_a_killed_turn_is_a_post_run_finding_not_clean(tmp_path: Path) -> None:
    """SIGKILL reports nothing in the stream; the check is written before the exit event, so it names the exit."""
    repo, _script = make_worker_repo(tmp_path)
    script = tmp_path / "killed.py"
    script.write_text("import json, os, signal\nprint(json.dumps({'type': 'system', 'subtype': 'init', "
                      "'session_id': 's-1', 'model': 'fake'}), flush=True)\nos.kill(os.getpid(), signal.SIGKILL)\n")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    assert wr.run(repo, rec.worker_id, Launch([sys.executable, str(script)])) == -9
    events = ws.events_since(repo, rec.worker_id)
    check = next(e for e in events if e.type == "post_run_check")
    assert [f["kind"] for f in check.detail["findings"]] == ["failed_turn"]
    assert check.summary == "post-run check: 1 finding(s): failed turn: exit -9"
    assert events[-1].type == "error" and events[-1].detail["exit"] == -9
    after = ws.load_record(repo, rec.worker_id)
    assert after.state == "failed" and "post_run_findings" in after.flags


def test_a_clean_exit_stays_a_clean_check(tmp_path: Path) -> None:
    """Exit 0 adds nothing: only a non-zero exit is a failed turn."""
    repo, _script = make_worker_repo(tmp_path)
    script = tmp_path / "ok.py"
    script.write_text(ECHO)
    spec = tmp_path / "ok.json"
    spec.write_text(json.dumps([{"type": "system", "subtype": "init", "session_id": "s-1", "model": "fake"},
                                {"type": "result", "subtype": "success", "result": "done", "session_id": "s-1"}]))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    assert wr.run(repo, rec.worker_id, Launch([sys.executable, str(script), str(spec)])) == 0
    check = next(e for e in ws.events_since(repo, rec.worker_id) if e.type == "post_run_check")
    assert check.summary == "post-run check: clean"


def test_model_mismatch_ignores_case_dashes_underscores_and_spaces() -> None:
    """Cursor names the model `Composer 2.5` for `--model composer-2.5`: the same model, no note."""
    for told, ran in (("composer-2.5", "Composer 2.5"), ("gpt_5.6-sol", "GPT 5.6 Sol"), ("opus", "OPUS")):
        assert mismatch_note({"requested_model": told, "observed_model": ran}) == ""
    assert mismatch_note({"requested_model": "composer-2.5", "observed_model": "Composer 2"}) == (
        "; model mismatch: told composer-2.5, harness reported Composer 2")
    assert mismatch_note({"requested_model": "composer-2.5", "observed_model": "composer-25"}) != ""
