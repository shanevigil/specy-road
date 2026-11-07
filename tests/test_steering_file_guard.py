"""M21.7: executors cannot change git steering unnoticed.

Fake executor turns that change git hooks and config (a linked worktree, the main checkout beside it, ``.venv``
linked by ``env_setup.link``, a second worktree holding the integration branch), the clean turn, and the sticky flag
and its listing by ``worker reconcile``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road import steering_paths
from specy_road import worker_reconcile as wrc
from specy_road import worker_state as ws
from specy_road import worker_turn_check as tc
from specy_road.git_config_text import parse_config
from specy_road.steering_paths import FLAG_STEERING, real_path


def _layout(tmp_path: Path) -> dict[str, Path]:
    """The coordinator checkout (on its own branch, so a second worktree can hold ``dev``), the leaf's linked
    worktree with ``.venv`` linked from it, and a base interpreter outside both that ``.venv/bin/python`` names."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\nenv_setup:\n  link: [.venv]\n", "env_setup")
    git(repo, "checkout", "-q", "-b", "coordinator")
    base = tmp_path / "base-python3"
    base.write_text("the interpreter\n")
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "python").symlink_to(base)
    (repo / ".git" / "info" / "exclude").write_text(".venv\n")
    leaf, second = tmp_path / "leaf", tmp_path / "second"
    git(repo, "worktree", "add", "-q", str(leaf), "feature/rm-thing")
    git(repo, "worktree", "add", "-q", str(second), "dev")
    (leaf / ".venv").symlink_to(repo / ".venv")
    return {"repo": repo, "leaf": leaf, "second": second, "tmp": tmp_path}


def _turn(repo: Path, rec: ws.WorkerRecord, act: Callable[[], None]) -> list[dict]:
    """One executor turn as the wrapper brackets it: the watch at the start, ``act`` as the turn, the check."""
    watch = tc.TurnWatch(repo, rec)
    act()
    tc.close_turn(repo, rec, watch)
    return [e for e in ws.events_since(repo, rec.worker_id) if e.type == "post_run_check"][-1].detail["findings"]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


HOOKS_CONFIGS = {   # name: (hooks directory name, text added to the common config, a BOM first); {d} that directory
    "trailing_comment": ("hooks", "[core]\n\thooksPath = {d} # managed by ops\n", False),
    "quoted_hash_then_comment": ("hooks #x;y", '[core]\n\thooksPath = "{d}" ; note\n', False),
    "escaped_quote_and_continuation": ('ho"oks', '[core]\n\thooksPath = "{d_escaped}"\n', False),
    "crlf_continuation": ("customhooks", "[core]\r\n\thooksPath = {d_crlf}\r\n", False),   # CRLF lines, \\<CRLF> joins
    "bom_prefixed_config": ("hooks", "[core]\n\thooksPath = {d}\n", True),   # the first section, after the BOM
    # {d} is set only under a condition that does not hold: git keeps the default hooks directory
    "nonmatching_conditional_include": ("hooks", '[includeIf "gitdir:/nowhere/"]\n\tpath = {other}\n', False),
    # the default hooks directory already holds pre-commit as a link to a file; the turn writes through the link
    "unchanged_symlink_written_through": ("hooks", "", False),
}
DEFAULT_HOOKS = {"nonmatching_conditional_include", "unchanged_symlink_written_through"}


@pytest.mark.parametrize("name", sorted(HOOKS_CONFIGS))
def test_a_hook_in_the_hooks_directory_git_uses_is_found_however_the_config_reads(tmp_path: Path, name: str) -> None:
    dirname, text, bom = HOOKS_CONFIGS[name]
    p = _layout(tmp_path)
    d = tmp_path / dirname
    d.mkdir()
    other = tmp_path / "other.gitconfig"
    other.write_text(f"[core]\n\thooksPath = {d}\n")
    escaped = str(d).replace('"', '\\"')
    half = len(str(d)) // 2
    added = text.format(d=d, other=other, d_escaped=escaped[:len(escaped) // 2] + "\\\n" + escaped[len(escaped) // 2:],
                        d_crlf=str(d)[:half] + "\\\r\n" + str(d)[half:])
    config = p["repo"] / ".git" / "config"
    config.write_text("\ufeff" + added + config.read_text() if bom else config.read_text() + added)   # BOM, then the section
    # git's own reading, conditions evaluated, names the directory the turn writes a hook into
    used = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=p["leaf"], capture_output=True, text=True)
    hooks = Path(used.stdout.strip()) if used.returncode == 0 else p["repo"] / ".git" / "hooks"
    assert (hooks == d) is (name not in DEFAULT_HOOKS)
    if hooks == d:   # and the check's parse of the file agrees with git's
        assert [v for k, v in parse_config(config.read_bytes().decode()) if k == "core.hookspath"] == [str(d)]
    real = tmp_path / "real-pre-commit"
    if name == "unchanged_symlink_written_through":
        real.write_text("#!/bin/sh\n")
        (hooks / "pre-commit").symlink_to(real)
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    found = _turn(p["repo"], rec, lambda: _write(hooks / "pre-commit", "#!/bin/sh\nevil\n"))   # through a link if one
    [steer] = [f for f in found if f["kind"] == "steering_file"]
    assert steer["class"] == "git_hook" and steer["path"] == str(hooks.resolve() / "pre-commit")
    if name == "unchanged_symlink_written_through":   # the link text is unchanged; what it resolves to is not
        assert steer["before"].startswith(f"link:{real}@") and steer["after"].startswith(f"link:{real}@")
        assert steer["before"] != steer["after"] and (hooks / "pre-commit").is_symlink()
    else:
        assert steer["before"] == "absent"
    assert "git_probes_skipped" in {f["kind"] for f in found}


