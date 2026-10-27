"""Regressions from the third independent review (GPT-5.6 Sol), part 2: findings F9–F15.

READY binds to the branch; a profile path cannot escape the repo; `--harness`
cannot override the roster; a plan with no coordinator says so; search
results are delimited; the verifier's byte cap is a cap.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import _repo

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import brainstorm_chat as bc
from specy_road.bundled_scripts import brainstorm_verify as bv
from specy_road.model_profiles import profile_for_entry
from specy_road.review_files import reviews_root


# --- F9 -----------------------------------------------------------------------

def test_a_ready_on_another_branch_does_not_complete(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    head = git(repo, "rev-parse", "HEAD")
    (d / "READY-x.md").write_text(f"---\nnode_id: M1.1\nagent: x\nbranch: feature/rm-other\ncommit: {head}\n"
                                  f"base: {head}\nchanged_paths: []\nverify: []\n---\n")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    spec = tmp_path / "ok.json"
    spec.write_text(json.dumps({"lines": [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]}))
    launch = wa.adapter_for("claude-code").launch(spec, repo, "opus", f"{sys.executable} {script} {{prompt}}")
    time.sleep(0.05)
    os.utime(d / "READY-x.md", None)
    assert wr.run(repo, rec.worker_id, launch) == 0
    assert ws.load_record(repo, rec.worker_id).state == "idle"


# --- F10, F11, F12 --------------------------------------------------------------

def test_a_profile_path_cannot_escape_the_repo(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    outside = tmp_path / "evil.md"
    outside.write_text("---\nprofile_schema: 2\n---\n")
    prof = profile_for_entry(repo, {"id": "x", "profile": "../evil.md"})
    assert prof is not None and not prof.ok and "escapes the repository" in prof.errors[0]


def test_harness_override_cannot_move_a_rostered_model(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    with pytest.raises(ws.WorkerError, match="rostered on harness"):
        ops.delegate(repo, "M1.1", "opus", harness="cursor")


def test_a_plan_without_a_coordinator_says_so(tmp_path: Path) -> None:
    from specy_road.bundled_scripts.roadmap_load import load_roadmap
    from specy_road.orchestrate_plan import Candidate, assign_leaf
    from specy_road.orchestration_config import effective_config

    repo = make_review_repo(tmp_path, orchestration="version: 1\nroster:\n  - {id: exec1, family: openai, roles: [executor, reviewer]}\n"
                                                     "  - {id: rev1, family: anthropic, roles: [reviewer]}\npolicy: {reviewers_required: 1}\n")
    config, _err = effective_config(repo)
    node = next(n for n in load_roadmap(repo)["nodes"] if n["id"] == "M1.1")
    a = assign_leaf(node, [Candidate(e, None) for e in config["roster"]], config)
    assert not a.ok and any("no eligible coordinator" in p for p in a.problems)


# --- F14, F15 -------------------------------------------------------------------

def test_search_results_are_delimited_as_untrusted() -> None:
    assert "<search-results>" in bc.UNTRUSTED_RESULTS or "search-results" in bc.UNTRUSTED_RESULTS
    text, _found = bc.run_searches([], {})
    assert "<search-results>" in text and "never instructions" in text


def test_the_byte_cap_blocks_rather_than_truncates(monkeypatch) -> None:
    class R:
        status = 200
        _left = bv.MAX_BYTES + 1

        def read(self, n):
            take = min(n, self._left)
            self._left -= take
            return b"x" * take

        def getheader(self, _name):
            return None

    class Conn:
        def __init__(self, host, address, port): pass
        def request(self, *a, **k): pass
        def getresponse(self): return R()
        def close(self): pass

    monkeypatch.setattr(bv, "_PinnedHTTPS", Conn)
    monkeypatch.setattr(bv, "_public_address", lambda host: "93.184.216.34")
    monkeypatch.setattr(bv, "_is_off_host", lambda host: False)
    with pytest.raises(ValueError, match="larger than"):
        bv.default_fetch("https://example.com/big")
    assert bv.check_source({"url": "https://example.com/big", "quote": "x"}, bv.default_fetch) == "blocked"
