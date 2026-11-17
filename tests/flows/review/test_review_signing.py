"""Signed review records (slice 6): the gate trusts a key, not a file."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.review import NODE, make_review_repo, review_text, git

from specy_road import review_signing as rs
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.bundled_scripts import review_packet as rp
from specy_road.review_files import PACKET_NAME, load_review, review_path, reviews_dir
from specy_road.review_gate import evaluate_gate
from tests.support.same.key_5acf3bfe8b72 import key as key_fn
from tests.support.extracted.review_signing import roster as roster_fn
from specy_road.review_files import reviews_root
from specy_road.review_gate import SigningError, write_human_approval
from tests.support.extracted.folded_review_evidence import _roster
from tests.support.extracted.review_signing import roster
from specy_road.review_files import render_front_matter

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH ssh-keygen")






def _record(repo: Path, model: str, **kw) -> dict:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    text = review_text(git(repo, "rev-parse", "HEAD"), model=model)
    p = d / f"REVIEW-{model}.md"
    p.write_text(text)
    data = load_review(p).data
    data["notes_sha256"] = rs.notes_digest("notes\n")   # as `review record` writes it; a signature must cover the notes
    data.update(kw)
    from specy_road.review_files import render_front_matter
    p.write_text(render_front_matter(data, "notes\n"))
    return data


def test_sign_and_verify_round_trip_and_tamper(tmp_path: Path) -> None:
    key, pub = key_fn(tmp_path, "opus")
    data = {"node_id": "M1.1", "model": "opus", "verdict": "approve", "commit": "abc1234", "family": "ignored"}
    sig = rs.sign(data, key)
    assert rs.verify(data, sig, pub, "opus") == (True, "")
    assert rs.verify({**data, "family": "anthropic", "independence": "same-family"}, sig, pub, "opus")[0]  # CLI-added fields excluded
    ok, why = rs.verify({**data, "verdict": "block"}, sig, pub, "opus")
    assert not ok and why
    _other, other_pub = key_fn(tmp_path, "sol")
    assert not rs.verify(data, sig, other_pub, "opus")[0]              # wrong key
    assert not rs.verify(data, "not base64!", pub, "opus")[0]


def test_sign_errors_are_clear(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(rs.SigningError, match="signing key not found"):
        rs.sign({"a": 1}, tmp_path / "missing")
    monkeypatch.setattr(rs.shutil, "which", lambda _n: None)
    with pytest.raises(rs.SigningError, match="ssh-keygen not found"):
        rs.sign({"a": 1}, tmp_path / "missing")
    assert rs.verify({"a": 1}, "YWJj", "ssh-ed25519 AAAA", "x") == (False, "ssh-keygen not found; signing review records needs OpenSSH 8.1 or newer")


def test_gate_requires_a_verifying_signature_when_policy_says_so(tmp_path: Path) -> None:
    key, pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=roster_fn(pub))
    _record(repo, "opus")
    g = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not g.passed and "signature missing" in g.ineligible[0][1]
    data = _record(repo, "opus")
    from specy_road.toolkit_version import stamp_review_toolkit_version
    data = stamp_review_toolkit_version(data)
    data["signature"] = rs.sign(data, key)
    from specy_road.review_files import render_front_matter
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, "notes\n"))
    assert evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD")).passed
    # Tampered after signing: refused.
    data["verdict"] = "approve"; data["acceptance"]["A1"] = "n/a"
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, "notes\n"))
    g = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not g.passed and "does not verify" in g.ineligible[0][1]


def test_rerender_signed_record_without_toolkit_version_keeps_signature(tmp_path: Path) -> None:
    key, pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=roster_fn(pub, signed=False))
    from specy_road.review_files import render_front_matter

    data = {
        "node_id": "M1.1",
        "model": "opus",
        "date": "2026-10-26",
        "verdict": "approve",
        "commit": git(repo, "rev-parse", "HEAD"),
        "acceptance": {"A1": "pass", "A2": "n/a"},
        "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
        "fresh_session": True,
        "authored_fix": False,
        "is_coordinator": False,
        rs.NOTES_KEY: rs.notes_digest("notes\n"),
    }
    data["signature"] = rs.sign(data, key)
    path = review_path(repo, "M1.1", "opus")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_front_matter(data, "notes\n"))
    loaded = load_review(path, ["A1", "A2"])
    assert loaded.ok and "toolkit_version" not in loaded.data
    assert rs.verify(loaded.data, loaded.data["signature"], pub, "opus")[0]
    path.write_text(render_front_matter(loaded.data, loaded.body))
    again = load_review(path, ["A1", "A2"])
    assert again.ok and "toolkit_version" not in again.data
    assert rs.verify(again.data, again.data["signature"], pub, "opus")[0]


def test_a_signature_is_checked_even_with_the_policy_off(tmp_path: Path) -> None:
    key, pub = key_fn(tmp_path, "opus")
    _sol_key, sol_pub = key_fn(tmp_path, "sol")
    repo = make_review_repo(tmp_path, orchestration=roster_fn(pub, signed=False))
    data = _record(repo, "opus")
    data["signature"] = rs.sign(data, tmp_path / "sol_key")   # someone else's key
    from specy_road.review_files import render_front_matter
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, "notes\n"))
    g = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not g.passed and "does not verify" in g.ineligible[0][1]
    # Signed, but the roster has no key for that reviewer: cannot count either.
    data = _record(repo, "sol")
    data["signature"] = rs.sign(data, tmp_path / "sol_key")
    review_path(repo, "M1.1", "sol").write_text(render_front_matter(data, "notes\n"))
    g = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert any("no public_key" in why for _r, why in g.ineligible)


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code or 0


@pytest.mark.slow
def test_review_record_signs_with_a_key_and_refuses_without_one(tmp_path: Path, capsys) -> None:
    key, pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=roster_fn(pub))
    notes = tmp_path / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    assert _cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 1
    assert "pass --sign-key" in capsys.readouterr().err
    assert _cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "1/1 approvals" in out and "met" in out
    rec = load_review(review_path(repo, "M1.1", "opus"))
    assert rec.ok and rec.data["signature"] and rec.data["family"] == "anthropic"
    assert evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD")).passed
    assert _cli("handoff", "status", "M1.1", "--repo-root", str(repo)) == 0
    assert "[signed]" in capsys.readouterr().out


def test_human_approval_needs_a_key_under_signed_reviews(tmp_path: Path, monkeypatch, capsys) -> None:
    key, pub = key_fn(tmp_path, "human")
    _opus_key, opus_pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=roster_fn(opus_pub, human_pub=pub))
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nx\n")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _p="": "a")
    with pytest.raises(SystemExit) as e:
        mir.main(["--repo-root", str(repo)])
    assert e.value.code == 1 and "needs --sign-key" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        mir.main(["--sign-key", str(key), "--repo-root", str(repo)])
        raise SystemExit(0)
    assert (e.value.code or 0) == 0
    rec = load_review(review_path(repo, "M1.1", "human"))
    assert rec.data["signature"] and rs.verify(rec.data, rec.data["signature"], pub, "human")[0]


@pytest.mark.parametrize("signed", [True, False])
def test_reviewer_prompt_and_handoff_status_name_the_sign_key(tmp_path: Path, capsys, signed: bool) -> None:
    _key_path, pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=roster_fn(pub, signed=signed))
    assert _cli("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1   # not met yet
    status = capsys.readouterr().out
    reviews_dir(repo, "M1.1").mkdir(parents=True)
    (reviews_dir(repo, "M1.1") / PACKET_NAME).write_text(rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[]))
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None, err
    record = "`specy-road review record M1.1 --model opus --verdict approve|block --file <notes.md>"
    if signed:
        assert f"{record} --sign-key <path to your private key>`." in text
        assert "`policy.signed_reviews` is on: `review record` refuses a record without `--sign-key`" in text
        assert "can approve (file a signed record: `specy-road review record --sign-key <your private key>`)" in status
    else:
        assert f"{record}`." in text and "--sign-key" not in text
        assert "can approve (file with `specy-road review record`)" in status and "--sign-key" not in status


@pytest.mark.slow
def test_a_launched_reviewers_verdict_is_filed_signed_with_the_callers_key(tmp_path: Path) -> None:
    from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
    from tests.support.cli import run_main
    from specy_road.review_delegate import delegate

    key, pub = key_fn(tmp_path, "opus")
    roster = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
              f"  - {{id: opus, family: anthropic, roles: [reviewer], harness: claude-code, public_key: \"{pub}\", "
              "channels: {cli: '{fake} {prompt} {session_flag}'}}\n"
              "policy: {reviewers_required: 1, signed_reviews: true}\n")
    repo, spec = delegate_repo(tmp_path, roster)
    set_steps(repo, spec, verdict_step(repo))
    head = git(repo, "rev-parse", "HEAD")
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)                 # no key: refused, never filed unsigned
    assert run["outcome"] == "rerun" and "policy.signed_reviews is on: pass --sign-key" in run["reason"]
    assert not review_path(repo, "M1.1", "opus").exists()
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--sign-key", str(key),
                         "--repo-root", str(repo)])
    assert e.value.code == 0 and evaluate_gate(repo, NODE, head).passed      # the signature verifies
    review_path(repo, "M1.1", "opus").unlink()
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                    "--sign-key", str(key), "--repo-root", str(repo)) == 0
    assert evaluate_gate(repo, NODE, head).passed



# --- F3, F18 ------------------------------------------------------------------

def test_signing_without_a_roster_key_is_refused_early(tmp_path: Path, capsys) -> None:
    key, _pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=roster("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", signed=False)
                            .replace('public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"', ""))
    from tests.support.review import review_text

    notes = tmp_path / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)])
    assert e.value.code == 1 and "has no public_key" in capsys.readouterr().err



def test_a_wrong_key_is_an_error_not_a_written_record(tmp_path: Path, capsys) -> None:
    key, _pub = key_fn(tmp_path, "opus")
    _other, other_pub = key_fn(tmp_path, "other")
    repo = make_review_repo(tmp_path, orchestration=roster(other_pub))
    from tests.support.review import review_text

    notes = tmp_path / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)])
    assert e.value.code == 1 and "does not verify" in capsys.readouterr().err
    assert not (reviews_root(repo) / "M1.1" / "REVIEW-opus.md").exists()


needs_keygen = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH ssh-keygen")



def _write(repo: Path, data: dict, body: str) -> None:
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, body))



def test_notes_digest_normalises_line_endings_and_trailing_whitespace() -> None:
    assert rs.notes_digest("a\r\nb\r\n") == rs.notes_digest("a\nb") == rs.notes_digest("a\nb\n\n  ")
    assert rs.notes_digest("a\nb") != rs.notes_digest("a\nc")



@needs_keygen
def test_a_signed_record_binds_its_notes(tmp_path: Path) -> None:
    key, pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster(pub))
    head = git(repo, "rev-parse", "HEAD")
    notes = tmp_path / "notes.md"
    # M11.75: an approve's observation lines carry a same-line 'not a defect because' reason
    notes.write_text(review_text(head, model="opus") + "Looked at src/a.py; not a defect because it is unchanged.\n")
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)])
    assert (e.value.code or 0) == 0
    rec = load_review(review_path(repo, "M1.1", "opus"))
    assert rec.data["notes_sha256"] == rs.notes_digest("notes\nLooked at src/a.py; not a defect because it is unchanged.\n")
    assert evaluate_gate(repo, NODE, head).passed
    # The body is replaced, front matter untouched: no longer counts.
    _write(repo, rec.data, "Something else entirely.\n")
    g = evaluate_gate(repo, NODE, head)
    assert not g.passed and "notes body does not match notes_sha256" in g.ineligible[0][1]
    # A signed record that never carried the hash does not count either.
    data = {k: v for k, v in rec.data.items() if k != "notes_sha256"}
    data["signature"] = rs.sign(data, key)
    _write(repo, data, rec.body)
    g = evaluate_gate(repo, NODE, head)
    assert not g.passed and "signed without notes_sha256" in g.ineligible[0][1]



def test_unsigned_records_keep_working_without_the_hash_but_a_present_one_is_checked(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster(None, signed=False))
    head = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    p = d / "REVIEW-opus.md"
    p.write_text(review_text(head, model="opus"))
    assert evaluate_gate(repo, NODE, head).passed                      # no hash: valid under unsigned policy
    data = {**load_review(p).data, "notes_sha256": rs.notes_digest("notes\n")}
    _write(repo, data, "notes\n")
    assert evaluate_gate(repo, NODE, head).passed
    _write(repo, data, "edited\n")
    g = evaluate_gate(repo, NODE, head)
    assert not g.passed and "notes body does not match" in g.ineligible[0][1]



@needs_keygen
def test_verify_rejects_a_mismatched_identity_on_its_own(tmp_path: Path) -> None:
    key, pub = key_fn(tmp_path, "opus")
    data = {"node_id": "M1.1", "model": "opus", "verdict": "approve", "commit": "abc1234"}
    sig = rs.sign(data, key)
    assert rs.verify(data, sig, pub, "opus") == (True, "")
    ok, why = rs.verify(data, sig, pub, "sol")
    assert not ok and "record model 'opus' is not the signer identity 'sol'" in why
    ok, why = rs.verify({**data, "model": "sol"}, sig, pub, "sol")     # relabelled record: signature breaks
    assert not ok and "not the signer identity" not in why



# --- human approval with a wrong key --------------------------------------

@needs_keygen
def test_a_wrong_human_key_writes_no_record_and_the_reason_is_printed(tmp_path: Path, monkeypatch, capsys) -> None:
    _human_key, human_pub = key_fn(tmp_path, "human")
    wrong_key, _wrong_pub = key_fn(tmp_path, "wrong")
    _opus_key, opus_pub = key_fn(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster(opus_pub, human_pub=human_pub))
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(SigningError, match="does not verify against the roster public_key for 'human'"):
        write_human_approval(repo, NODE, head, wrong_key)
    assert not review_path(repo, "M1.1", "human").exists()
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nx\n")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _p="": "a")
    with pytest.raises(SystemExit) as e:
        mir.main(["--sign-key", str(wrong_key), "--repo-root", str(repo)])
    captured = capsys.readouterr()
    assert e.value.code == 1
    assert "could not sign" in captured.err and "wrong key?" in captured.err
    assert "[ok] wrote" not in captured.out
    assert not review_path(repo, "M1.1", "human").exists()
