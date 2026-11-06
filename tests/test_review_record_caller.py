"""``review record`` files only under the caller's own model (M21.31, CR1).

The caller is a worker (``SPECY_ROAD_WORKER_ID``), one harness marker, or unidentified; an unidentified caller
attests with ``--human-filed``, and the gate counts that record only signed or under
``policy.count_human_filed_reviews``. ``review delegate`` files through ``file_review`` and is not checked.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.review_delegate_helpers import (delegate_repo, handoff_status_node, run_review_cli, run_review_delegate,
                                           set_steps, verdict_step)
from tests.review_repo_helpers import git, make_review_repo, review_text

from specy_road.bundled_scripts import role_prompt
from specy_road.review_caller import HARNESS_MARKERS
from specy_road.review_files import review_path, reviews_dir
from specy_road.worker_state import create_record, record_path

pytestmark = pytest.mark.real_review_caller

OPUS, SOL = "claude-opus-5-5", "gpt-6.1-sol"
CLAUDE, CURSOR = {"CLAUDECODE": "1"}, {"CURSOR_AGENT": "1"}


def _roster(*, opus_pub: str | None = None, count_human: bool = False) -> str:
    key = f", public_key: \"{opus_pub}\"" if opus_pub else ""
    return ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - {{id: {OPUS}, family: anthropic, roles: [reviewer], harness: claude-code{key}}}\n"
            f"  - {{id: {SOL}, family: openai, roles: [reviewer], harness: codex}}\n"
            f"policy: {{reviewers_required: 1, count_human_filed_reviews: {str(count_human).lower()}}}\n")


def _env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for _, var, _ in HARNESS_MARKERS:
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def _tree(repo: Path) -> list[tuple[str, bytes]]:
    root = reviews_dir(repo, "M1.1").parent
    return sorted((str(p), p.read_bytes() if p.is_file() else b"") for p in root.rglob("*")) if root.exists() else []


def _record(repo: Path, model: str, *extra: str) -> int:
    notes = repo.parent / f"notes-{model}.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, commands_rerun=["pytest -q"]))
    return run_review_cli("review", "record", "M1.1", "--model", model, "--verdict", "approve", "--file",
                          str(notes), "--repo-root", str(repo), *extra)


def _worker(repo: Path, monkeypatch: pytest.MonkeyPatch, model: str) -> None:
    monkeypatch.setenv("SPECY_ROAD_WORKER_ID", create_record(repo, "M1.1", "cursor", model, repo).worker_id)


def _filed(repo: Path, model: str) -> dict:
    return yaml.safe_load(review_path(repo, "M1.1", model).read_text().split("---\n")[1])


@pytest.mark.parametrize("env, model, worker, says", [
    (CURSOR, OPUS, None, f"{OPUS} is a claude-code roster entry and this command runs under cursor"),   # CR1 r1
    (CURSOR, SOL, None, f"{SOL} is a codex roster entry and this command runs under cursor"),         # CR1 r3
    ({}, SOL, "composer-2.5", "runs under a worker of composer-2.5"),
    (CLAUDE, OPUS, "composer-2.5", "runs under a worker of composer-2.5"),   # the worker wins over its marker
    ({**CURSOR, **CLAUDE}, OPUS, None, "--human-filed"),   # two markers: unidentified
    ({}, OPUS, None, "--human-filed"),
])
def test_a_caller_that_is_not_the_model_is_refused_and_writes_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, env, model, worker, says) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster())
    _env(monkeypatch, env)
    if worker:
        _worker(repo, monkeypatch, worker)
    before = _tree(repo)
    assert _record(repo, model) == 1
    err = capsys.readouterr().err
    assert says in err and "nothing was written" in err
    assert _tree(repo) == before


@pytest.mark.parametrize("worker_id, body", [("../w-1", None), ("w-0042", None), ("w-0042", "{not: [yaml"),
                                             ("w-0042", "- a list\n")])
def test_a_worker_id_that_does_not_resolve_is_refused_without_a_traceback(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, worker_id, body) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster())
    _env(monkeypatch, CLAUDE)
    if body is not None:
        record_path(repo, worker_id).parent.mkdir(parents=True, exist_ok=True)
        record_path(repo, worker_id).write_text(body)
    monkeypatch.setenv("SPECY_ROAD_WORKER_ID", worker_id)
    before = _tree(repo)
    assert _record(repo, OPUS) == 1
    err = capsys.readouterr().err
    assert "SPECY_ROAD_WORKER_ID" in err and "Traceback" not in err
    assert _tree(repo) == before


@pytest.mark.parametrize("attest", ["", "   ", "me\nbecause"])
def test_an_attestation_must_be_one_non_empty_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
                                                   attest: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster())
    _env(monkeypatch, {})
    before = _tree(repo)
    assert _record(repo, OPUS, "--human-filed", attest) == 1
    assert "--human-filed takes one non-empty line" in capsys.readouterr().err
    assert _tree(repo) == before


@pytest.mark.parametrize("extra", [(), ("--human-filed", "savigil, pasted notes")])
def test_the_models_own_harness_files_and_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
                                                 extra) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster())
    _env(monkeypatch, CLAUDE)
    assert _record(repo, OPUS, *extra) == 0
    assert "human_filed" not in _filed(repo, OPUS)
    assert ("--human-filed ignored" in capsys.readouterr().err) == bool(extra)
    assert handoff_status_node(repo, capsys)["policy_met"]


def test_the_workers_own_model_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster())
    _env(monkeypatch, CURSOR)   # a worker's model need not match its inherited marker's harness
    _worker(repo, monkeypatch, SOL)
    assert _record(repo, SOL) == 0
    assert handoff_status_node(repo, capsys)["policy_met"]


@pytest.mark.parametrize("count_human", [False, True])
def test_a_hand_filed_record_counts_only_under_the_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
                                                         count_human: bool) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster(count_human=count_human))
    _env(monkeypatch, {})
    assert _record(repo, OPUS, "--human-filed", "  savigil, notes pasted from a claude.ai chat ") == 0
    assert _filed(repo, OPUS)["human_filed"] == "savigil, notes pasted from a claude.ai chat"
    st = handoff_status_node(repo, capsys)
    assert st["policy_met"] is count_human
    said = "filed by hand (human_filed) and unsigned; policy.count_human_filed_reviews is off"
    assert any(said in p for p in st["problems"]) is not count_human


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH ssh-keygen")
def test_a_signed_hand_filed_record_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    key = tmp_path / "opus_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", OPUS, "-f", str(key)], check=True)
    repo = make_review_repo(tmp_path, orchestration=_roster(opus_pub=Path(f"{key}.pub").read_text().strip()))
    _env(monkeypatch, {})
    assert _record(repo, OPUS, "--human-filed", "savigil, by hand", "--sign-key", str(key)) == 0
    assert _filed(repo, OPUS)["human_filed"] == "savigil, by hand"
    assert handoff_status_node(repo, capsys)["policy_met"]


def test_review_delegate_from_a_cursor_coordinator_files_and_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                    capsys) -> None:
    repo, spec = delegate_repo(tmp_path)   # the reviewer, opus, is a claude-code entry
    _env(monkeypatch, CURSOR)
    set_steps(repo, spec, verdict_step(repo))
    assert run_review_delegate(repo) == 0
    assert "human_filed" not in _filed(repo, "opus")
    assert handoff_status_node(repo, capsys)["policy_met"]


def test_the_paste_prompt_keeps_the_plain_line_and_adds_the_human_sentence(tmp_path: Path) -> None:
    repo, _spec = delegate_repo(tmp_path)
    pasted = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus", read_back=False)[0]
    line = next(x for x in pasted.splitlines() if "`specy-road review record M1.1 --model opus" in x)
    assert "--human-filed" not in line
    assert "A human filing the verdict from a terminal with no harness marker adds `--human-filed \"<who and why>\"`" \
        in pasted
