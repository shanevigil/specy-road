"""Signed review records (slice 6): the gate trusts a key, not a file."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, git, make_review_repo, review_text

from specy_road import review_signing as rs
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli
from specy_road.review_files import load_review, review_path, reviews_dir
from specy_road.review_gate import evaluate_gate

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH ssh-keygen")


def _key(tmp_path: Path, name: str) -> tuple[Path, str]:
    key = tmp_path / f"{name}_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, (tmp_path / f"{name}_key.pub").read_text(encoding="utf-8").strip()


def _roster(opus_pub: str, human_pub: str | None = None, *, signed: bool = True) -> str:
    human = f"  - {{id: human, family: human, roles: [coordinator, reviewer], public_key: \"{human_pub}\"}}\n" if human_pub \
        else "  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
    return ("version: 1\nroster:\n" + human +
            f"  - {{id: opus, family: anthropic, roles: [reviewer], public_key: \"{opus_pub}\"}}\n"
            "  - {id: sol, family: openai, roles: [reviewer]}\n"
            f"policy: {{reviewers_required: 1, signed_reviews: {'true' if signed else 'false'}}}\n")


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
    key, pub = _key(tmp_path, "opus")
    data = {"node_id": "M1.1", "model": "opus", "verdict": "approve", "commit": "abc1234", "family": "ignored"}
    sig = rs.sign(data, key)
    assert rs.verify(data, sig, pub, "opus") == (True, "")
    assert rs.verify({**data, "family": "anthropic", "independence": "same-family"}, sig, pub, "opus")[0]  # CLI-added fields excluded
    ok, why = rs.verify({**data, "verdict": "block"}, sig, pub, "opus")
    assert not ok and why
    _other, other_pub = _key(tmp_path, "sol")
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
    key, pub = _key(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster(pub))
    _record(repo, "opus")
    g = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not g.passed and "signature missing" in g.ineligible[0][1]
    data = _record(repo, "opus")
    data["signature"] = rs.sign(data, key)
    from specy_road.review_files import render_front_matter
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, "notes\n"))
    assert evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD")).passed
    # Tampered after signing: refused.
    data["verdict"] = "approve"; data["acceptance"]["A1"] = "n/a"
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, "notes\n"))
    g = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not g.passed and "does not verify" in g.ineligible[0][1]


def test_a_signature_is_checked_even_with_the_policy_off(tmp_path: Path) -> None:
    key, pub = _key(tmp_path, "opus")
    _sol_key, sol_pub = _key(tmp_path, "sol")
    repo = make_review_repo(tmp_path, orchestration=_roster(pub, signed=False))
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


def test_review_record_signs_with_a_key_and_refuses_without_one(tmp_path: Path, capsys) -> None:
    key, pub = _key(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster(pub))
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
    key, pub = _key(tmp_path, "human")
    _opus_key, opus_pub = _key(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster(opus_pub, human_pub=pub))
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
