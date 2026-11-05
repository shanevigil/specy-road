"""M8.3: what a reviewer leaves behind is never trusted (Sol-low's block at b148b290: R1-R3).

R1: specy-road never writes through a symlink in the hand-off directory, its records, run files, notes and their
parent directories included; any symlink there is a review failure, and recovery replaces the path itself.
R2: an event ``type`` that is not a string (a list, an object) is no harness event: a rerun request, never a crash.
R3: harness output is split on ``\\n`` only, so a U+2028 left raw inside a JSON string stays part of its event.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step, wrote_paths
from tests.review_repo_helpers import commit_file, git, review_output

from specy_road import review_files as rf
from specy_road.review_answer import Rerun, final_answer
from specy_road.review_delegate import delegate
from specy_road.review_record_write import run_text
from specy_road.worker_adapters import ADAPTERS


def _filed_block(tmp_path: Path) -> tuple[Path, Path, bytes, bytes]:
    """A filed block record, then a fix commit: ``(repo, spec, the record's bytes, src/a.py's bytes)``."""
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo, "block"))
    assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["outcome"] == "recorded"
    commit_file(repo, "src/a.py", "print('fixed')\n", "fix")
    return repo, spec, rf.review_path(repo, "M1.1", "opus").read_bytes(), (repo / "src" / "a.py").read_bytes()


# --- R1 -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["REVIEW-opus.md", "notes-opus.md", "RUN-opus.json", "RUN-opus.log",
                                  ".review-run.lock", "RUN-opus.json.tmp"])
def test_a_symlink_to_a_source_file_in_the_hand_off_directory_is_a_failure_and_never_written_through(
        tmp_path: Path, name: str) -> None:
    repo, spec, record, source = _filed_block(tmp_path)
    reviews = rf.reviews_dir(repo, "M1.1")
    set_steps(repo, spec, {**verdict_step(repo), "symlink": {"path": str(reviews / name),
                                                             "target": str(repo / "src" / "a.py")}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "review_failure" and f"work/reviews/M1.1/{name}" in wrote_paths(run["reason"])
    assert (repo / "src" / "a.py").read_bytes() == source                 # never written through the link
    assert not (reviews / name).is_symlink()                               # recovery removed the link
    path = rf.review_path(repo, "M1.1", "opus")
    assert not path.is_symlink() and path.read_bytes() == record          # the earlier block, a regular file


def test_a_symlinked_history_directory_is_replaced_and_the_record_copies_restored(tmp_path: Path) -> None:
    repo, spec, record, source = _filed_block(tmp_path)
    reviews = rf.reviews_dir(repo, "M1.1")
    copies = {p.name: p.read_bytes() for p in (reviews / "history").glob("*-opus.md")}
    assert copies
    set_steps(repo, spec, {**verdict_step(repo), "symlink": {"path": str(reviews / "history"),
                                                             "target": str(repo / "src")}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "review_failure" and "work/reviews/M1.1/history" in wrote_paths(run["reason"])
    assert (repo / "src" / "a.py").read_bytes() == source and not list((repo / "src").glob("*-opus.md"))
    hist = reviews / "history"
    assert hist.is_dir() and not hist.is_symlink()
    assert {n: (hist / n).read_bytes() for n in copies} == copies
    assert rf.review_path(repo, "M1.1", "opus").read_bytes() == record


def test_a_symlink_left_from_an_earlier_run_still_fails_the_next_one(tmp_path: Path) -> None:
    """A symlink there is never specy-road's: one already present before the run is reported too."""
    repo, spec = delegate_repo(tmp_path)
    (rf.reviews_dir(repo, "M1.1") / "planted").symlink_to(repo / "src")
    set_steps(repo, spec, verdict_step(repo))
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "review_failure" and wrote_paths(run["reason"]) == ["work/reviews/M1.1/planted"]
    assert not rf.review_path(repo, "M1.1", "opus").exists()


# --- R2 -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [[], {}, ["result"], {"x": 1}, 1, None])
@pytest.mark.parametrize("harness", sorted(ADAPTERS))
def test_a_non_string_event_type_is_a_schema_rerun_on_every_adapter(harness: str, value: object) -> None:
    got = final_answer(ADAPTERS[harness], json.dumps({"type": value, "result": None}))
    assert isinstance(got, Rerun) and "does not match the review output schema" in got.reason


@pytest.mark.parametrize("value", [[], {"x": 1}])
def test_a_generic_reviewer_answering_a_non_string_type_is_a_rerun_through_delegate(tmp_path: Path,
                                                                                  value: object) -> None:
    from tests.test_review_record_write import GENERIC
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {"plain": True, "raw": json.dumps({"type": value, "result": None})})
    run = delegate(repo, "M1.1", "gem", sleep=lambda s: None)
    assert run["state"] == "incomplete" and run["outcome"] == "rerun"
    assert "does not match the review output schema" in run["reason"]
    assert not rf.review_path(repo, "M1.1", "gem").exists()


# --- R3 -------------------------------------------------------------------------------------------------------------

# What str.splitlines breaks on that a JSON string may carry raw (C0 controls such as \x0b-\x1e must be escaped).
SEPARATORS = ["\u2028", "\u2029", "\u0085"]


@pytest.mark.parametrize("sep", SEPARATORS, ids=[f"U+{ord(c):04X}" for c in SEPARATORS])
@pytest.mark.parametrize("harness", ["claude-code", "cursor", "codex", "generic"])
def test_a_line_separator_raw_inside_a_json_string_stays_in_its_event(harness: str, sep: str) -> None:
    answer = {**review_output("a" * 40, model="m"), "notes": f"## Findings{sep}none"}
    text = json.dumps(answer, ensure_ascii=False)
    out = {"claude-code": json.dumps({"type": "result", "subtype": "success", "result": text}, ensure_ascii=False),
           "cursor": json.dumps({"type": "result", "subtype": "success", "result": text}, ensure_ascii=False),
           "codex": "\n".join(json.dumps(e, ensure_ascii=False) for e in (
               {"type": "turn.started"}, {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
               {"type": "turn.completed"})),
           "generic": text}[harness]
    assert sep in out                                                       # left raw, as UTF-8 JSON allows
    assert final_answer(ADAPTERS[harness], out) == answer


def test_run_text_keeps_a_raw_u2028_and_delegate_files_the_answer(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    step = verdict_step(repo)
    step["answer"]["notes"] = "## Findings\u2028none, not a defect because the change is covered"
    set_steps(repo, spec, {**step, "unescaped": True})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    log = rf.reviews_dir(repo, "M1.1") / "RUN-opus.log"
    assert "\u2028" in log.read_text(encoding="utf-8")                      # the harness's line kept it raw
    last = run["attempts"][-1]
    assert "\u2028" in run_text(log, last["log_start"], last["log_end"])
    assert run["outcome"] == "recorded", run["reason"]
    assert "\u2028" in (rf.reviews_dir(repo, "M1.1") / "notes-opus.md").read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain", "src") == ""
