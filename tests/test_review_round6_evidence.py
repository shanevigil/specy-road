"""Round-6 review fixes: evidence the gate, the packet and reconcile rely on.

* B2 — a rename or copy into a touch zone is also a change outside it, in
  ``worker reconcile``, the review packet and the finish-time check.
* F6 — a READY under ``work/reviews/<node>/`` naming another node or branch
  never feeds ``handoff status``, the packet or completion.
* F12 — the Markdown notes are bound to the signed front matter
  (``notes_sha256``); ``verify`` rejects a mismatched identity on its own; the
  packet labels committed, working-tree and missing summaries distinctly.
* A wrong ``--sign-key`` on the interactive human approval writes nothing and
  the reason is printed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road import review_signing as rs
from specy_road import worker_reconcile as wr
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.finish_implementation_check import changed_paths
from specy_road.git_changed_paths import diff_paths, parse_name_status
from specy_road.review_files import latest_ready, load_review, render_front_matter, review_path, reviews_dir
from specy_road.review_gate import SigningError, evaluate_gate, write_human_approval
from specy_road.review_target import resolve_target

needs_keygen = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH ssh-keygen")


# --- B2 -------------------------------------------------------------------

def _rename_into_zone(tmp_path: Path, src: str, dst: str) -> Path:
    """A repo whose base holds ``src`` and whose feature branch renames it to ``dst``."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, src, "# old\n" * 20, "base doc")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "dev")
    git(repo, "mv", src, dst)
    git(repo, "commit", "-qm", "rename")
    return repo


def test_parse_name_status_returns_both_sides_of_renames_and_copies() -> None:
    out = "M\0a.py\0R100\0docs/old name.md\0src/old name.md\0C75\0src/a.py\0src/b.py\0D\0gone\ttab\0"
    assert parse_name_status(out) == {"a.py", "docs/old name.md", "src/old name.md", "src/a.py", "src/b.py", "gone\ttab"}
    assert parse_name_status("") == set()


def test_committed_rename_into_the_zone_is_reported_on_both_sides(tmp_path: Path) -> None:
    repo = _rename_into_zone(tmp_path, "docs/old name.md", "src/old name.md")
    assert "R100" in git(repo, "diff", "--name-status", "dev...HEAD")   # git does see the rename
    t = resolve_target(repo, "M1.1")
    paths, lines = rp._changed(repo, t)
    assert "docs/old name.md" in paths and "src/old name.md" in paths
    assert any("docs/old name.md" in ln and "outside touch zones" in ln for ln in lines)
    assert "docs/old name.md" in wr._changed_since(repo, t.base)
    assert "docs/old name.md" in changed_paths(repo, "refs/heads/dev")


def test_rename_out_of_the_zone_keeps_the_source_inside_it(tmp_path: Path) -> None:
    repo = _rename_into_zone(tmp_path, "src/keep me.py", "docs/keep me.py")
    t = resolve_target(repo, "M1.1")
    paths, lines = rp._changed(repo, t)
    assert "src/keep me.py" in paths and "docs/keep me.py" in paths
    assert any("docs/keep me.py" in ln and "outside touch zones" in ln for ln in lines)
    assert not any("src/keep me.py" in ln and "outside" in ln for ln in lines)


def test_uncommitted_rename_is_seen_by_reconcile(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "mv", "src/a.py", "docs/a.py")                      # staged
    assert wr._changed_since(repo, "HEAD") == ["docs/a.py", "src/a.py"]
    git(repo, "mv", "docs/a.py", "src/a.py")
    (repo / "src" / "a.py").rename(repo / "docs" / "a moved.py")   # unstaged delete + untracked file
    assert wr._changed_since(repo, "HEAD") == ["docs/a moved.py", "src/a.py"]


def test_copy_is_reported_on_both_sides(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "docs/big.md", "line\n" * 40, "base doc")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "dev")
    shutil.copy(repo / "docs" / "big.md", repo / "src" / "big.md")
    (repo / "docs" / "big.md").write_text("line\n" * 40 + "more\n")   # a touched source lets git find the copy
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "copy")
    assert "C" in git(repo, "diff", "--name-status", "--find-copies", "dev...HEAD").split()[-3][0]
    assert {"docs/big.md", "src/big.md"} <= set(diff_paths(repo, "dev...HEAD"))


def test_diff_paths_is_none_outside_git(tmp_path: Path) -> None:
    assert diff_paths(tmp_path, "HEAD") is None


# --- F6 -------------------------------------------------------------------

def _ready(repo: Path, name: str, *, node_id: str = "M1.1", branch: str = "feature/rm-thing") -> Path:
    t = resolve_target(repo, "M1.1")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(f"---\nnode_id: {node_id}\nagent: x\nbranch: {branch}\ncommit: '{t.commit}'\n"
                 f"base: '{t.base}'\nchanged_paths: [src/a.py]\nverify:\n  - {{cmd: 'echo hi', exit: 0, tail: hi}}\n---\n")
    return p


