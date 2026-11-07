"""Tests for abort-task-pickup (undo do-next-available-task)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
import pytest

from specy_road.bundled_scripts import abort_task_pickup as atp


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _claimed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A feature branch with a resolvable registry claim."""
    monkeypatch.setattr(atp, "current_branch", lambda _root: "feature/rm-ab")
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: ("ab", {"version": 1, "entries": []}, {"node_id": "M9.1"}, []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )


def _git(root, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path) -> None:
    """A git repo with one tracked source file, as a pickup leaves it."""
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "T"]):
        _git(tmp_path, *args)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    _git(tmp_path, "add", "src/app.py")
    _git(tmp_path, "commit", "-q", "-m", "init")


def _refusal(tmp_path, capsys) -> str:
    """Run abort on a claimed branch and return its stderr; it must exit 1."""
    with pytest.raises(SystemExit) as e:
        atp.main(["--repo-root", str(tmp_path)])
    assert e.value.code == 1
    return capsys.readouterr().err


def test_abort_refuses_tracked_change_naming_path_and_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    _repo(tmp_path)
    _claimed(monkeypatch)
    (tmp_path / "src" / "app.py").write_text("x = 2\n")
    err = _refusal(tmp_path, capsys)
    assert "tracked changes block abort-task-pickup: it checks out 'main'" in err
    assert "  src/app.py (unstaged edit)" in err
    assert "stash" not in err   # the project rules forbid it; abort must not suggest it
    _git(tmp_path, "add", "src/app.py")
    (tmp_path / "src" / "app.py").write_text("x = 3\n")
    assert "  src/app.py (staged edit, unstaged edit)" in _refusal(tmp_path, capsys)


class _PastTheCheck(Exception):
    pass


def test_untracked_files_do_not_block_abort(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Coordinator notes under work/ (and pickup's own brief) survive the checkout; only tracked changes block."""
    _repo(tmp_path)
    (tmp_path / "work").mkdir()
    for name in ("brief-M9.1.md", "coordinator-notes.md", "handoff-M9.2.txt"):
        (tmp_path / "work" / name).write_text("note\n")
    (tmp_path / "scratch.txt").write_text("untracked outside work/\n")
    _claimed(monkeypatch)
    monkeypatch.setattr(atp, "resolve_integration_defaults", lambda *_a, **_k: ("dev", "origin", []))

    def fetch(_root, *args: str) -> None:
        raise _PastTheCheck(args)

    monkeypatch.setattr(atp, "git_run", fetch)
    with pytest.raises(_PastTheCheck) as e:
        atp.main(["--repo-root", str(tmp_path)])
    assert e.value.args[0] == ("fetch", "origin")
    assert (tmp_path / "work" / "coordinator-notes.md").is_file()


def test_tracked_change_under_work_still_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    _repo(tmp_path)
    _claimed(monkeypatch)
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "notes.md").write_text("tracked\n")
    _git(tmp_path, "add", "work/notes.md")
    assert "  work/notes.md (staged new file)" in _refusal(tmp_path, capsys)


def test_abort_names_a_conflicted_path(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    _repo(tmp_path)
    _git(tmp_path, "checkout", "-q", "-b", "other")
    (tmp_path / "src" / "app.py").write_text("x = 'other'\n")
    _git(tmp_path, "commit", "-q", "-am", "other")
    _git(tmp_path, "checkout", "-q", "-")
    (tmp_path / "src" / "app.py").write_text("x = 'here'\n")
    _git(tmp_path, "commit", "-q", "-am", "here")
    subprocess.run(["git", "merge", "-q", "other"], cwd=tmp_path, capture_output=True)
    _claimed(monkeypatch)
    assert "  src/app.py (unmerged (conflict))" in _refusal(tmp_path, capsys)


def test_refused_checkout_of_the_base_exits_with_a_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    """An untracked file the base tracks makes git refuse the checkout: a clean exit, not a traceback."""
    _git_init(tmp_path)
    _claimed(monkeypatch)
    monkeypatch.setattr(atp, "git_capture", lambda *_a, **_k: "")
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 0)

    def git(_root, *args: str) -> None:
        if args[0] == "checkout":
            raise subprocess.CalledProcessError(1, ["git", *args])

    monkeypatch.setattr(atp, "git_run", git)
    err = _refusal(tmp_path, capsys)
    assert "could not check out 'main'" in err and "move it aside" in err


def test_abort_refuses_non_feature_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _git_init(tmp_path)
    monkeypatch.setattr(atp, "current_branch", lambda _root: "main")
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_abort_refuses_ahead_of_remote_without_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _git_init(tmp_path)
    # A pushed claim: nothing ahead of origin is a local-only registration.
    monkeypatch.setattr(atp, "git_capture", lambda *_a, **_k: "")
    monkeypatch.setattr(atp, "current_branch", lambda _root: "feature/rm-x")
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: (
            "x",
            {"version": 1, "entries": []},
            {"node_id": "M1.1"},
            [],
        ),
    )
    monkeypatch.setattr(atp, "git_run", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 2)
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_abort_pickup_git_order(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _git_init(tmp_path)
    calls: list[list[str]] = []

    def fake_git(_root, *args: str) -> None:
        calls.append(list(args))

    branches = iter(["feature/rm-ab", "dev"])

    def fake_branch(_root) -> str:
        return next(branches)

    reg_doc = {
        "version": 1,
        "entries": [
            {
                "codename": "ab",
                "node_id": "M9.1",
                "branch": "feature/rm-ab",
                "touch_zones": ["src/"],
            }
        ],
    }
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        yaml.dump(reg_doc),
        encoding="utf-8",
    )

    # A pushed claim: nothing ahead of origin is a local-only registration.
    monkeypatch.setattr(atp, "git_capture", lambda *_a, **_k: "")
    monkeypatch.setattr(atp, "current_branch", fake_branch)
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: ("ab", reg_doc, {"node_id": "M9.1"}, []),
    )
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 0)
    monkeypatch.setattr(atp, "_sync_integration_branch_ff", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "git_run", fake_git)
    monkeypatch.setattr(atp, "_delete_feature_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_remove_pickup_work_files", lambda *_a, **_k: None)

    atp.main(["--repo-root", str(tmp_path)])

    assert calls[0] == ["fetch", "origin"]
    assert calls[1] == ["add", "roadmap/registry.yaml"]
    assert calls[2][0] == "commit"
    assert "abort task pickup" in calls[2][2]
    assert calls[3] == ["push", "origin", "main"]


