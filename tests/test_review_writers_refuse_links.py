"""M21.38: review writers and the review lock refuse any symlink from the project root down."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from tests.review_delegate_helpers import delegate_repo, run_review_cli, set_steps, verdict_step
from tests.review_repo_helpers import git, make_review_repo, review_text
from tests.test_models_and_prompt import run_main
from tests.test_review_cli import ONE_AI
from tests.test_review_gate import TWO_FAMILIES

from specy_road import safe_write
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import role_prompt
from specy_road.bundled_scripts.registration_pickup_commit import registration_commit_message
from specy_road.review_delegate import delegate
from specy_road.review_delegate_packet import ensure_packet
from specy_road.review_files import archive_review, project_of, review_path, reviews_dir, write_review
from specy_road.review_policy_pin import pinned_message
from specy_road.review_rejected import rejected_path, write_rejected
from specy_road.review_target import resolve_target
from specy_road.reviewer_run_failure import run_path, save_run

LOCKS = ("lock-dangling", "lock-in", "node", "reviews", "work")
CALLERS = ("delegate", "prompt", "record", "accept", "mark")


def _tree(root: Path) -> list[tuple[str, str]]:
    """Each entry under ``root`` by lstat: a link's target, or a file's bytes. Symlink directories are not entered."""
    rows: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            rel = str(path.relative_to(root))
            if path.is_symlink():
                rows.append((rel, "link:" + os.readlink(path)))
            elif path.is_file():
                rows.append((rel, path.read_bytes().decode()))
    return sorted(rows)


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "record.md").write_bytes(b"record\n")
    (outside / "inner").symlink_to(outside / "record.md")
    return outside


def _replace(path: Path, target: Path, *, directory: bool) -> None:
    if path.is_symlink() or path.exists():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.symlink_to(target, target_is_directory=directory)


def _plant(repo: Path, kind: str, outside: Path) -> Path:
    """The symlink ``kind`` asks for; returns the path the refusal must name."""
    node = reviews_dir(repo, "M1.1")
    if kind == "lock-dangling":
        node.mkdir(parents=True, exist_ok=True)
        link = node / ".review-run.lock"
        link.symlink_to(outside / "missing.lock")
        return link
    if kind == "lock-in":
        node.mkdir(parents=True, exist_ok=True)
        link = node / ".review-run.lock"
        link.symlink_to(repo / "src" / "a.py")
        return link
    if kind == "node":
        node.parent.mkdir(parents=True, exist_ok=True)
        _replace(node, outside, directory=True)
        return node
    if kind == "reviews":
        (repo / "work").mkdir(exist_ok=True)
        _replace(repo / "work" / "reviews", outside, directory=True)
        return repo / "work" / "reviews"
    _replace(repo / "work", outside, directory=True)
    return repo / "work"


def _policy_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path / "policy", orchestration=TWO_FAMILIES)
    (repo / "work").mkdir()
    git(repo, "checkout", "-q", "dev")
    message = pinned_message(repo, registration_commit_message("thing", include_ci_skip=True))
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "rebase", "-q", "dev")
    git(repo, "checkout", "-q", "dev")
    orch = repo / "roadmap" / "orchestration.yaml"
    orch.write_text(orch.read_text().replace("{id: composer, family: cursor, roles: [executor]}",
                                             "{id: composer, family: cursor, roles: [executor, reviewer]}"))
    git(repo, "add", "-A", "--", "roadmap/orchestration.yaml")
    git(repo, "commit", "-qm", "policy")
    git(repo, "checkout", "-q", "feature/rm-thing")
    return repo


def _repo(tmp_path: Path, caller: str) -> tuple[Path, Path | None]:
    if caller == "accept":
        return _policy_repo(tmp_path), None
    if caller == "record":
        return make_review_repo(tmp_path, orchestration=ONE_AI), None
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    return repo, spec


def _invoke(caller: str, repo: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    if caller == "delegate":
        return run_review_cli("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0",
                              "--repo-root", str(repo))
    if caller == "prompt":
        return run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
                        "--run", "--repo-root", str(repo))
    if caller == "record":
        notes = repo.parent / "notes.md"
        notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
        return run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                              "--file", str(notes), "--repo-root", str(repo))
    if caller == "accept":
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt="": "M1.1")
        return run_review_cli("review", "accept-policy", "M1.1", "--repo-root", str(repo))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "a")
    with pytest.raises(SystemExit) as caught:
        mir.main(["--allow-missing-summary", "--repo-root", str(repo)])
    return caught.value.code or 0


@pytest.mark.parametrize("kind", LOCKS)
@pytest.mark.parametrize("caller", CALLERS)
def test_the_lock_refuses_a_symlink_before_any_filing(tmp_path: Path, monkeypatch, capsys, caller: str,
                                                      kind: str) -> None:
    repo, spec = _repo(tmp_path, caller)
    outside = _outside(tmp_path)
    before = _tree(outside)
    link = _plant(repo, kind, outside)
    source = (repo / "src" / "a.py").read_bytes()

    code = _invoke(caller, repo, monkeypatch)
    err = capsys.readouterr().err

    assert code == 1 and str(link) in err and "Traceback" not in err
    assert _tree(outside) == before
    assert (repo / "src" / "a.py").read_bytes() == source
    if spec is not None:
        assert not spec.with_name("calls.json").exists()


def _record(repo: Path, *, notes: str | None = None) -> int:
    text = notes or review_text(git(repo, "rev-parse", "HEAD"), model="opus")
    path = repo.parent / "notes.md"
    path.write_text(text)
    return run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                          "--file", str(path), "--repo-root", str(repo))


@pytest.mark.parametrize("dangling", [True, False])
def test_review_record_refuses_a_linked_live_record(tmp_path: Path, capsys, dangling: bool) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    before = _tree(outside)
    link = review_path(repo, "M1.1", "opus")
    link.parent.mkdir(parents=True, exist_ok=True)
    target = outside / "made.md" if dangling else outside / "record.md"
    link.symlink_to(target)

    code = _record(repo)
    err = capsys.readouterr().err

    assert code == 1 and str(link) in err and "Traceback" not in err
    assert _tree(outside) == before
    assert not target.exists() if dangling else target.read_bytes() == b"record\n"


def test_review_record_leaves_the_record_and_marker_when_history_is_linked(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    before = _tree(outside)
    node = reviews_dir(repo, "M1.1")
    node.mkdir(parents=True)
    record, marker = review_path(repo, "M1.1", "opus"), rejected_path(node, "opus")
    record.write_bytes(b"old record\n")
    marker.write_bytes(b"old marker\n")
    (node / "history").symlink_to(outside, target_is_directory=True)

    code = _record(repo)
    err = capsys.readouterr().err

    assert code == 1 and str(node / "history") in err and "Traceback" not in err
    assert record.read_bytes() == b"old record\n" and marker.read_bytes() == b"old marker\n"
    assert _tree(outside) == before


def test_write_review_does_not_unlink_through_a_linked_node_directory(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    (outside / "review-x.md").write_bytes(b"stay\n")
    before = _tree(outside)
    node = reviews_dir(repo, "M1.1")
    node.parent.mkdir(parents=True, exist_ok=True)
    _replace(node, outside, directory=True)

    with pytest.raises(safe_write.SafeWriteError) as caught:
        write_review(node / "REVIEW-x.md", "new")

    assert str(node) in str(caught.value)
    assert _tree(outside) == before and (outside / "review-x.md").read_bytes() == b"stay\n"


def test_archive_review_refuses_a_linked_history_directory(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    before = _tree(outside)
    node = reviews_dir(repo, "M1.1")
    node.mkdir(parents=True)
    (node / "history").symlink_to(outside, target_is_directory=True)

    with pytest.raises(safe_write.SafeWriteError) as caught:
        archive_review(repo, "M1.1", "opus", "copy\n")

    assert str(node / "history") in str(caught.value) and _tree(outside) == before


@pytest.mark.parametrize("kind", ("file", "reviews", "work"))
def test_a_refused_marker_writes_nothing_outside(tmp_path: Path, capsys, kind: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    before = _tree(outside)
    node = reviews_dir(repo, "M1.1")
    if kind == "file":
        node.mkdir(parents=True)
        link = rejected_path(node, "opus")
        link.symlink_to(outside / "record.md")
    else:
        link = _plant(repo, kind, outside)
    data = yaml.safe_load(review_text(git(repo, "rev-parse", "HEAD"), model="opus").split("---")[1])
    data["findings"]["correctness"] = ["Advisory: x drops y"]
    notes = "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n"

    code = _record(repo, notes=notes)
    err = capsys.readouterr().err

    assert code == 1 and str(link) in err and "Traceback" not in err
    assert _tree(outside) == before


@pytest.mark.parametrize("suffix", ("", "-resume", "-repair", "-repair-full"))
def test_delegate_refuses_a_linked_prompt_before_launch(tmp_path: Path, capsys, suffix: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    outside = _outside(tmp_path)
    before = _tree(outside)
    path = repo / "work" / f"prompt-M1.1-reviewer-opus{suffix}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(outside / "record.md")
    if suffix.startswith("-repair"):
        commit = git(repo, "rev-parse", "HEAD")
        save_run(run_path(repo, "M1.1", "opus"), {"node_id": "M1.1", "model": "opus", "harness": "claude-code",
                 "commit": commit, "state": "incomplete", "session_id": "sess-1", "refusal": "no",
                 "refusal_kind": "record", "attempts": []})
        set_steps(repo, spec, verdict_step(repo))
        code = run_review_cli("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--resume",
                              "--repo-root", str(repo))
    else:
        set_steps(repo, spec, verdict_step(repo))
        code = run_review_cli("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0",
                              "--repo-root", str(repo))

    err = capsys.readouterr().err
    assert code == 1 and str(path) in err and "Traceback" not in err
    assert _tree(outside) == before and not spec.with_name("calls.json").exists()


def test_a_refused_then_repair_run_does_not_launch_the_repair(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    outside = _outside(tmp_path)
    before = _tree(outside)
    repair = repo / "work" / "prompt-M1.1-reviewer-opus-repair.md"
    repair.parent.mkdir(parents=True, exist_ok=True)
    repair.symlink_to(outside / "record.md")
    step = verdict_step(repo)
    step["answer"] = {**step["answer"], "notes": "## Findings\n\nAdvisory: x drops y\n"}
    set_steps(repo, spec, step, verdict_step(repo))

    code = run_review_cli("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--repo-root", str(repo))

    err = capsys.readouterr().err
    calls = spec.with_name("calls.json")
    assert code == 1 and str(repair) in err and "Traceback" not in err
    assert _tree(outside) == before and len(json.loads(calls.read_text())) == 1


@pytest.mark.parametrize("dangling", [True, False])
def test_accept_policy_refuses_a_linked_acceptance_file(tmp_path: Path, monkeypatch, capsys, dangling: bool) -> None:
    repo = _policy_repo(tmp_path)
    outside = _outside(tmp_path)
    before = _tree(outside)
    path = reviews_dir(repo, "M1.1") / "POLICY-ACCEPTED.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    target = outside / ("made.yaml" if dangling else "record.md")
    path.symlink_to(target)

    code = _invoke("accept", repo, monkeypatch)
    err = capsys.readouterr().err

    assert code == 1 and str(path) in err and "Traceback" not in err
    assert _tree(outside) == before


@pytest.mark.parametrize("dangling", [True, False])
def test_human_approval_refuses_a_linked_record(tmp_path: Path, monkeypatch, capsys, dangling: bool) -> None:
    repo, _spec = delegate_repo(tmp_path)
    outside = _outside(tmp_path)
    before = _tree(outside)
    path = review_path(repo, "M1.1", "human")
    path.parent.mkdir(parents=True, exist_ok=True)
    target = outside / ("made.md" if dangling else "record.md")
    path.symlink_to(target)

    code = _invoke("mark", repo, monkeypatch)
    err = capsys.readouterr().err

    assert code == 1 and str(path) in err and "Traceback" not in err
    assert _tree(outside) == before


def test_prompt_run_refuses_its_default_file_before_launch(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    outside = _outside(tmp_path)
    before = _tree(outside)
    path = repo / "work" / "prompt-M1.1-reviewer-opus.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(outside / "record.md")
    set_steps(repo, spec, verdict_step(repo))

    code = run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo))
    err = capsys.readouterr().err

    assert code == 1 and str(path) in err and "Traceback" not in err
    assert _tree(outside) == before and not spec.with_name("calls.json").exists()


def test_ensure_packet_refuses_a_linked_node_directory(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    before = _tree(outside)
    node = reviews_dir(repo, "M1.1")
    node.parent.mkdir(parents=True, exist_ok=True)
    _replace(node, outside, directory=True)

    with pytest.raises(safe_write.SafeWriteError) as caught:
        ensure_packet(repo, resolve_target(repo, "M1.1", None), None)

    assert str(node) in str(caught.value) and _tree(outside) == before
    assert not (outside / "PACKET.md").exists()


def test_a_reviewer_that_replaces_reviews_with_a_link_is_a_review_failure(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    outside = _outside(tmp_path)
    (outside / "REVIEW-opus.md").write_bytes(b"secret\n")
    (outside / "planted").symlink_to(outside / "REVIEW-opus.md")
    before = _tree(outside)
    set_steps(repo, spec, {**verdict_step(repo), "symlink": {"path": str(repo / "work" / "reviews"),
                                                             "target": str(outside)}})

    run = delegate(repo, "M1.1", "opus", sleep=lambda _s: None, retries=0)

    assert run["outcome"] == "review_failure" and run["state"] == "incomplete"
    assert _tree(outside) == before
    assert not (outside / "M1.1").exists()


def test_write_rejected_refuses_a_linked_ancestor_before_mkdir(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    outside = _outside(tmp_path)
    before = _tree(outside)
    _replace(repo / "work", outside, directory=True)
    node = project_of(repo / "work") / "work" / "reviews" / "M1.1"

    got = write_rejected(node, "opus", "abc", "error: x")

    err = capsys.readouterr().err
    assert str(repo / "work") in err and "Traceback" not in err
    assert got == node / "REJECTED-opus.md" and _tree(outside) == before
