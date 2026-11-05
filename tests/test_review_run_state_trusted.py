"""M8.3: a reviewer run's own state is never read back from the reviewer-writable run file (Sol-low, 40d66c96).

``prompt --channel cli`` used to re-read ``RUN-<model>.json`` after the harness and write its transcript to that
file's ``log`` path: a reviewer that pointed ``log`` at ``src/a.py`` had specy-road overwrite it. Now the record
stays in memory from open to close, and every path is derived from the node, the model and the hand-off directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.test_models_and_prompt import run_main
from tests.test_review_record_write import GENERIC

from specy_road import review_files as rf
from specy_road.bundled_scripts import role_prompt
from specy_road.review_delegate import delegate
from specy_road.review_usage import review_usage
from specy_road.review_write_check import replace_file


def _forged_run(repo: Path, model: str) -> dict:
    """What a reviewer writes over its run file: the log (and attempt span) pointed at a tracked source file."""
    src = str(repo / "src" / "a.py")
    return {"node_id": "M1.1", "model": model, "state": "complete", "log": src, "source": "prompt-cli",
            "attempts": [{"log_start": 0, "log_end": 0, "log_sha256": None}], "events": []}


@pytest.mark.parametrize("files", [True, False], ids=["recorded", "rerun"])
def test_prompt_cli_never_writes_to_a_log_path_the_reviewer_put_in_its_run_file(tmp_path: Path, capsys,
                                                                                files: bool) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    source = (repo / "src" / "a.py").read_bytes()
    run_file = rf.reviews_dir(repo, "M1.1") / "RUN-gem.json"
    step = verdict_step(repo, model="gem") if files else {"raw": "not a verdict"}
    set_steps(repo, spec, {**step, "plain": True,
                           "write": {"path": str(run_file), "text": json.dumps(_forged_run(repo, "gem"))}})
    rc = run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli",
                  "--repo-root", str(repo))
    assert (repo / "src" / "a.py").read_bytes() == source                      # never written
    run = json.loads(run_file.read_text())
    assert run["source"] == "prompt-cli" and run["log"] == str(run_file.with_suffix(".log"))   # specy-road's own
    assert run_file.with_suffix(".log").read_text().strip()                    # the transcript went beside it
    if files:
        assert rc == 0 and run["state"] == "complete" and rf.review_path(repo, "M1.1", "gem").exists()
    else:
        assert rc == 1 and run["state"] == "incomplete" and run["outcome"] == "rerun"
        assert not rf.review_path(repo, "M1.1", "gem").exists()


def test_review_delegate_keeps_its_attempt_spans_and_log_in_memory(tmp_path: Path) -> None:
    """A run file forged mid-run (log path, attempt span) changes nothing: the answer is read from specy-road's
    own span, and the record written at the end is specy-road's."""
    repo, spec = delegate_repo(tmp_path)
    source = (repo / "src" / "a.py").read_bytes()
    run_file = rf.reviews_dir(repo, "M1.1") / "RUN-opus.json"
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(run_file),
                                                           "text": json.dumps(_forged_run(repo, "opus"))}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "recorded", run["reason"]
    assert (repo / "src" / "a.py").read_bytes() == source
    saved = json.loads(run_file.read_text())
    assert saved["log"] == str(run_file.with_suffix(".log")) and saved["attempts"] == run["attempts"]
    assert saved["attempts"][-1]["log_end"] > saved["attempts"][-1]["log_start"]


def test_specy_roads_writer_refuses_a_symlinked_directory(tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "linked").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(OSError):
        replace_file(tmp_path / "linked" / "RUN-x.json", "{}")
    assert not list((tmp_path / "elsewhere").iterdir())


def test_review_usage_reads_an_unknown_harness_in_a_run_file_as_generic(tmp_path: Path) -> None:
    """A run file's ``harness`` only picks the usage parser: an unknown one reads as ``generic``, never a crash."""
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    run_file = rf.reviews_dir(repo, "M1.1") / "RUN-opus.json"
    run_file.write_text(json.dumps({**json.loads(run_file.read_text()), "harness": "../../etc"}))
    assert [r["model"] for r in review_usage(repo, "M1.1")["runs"]] == ["opus"]