@pytest.mark.parametrize("snapshot", ["taken", "unavailable"])
def test_a_changed_fsmonitor_is_reported_before_any_git_command_could_run_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snapshot: str) -> None:
    """With no steering snapshot from the turn's start (whatever failed), the check fails closed: no git probe."""
    p = _layout(tmp_path)
    sentinel = tmp_path / "fsmonitor-ran"
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    if snapshot == "unavailable":
        def fail(_scope):
            raise OSError("the snapshot could not be taken")
        monkeypatch.setattr(steering_paths, "git_snapshot", fail)
    found = _turn(p["repo"], rec, lambda: git(p["leaf"], "config", "core.fsmonitor", f"touch {sentinel}"))
    assert not sentinel.exists()
    if snapshot == "unavailable":
        [error] = found
        assert error["kind"] == "check_error" and "git probes skipped" in error["summary"]
    else:
        [steer] = [f for f in found if f["kind"] == "steering_file"]
        assert steer["class"] == "git_config" and steer["path"].endswith("/.git/config")
        assert "core.fsmonitor=unset" in steer["before"] and f"core.fsmonitor=touch {sentinel}" in steer["after"]
        assert "git_probes_skipped" in {f["kind"] for f in found}
    subprocess.run(["git", "status"], cwd=p["leaf"], capture_output=True, check=False)
    assert sentinel.exists()   # the scenario is real: the probe the check skipped would have run it


def test_a_clean_turn_has_no_findings_and_leaves_the_flag_reconcile_lists_and_clears(tmp_path: Path) -> None:
    p = _layout(tmp_path)
    repo, leaf = p["repo"], p["leaf"]
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", leaf, branch="feature/rm-thing")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _turn(repo, rec, lambda: _write(hook, "#!/bin/sh\n"))

    def clean() -> None:   # its READY, its own registry entry, in-zone code
        for root in (ws.reviews_root(repo), leaf / "work" / "reviews"):   # either checkout's copy is its own READY
            _write(root / "M1.1" / "READY-opus.md", "---\nnode_id: M1.1\n---\n")
        reg = leaf / "roadmap" / "registry.yaml"
        reg.write_text(reg.read_text().replace("implementation_review: pending", "implementation_review: requested"))
        _write(leaf / "src" / "b.py", "print('b')\n")
        git(leaf, "add", "src/b.py", "roadmap/registry.yaml")
        git(leaf, "commit", "-qm", "in zone")
    assert _turn(repo, rec, clean) == []
    after = ws.load_record(repo, rec.worker_id)
    assert FLAG_STEERING in after.flags and tc.FLAG_POST_RUN not in after.flags   # sticky across a clean turn
    o = {"worker_id": rec.worker_id, "delta": wrc.reconcile(repo, rec.worker_id)[1]}
    steering = [ln.strip() for ln in wrc.reconcile_lines(o) if ln.strip().startswith(str(real_path(hook)))]
    assert len(steering) == 1 and steering[0].startswith(f"{real_path(hook)} git_hook absent ")
    assert FLAG_STEERING not in ws.load_record(repo, rec.worker_id).flags
    assert wrc.reconcile(repo, rec.worker_id)[1]["steering"] == []


# --- one rule for an input that cannot be read ---------------------------------------------------------------


def _unreadable_as(kind: str, path: Path, tmp: Path) -> None:
    """Leave ``path`` unreadable in the way ``kind`` names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    if kind == "unreadable":
        path.write_text("x\n")
        path.chmod(0)
    elif kind == "dangling_symlink":
        path.symlink_to(tmp / "missing-target")
    else:   # symlink_loop
        path.symlink_to(path.name)


def _where(p: dict[str, Path], where: str) -> tuple[Path, str]:
    """``(the path, its class)``; a git config row is a file the common config includes."""
    if where == "git_config":
        config = p["repo"] / ".git" / "config"
        config.write_text(config.read_text() + f"[include]\n\tpath = {p['tmp'] / 'extra.gitconfig'}\n")
    return {"git_config": (p["tmp"] / "extra.gitconfig", "git_config"),
            "hook": (p["repo"] / ".git" / "hooks" / "pre-commit", "git_hook")}[where]


UNREADABLE_ROWS = [   # (failure kind, where): every combination where that kind is a failure to read there
    *[(k, "hook") for k in ("unreadable", "dangling_symlink", "symlink_loop")],
    ("unreadable", "git_config"), ("symlink_loop", "git_config"),   # a missing include is left out, as git does
]


@pytest.mark.parametrize(("kind", "where"), UNREADABLE_ROWS)
def test_an_unreadable_steering_input_is_one_check_error_and_the_rest_is_still_compared(
        tmp_path: Path, kind: str, where: str) -> None:
    if kind == "unreadable" and os.geteuid() == 0:
        pytest.skip("root reads a mode-000 file")
    p = _layout(tmp_path)
    path, cls = _where(p, where)
    _unreadable_as(kind, path, tmp_path)
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    config = p["repo"] / ".git" / "config"
    found = _turn(p["repo"], rec, lambda: config.write_text(config.read_text() + "[specy]\n\tturn = 1\n"))   # unrelated
    [error] = [f for f in found if f["kind"] == "check_error" and f.get("path") == str(real_path(path))]
    assert error["class"] == cls
    [other] = [f for f in found if f["kind"] == "steering_file"]
    assert other["class"] == "git_config" and other["path"] == str(real_path(config))
    assert FLAG_STEERING in ws.load_record(p["repo"], rec.worker_id).flags
    assert "git_probes_skipped" in {f["kind"] for f in found}   # unverified git steering: no git command
    assert not [f for f in found if f.get("class") == "harness"]