def test_a_ready_for_another_node_or_branch_is_invalid_here(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _ready(repo, "READY-wrong.md", node_id="M9.9", branch="feature/other")
    assert latest_ready(repo, "M1.1") is None
    st = review_cli._node_status(repo, "M1.1")
    assert st["state"] == "waiting"
    assert any("node_id is 'M9.9', not 'M1.1'" in e for r in st["ready"] for e in r["errors"])
    assert "READY-wrong.md" not in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    # Right node, wrong branch: still not this node's hand-off.
    _ready(repo, "READY-wrong.md", branch="feature/other")
    assert latest_ready(repo, "M1.1", "feature/rm-thing") is None
    assert "branch is 'feature/other', not the registered 'feature/rm-thing'" in review_cli._node_status(repo, "M1.1")["ready"][0]["errors"][0]
    _ready(repo, "READY-right.md")
    assert latest_ready(repo, "M1.1", "feature/rm-thing").path.name == "READY-right.md"
    assert review_cli._node_status(repo, "M1.1")["state"] == "in-review"


# --- F12 ------------------------------------------------------------------

def _key(tmp_path: Path, name: str) -> tuple[Path, str]:
    key = tmp_path / f"{name}_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, (tmp_path / f"{name}_key.pub").read_text(encoding="utf-8").strip()


def _roster(opus_pub: str | None, human_pub: str | None = None, *, signed: bool = True) -> str:
    human = (f"  - {{id: human, family: human, roles: [coordinator, reviewer], public_key: \"{human_pub}\"}}\n"
             if human_pub else "  - {id: human, family: human, roles: [coordinator, reviewer]}\n")
    opus = (f"  - {{id: opus, family: anthropic, roles: [reviewer], public_key: \"{opus_pub}\"}}\n"
            if opus_pub else "  - {id: opus, family: anthropic, roles: [reviewer]}\n")
    return ("version: 1\nroster:\n" + human + opus +
            f"policy: {{reviewers_required: 1, signed_reviews: {'true' if signed else 'false'}}}\n")


def _write(repo: Path, data: dict, body: str) -> None:
    review_path(repo, "M1.1", "opus").write_text(render_front_matter(data, body))


def test_notes_digest_normalises_line_endings_and_trailing_whitespace() -> None:
    assert rs.notes_digest("a\r\nb\r\n") == rs.notes_digest("a\nb") == rs.notes_digest("a\nb\n\n  ")
    assert rs.notes_digest("a\nb") != rs.notes_digest("a\nc")


@needs_keygen
def test_a_signed_record_binds_its_notes(tmp_path: Path) -> None:
    key, pub = _key(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster(pub))
    head = git(repo, "rev-parse", "HEAD")
    notes = tmp_path / "notes.md"
    notes.write_text(review_text(head, model="opus") + "Looked at src/a.py.\n")
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)])
    assert (e.value.code or 0) == 0
    rec = load_review(review_path(repo, "M1.1", "opus"))
    assert rec.data["notes_sha256"] == rs.notes_digest("notes\nLooked at src/a.py.\n")
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
    key, pub = _key(tmp_path, "opus")
    data = {"node_id": "M1.1", "model": "opus", "verdict": "approve", "commit": "abc1234"}
    sig = rs.sign(data, key)
    assert rs.verify(data, sig, pub, "opus") == (True, "")
    ok, why = rs.verify(data, sig, pub, "sol")
    assert not ok and "record model 'opus' is not the signer identity 'sol'" in why
    ok, why = rs.verify({**data, "model": "sol"}, sig, pub, "sol")     # relabelled record: signature breaks
    assert not ok and "not the signer identity" not in why


def test_packet_labels_committed_working_tree_and_missing_summaries(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rel = "work/implementation-summary-M1.1.md"
    t = resolve_target(repo, "M1.1")
    text = "\n".join(rp._summary(repo, t))
    assert rp.SUMMARY_MISSING in text and rp.ASSERTED not in text and rp.ASSERTED_WORKING_TREE not in text
    (repo / "work").mkdir()
    (repo / rel).write_text("From the tree.\n")
    text = "\n".join(rp._summary(repo, t))
    assert rp.ASSERTED_WORKING_TREE in text and "From the tree." in text and rp.ASSERTED not in text
    commit_file(repo, rel, "Committed.\n", "summary")
    text = "\n".join(rp._summary(repo, resolve_target(repo, "M1.1")))
    assert rp.ASSERTED in text and "Committed." in text and rp.ASSERTED_WORKING_TREE not in text


# --- human approval with a wrong key --------------------------------------

@needs_keygen
def test_a_wrong_human_key_writes_no_record_and_the_reason_is_printed(tmp_path: Path, monkeypatch, capsys) -> None:
    _human_key, human_pub = _key(tmp_path, "human")
    wrong_key, _wrong_pub = _key(tmp_path, "wrong")
    _opus_key, opus_pub = _key(tmp_path, "opus")
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


def test_post_write_gate_failure_prints_its_problems(tmp_path: Path, monkeypatch, capsys) -> None:
    """The record is written, then the gate still fails: every problem is printed, not only the generic error."""
    repo = make_review_repo(tmp_path, orchestration=_roster(None, signed=False))
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nx\n")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _p="": "a")
    monkeypatch.setattr(mir, "evaluate_gate", _gate_then_stale(mir.evaluate_gate))
    with pytest.raises(SystemExit) as e:
        mir.main(["--repo-root", str(repo)])
    captured = capsys.readouterr()
    assert e.value.code == 1
    assert "[ok] wrote" in captured.out and "- need 1 approvals at this commit, have 0" in captured.err


def _gate_then_stale(real):
    """After the human record lands, pretend the branch moved on so the new record is stale."""
    calls = {"n": 0}

    def fake(repo_root, node, commit, **kw):
        calls["n"] += 1
        if calls["n"] >= 2 and review_path(repo_root, "M1.1", "human").exists():
            commit_file(repo_root, "src/later.py", "x\n", "after approval")
            commit = git(repo_root, "rev-parse", "HEAD")
        return real(repo_root, node, commit, **kw)

    return fake
