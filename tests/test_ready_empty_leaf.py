"""``specy-road ready`` refuses a leaf with no committed in-zone work, and status does not offer it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo
from tests.test_nested_repo_worktrees import add_nested_repo

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import render_front_matter, reviews_dir

#: Rows of one table: dirty in-zone paths are refused and named; the boundary rows and nested-only work are not.
_LEAF = {
    "staged": ("src/a.py", 1),
    "unstaged": ("src/a.py", 1),
    "deleted": ("src/a.py", 1),
    "untracked": ("src/new.py", 1),
    "outside": (None, 0),
    "prefix": (None, 0),
    "no-commit": (None, 1),
    "nested": (None, 0),
}


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _ready_path(repo: Path) -> Path:
    return reviews_dir(repo, "M1.1") / "READY-opus.md"


def _prepare(tmp_path: Path, kind: str) -> Path:
    repo = make_review_repo(tmp_path)
    if kind == "no-commit":
        git(repo, "reset", "--hard", "dev")
        commit_file(repo, "docs/only.md", "outside\n", "outside the zone")
        return repo
    if kind == "nested":
        git(repo, "reset", "--hard", "dev")
        nested = add_nested_repo(repo, "src/engine", "dev")
        git(nested, "checkout", "-q", "-b", "feature/rm-thing")
        commit_file(nested, "core.py", "x = 2\n", "leaf work in the nested repo")
        return repo
    if kind == "staged":
        (repo / "src/a.py").write_text("staged\n", encoding="utf-8")
        git(repo, "add", "src/a.py")
    elif kind == "unstaged":
        (repo / "src/a.py").write_text("unstaged\n", encoding="utf-8")
    elif kind == "deleted":
        git(repo, "rm", "-q", "src/a.py")
    elif kind == "untracked":
        (repo / "src/new.py").write_text("new\n", encoding="utf-8")
    elif kind == "outside":
        (repo / "docs/x.md").write_text("edited\n", encoding="utf-8")
    elif kind == "prefix":
        (repo / "src2").mkdir()
        (repo / "src2/a.py").write_text("sibling\n", encoding="utf-8")
    return repo


@pytest.mark.parametrize("kind", list(_LEAF))
def test_ready_refuses_only_in_zone_dirt_and_an_empty_leaf(tmp_path: Path, capsys, kind: str) -> None:
    repo = _prepare(tmp_path, kind)
    named, code = _LEAF[kind]
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == code
    err = capsys.readouterr().err
    ready = _ready_path(repo)
    if code:
        assert not ready.exists()
        if named:
            assert named in err
        else:
            assert "no committed in-zone path differs from the integration merge base" in err
            assert "docs/only.md" not in err
    else:
        assert ready.is_file()
        assert "uncommitted in-zone changes" not in err
        assert "no committed in-zone path" not in err


def test_a_preflight_refusal_runs_no_command(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "reset", "--hard", "dev")
    monkeypatch.chdir(repo)
    marker = tmp_path / "marker"
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run", f"touch {marker}", "--repo-root", str(repo)) == 1
    assert not marker.exists()
    assert not _ready_path(repo).exists()


@pytest.mark.parametrize("cmd", [
    "python3 -c \"open('src/from-run.py','w').write('x')\"",
    "git commit --allow-empty -m move-head",
])
def test_a_run_that_dirties_a_zone_or_moves_head_keeps_the_existing_ready(
        tmp_path: Path, monkeypatch, capsys, cmd: str) -> None:
    repo = make_review_repo(tmp_path)
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == 0
    ready = _ready_path(repo)
    before = ready.read_bytes()
    monkeypatch.chdir(repo)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run", cmd, "--repo-root", str(repo)) == 1
    assert ready.read_bytes() == before
    err = capsys.readouterr().err
    assert "src/from-run.py" in err or "HEAD moved during --run" in err


def _hand_ready(repo: Path, *, blocked: bool) -> None:
    sha = git(repo, "rev-parse", "HEAD")
    data = {
        "node_id": "M1.1", "agent": "opus", "branch": "feature/rm-thing",
        "commit": sha, "base": sha, "changed_paths": [], "verify": [{"cmd": "true", "exit": 0}],
    }
    if blocked:
        data["blocked_on"] = [{"acceptance": "A1", "reason": "cannot without weakening a test"}]
    path = _ready_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_front_matter(data), encoding="utf-8")


def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    _cli("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)["nodes"][0]


@pytest.mark.parametrize("kind", ["empty", "blocked", "nonempty"])
def test_status_rows_for_an_empty_a_blocked_and_a_nonempty_ready(tmp_path: Path, capsys, kind: str) -> None:
    repo = make_review_repo(tmp_path)
    if kind == "nonempty":
        assert _cli("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == 0
    else:
        git(repo, "reset", "--hard", "dev")
        _hand_ready(repo, blocked=kind == "blocked")
    capsys.readouterr()
    text_code = _cli("handoff", "status", "M1.1", "--repo-root", str(repo))
    text = capsys.readouterr().out
    st = _status(repo, capsys)
    if kind == "empty":
        assert text_code == 1 and st["state"] == "waiting"
        assert "INVALID" in text and "commit resolves to its base" in text
        assert "--role reviewer" not in text
        assert st["ready"][0]["errors"]
    elif kind == "blocked":
        assert st["state"] == "executor_blocked" and "executor_blocked" in text
        assert "INVALID" not in text and st["ready"][0]["errors"] == []
        assert "A1: cannot without weakening a test" in text
    else:
        assert st["state"] == "in-review" and "READY-opus.md (ok)" in text
        assert "INVALID" not in text and st["ready"][0]["errors"] == []