def test_abort_allows_ahead_with_force(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _git_init(tmp_path)
    calls: list[str] = []

    def fake_git(_root, *args: str) -> None:
        calls.append(args[0])

    branches = iter(["feature/rm-ab", "dev"])

    def fake_branch(_root) -> str:
        return next(branches)

    reg_doc = {
        "version": 1,
        "entries": [
            {
                "codename": "ab",
                "node_id": "M9.1",
                "branch": "feature/rm-ab",
                "touch_zones": ["src/"],
            }
        ],
    }
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        yaml.dump(reg_doc),
        encoding="utf-8",
    )

    # A pushed claim: nothing ahead of origin is a local-only registration.
    monkeypatch.setattr(atp, "git_capture", lambda *_a, **_k: "")
    monkeypatch.setattr(atp, "current_branch", fake_branch)
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: (
            "ab",
            {"version": 1, "entries": []},
            {"node_id": "M9.1"},
            [],
        ),
    )
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 3)
    monkeypatch.setattr(atp, "_sync_integration_branch_ff", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "git_run", fake_git)
    monkeypatch.setattr(atp, "_delete_feature_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_remove_pickup_work_files", lambda *_a, **_k: None)

    atp.main(["--repo-root", str(tmp_path), "--force"])

    assert "push" in calls


def _claim_leaf(tmp_path, shape: str):
    """A claimed leaf in a linked worktree; the main checkout is on ``park``, not ``dev``."""
    from tests.review_repo_helpers import make_layout_finish_repo

    git_top, project = make_layout_finish_repo(tmp_path / "src", shape)
    return git_top, project


def _open_leaf(git_top, tmp_path, shape: str):
    bare = tmp_path / "remote.git"
    _git(tmp_path, "clone", "-q", "--bare", str(git_top), str(bare))
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    _git(git_top, "remote", "add", "origin", str(bare))
    _git(git_top, "fetch", "-q", "origin")
    _git(git_top, "checkout", "-q", "-b", "park")
    leaf_top = tmp_path / "leaf"
    _git(git_top, "worktree", "add", "-q", str(leaf_top), "feature/rm-thing")
    return leaf_top / "sr" if shape == "nested" else leaf_top


def _place_main_copies(git_top, project, shape: str, kind: str) -> None:
    work = project / "work"
    brief, prompt = work / "brief-M1.1.md", work / "prompt-M1.1.md"
    notes = project / "notes.md"
    notes.write_text("target\n", encoding="utf-8")
    if kind == "work_link":
        real = project / "elsewhere"
        real.mkdir()
        (real / "brief-M1.1.md").write_text("stay\n", encoding="utf-8")
        work.symlink_to(real, target_is_directory=True)
        return
    work.mkdir()
    if kind == "tracked":
        brief.write_text("tracked\n", encoding="utf-8")
        prompt.write_text("tracked\n", encoding="utf-8")
        _git(git_top, "add", "-A")
        _git(git_top, "commit", "-qm", "track briefs")
    elif kind == "symlink":
        rel = "notes.md" if shape == "embedded" else "sr/notes.md"
        _git(git_top, "add", rel)
        _git(git_top, "commit", "-qm", "target")
        brief.symlink_to(notes)
        prompt.write_text("drop\n", encoding="utf-8")
    else:
        brief.write_text("brief\n", encoding="utf-8")
        prompt.write_text("prompt\n", encoding="utf-8")
    (work / "notes.md").write_text("other\n", encoding="utf-8")


@pytest.mark.parametrize("shape", ["embedded", "nested"])
@pytest.mark.parametrize("kind", ["untracked", "tracked", "symlink", "work_link"])
def test_abort_from_a_linked_worktree_cleans_the_main_checkout(
    tmp_path, shape: str, kind: str, capsys,
) -> None:
    """Abort from a linked worktree removes the main checkout's untracked brief and prompt only."""
    git_top, project = _claim_leaf(tmp_path, shape)
    _place_main_copies(git_top, project, shape, kind)
    leaf = _open_leaf(git_top, tmp_path, shape)
    atp.main(["--repo-root", str(leaf), "--force"])
    out = capsys.readouterr().out
    work = project / "work"
    brief, prompt = work / "brief-M1.1.md", work / "prompt-M1.1.md"
    prefix = "sr/" if shape == "nested" else ""
    if kind == "untracked":
        assert not brief.exists() and not prompt.exists()
        assert f"[ok] removed {prefix}work/brief-M1.1.md" in out
        assert (work / "notes.md").read_text(encoding="utf-8") == "other\n"
    elif kind == "tracked":
        assert brief.read_text(encoding="utf-8") == "tracked\n"
        assert prompt.read_text(encoding="utf-8") == "tracked\n"
    elif kind == "symlink":
        assert brief.is_symlink() and (project / "notes.md").read_text(encoding="utf-8") == "target\n"
        assert not prompt.exists()
    else:
        assert work.is_symlink()
        assert (project / "elsewhere" / "brief-M1.1.md").read_text(encoding="utf-8") == "stay\n"
