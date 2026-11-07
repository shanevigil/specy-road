"""M22.5: executors cannot change git steering unnoticed.

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
    ignored = p["repo"] / ".git" / "hooks" / "ignored-by-git"   # in a default directory git does not use here

    def act() -> None:
        _write(hooks / "pre-commit", "#!/bin/sh\nevil\n")   # through a link if one
        if hooks == d:
            _write(ignored, "#!/bin/sh\n")
    found = _turn(p["repo"], rec, act)
    [steer] = [f for f in found if f["kind"] == "steering_file"]
    assert steer["class"] == "git_hook" and steer["path"] == str(hooks.resolve() / "pre-commit")
    if name == "unchanged_symlink_written_through":   # the link is unchanged; the file it resolves to is not
        assert len(steer["before"]) == len(steer["after"]) == 64 and steer["before"] != steer["after"]
        assert (hooks / "pre-commit").is_symlink()
    else:
        assert steer["before"] == "absent"
    assert "git_probes_skipped" in {f["kind"] for f in found}


@pytest.mark.parametrize("snapshot", ["taken", "unavailable", "include_created", "include_link_created"])
def test_a_changed_fsmonitor_is_reported_before_any_git_command_could_run_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snapshot: str) -> None:
    """With no steering snapshot from the turn's start (whatever failed), the check fails closed: no git probe. An
    include the unchanged config already names, missing at the start and created by the turn (as a file, or as a
    link to a file holding the value), is a change too."""
    p = _layout(tmp_path)
    sentinel = tmp_path / "fsmonitor-ran"
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    if snapshot == "unavailable":
        def fail(_scope):
            raise OSError("the snapshot could not be taken")
        monkeypatch.setattr(steering_paths, "git_snapshot", fail)
    included = tmp_path / "later.gitconfig"
    target = tmp_path / "target.gitconfig"
    if snapshot in ("include_created", "include_link_created"):
        config = p["repo"] / ".git" / "config"
        config.write_text(config.read_text() + f"[include]\n\tpath = {included}\n")
        made = included if snapshot == "include_created" else target
        act = lambda: (made.write_text(f"[core]\n\tfsmonitor = touch {sentinel}\n"),  # noqa: E731
                       made == target and included.symlink_to(target))
    else:
        act = lambda: git(p["leaf"], "config", "core.fsmonitor", f"touch {sentinel}")  # noqa: E731
    found = _turn(p["repo"], rec, act)
    assert not sentinel.exists()
    if snapshot == "unavailable":   # one check_error per class naming the worktree, and the probes skipped
        errors = [f for f in found if f["kind"] == "check_error"]
        assert sorted(e["class"] for e in errors) == ["git_config", "git_hook"]
        assert {e["path"] for e in errors} == {str(p["leaf"])}
        assert [f["kind"] for f in found if f["kind"] != "check_error"] == ["git_probes_skipped"]
    else:
        [steer] = [f for f in found if f["kind"] == "steering_file"]
        assert steer["class"] == "git_config"
        assert steer["path"] == str(real_path(included)) if snapshot != "taken" else steer["path"].endswith("/.git/config")
        assert "core.fsmonitor=unset" in steer["before"] and f"core.fsmonitor=touch {sentinel}" in steer["after"]
        assert "git_probes_skipped" in {f["kind"] for f in found}
    subprocess.run(["git", "status"], cwd=p["leaf"], capture_output=True, check=False)
    assert sentinel.exists()   # the scenario is real: the probe the check skipped would have run it


@pytest.mark.parametrize("first", ["hook", "config_value_with_newline"])
def test_a_clean_turn_has_no_findings_and_leaves_the_flag_reconcile_lists_and_clears(tmp_path: Path, first: str) -> None:
    """Reconcile lists the first turn's change as one line, also when the changed value holds a newline."""
    p = _layout(tmp_path)
    repo, leaf = p["repo"], p["leaf"]
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", leaf, branch="feature/rm-thing")
    if first == "hook":
        hook, start = repo / ".git" / "hooks" / "pre-commit", "git_hook absent "
        _turn(repo, rec, lambda: _write(hook, "#!/bin/sh\n"))
    else:
        hook, start = repo / ".git" / "config", "git_config "
        _turn(repo, rec, lambda: hook.write_text(hook.read_text() + '[core]\n\tsshCommand = "ssh\\nevil"\n'))

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
    lines = "\n".join(wrc.reconcile_lines(o)).splitlines()   # physical lines, as printed
    steering = [ln.strip() for ln in lines if ln.strip().startswith(str(real_path(hook)))]
    assert len(steering) == 1 and steering[0].startswith(f"{real_path(hook)} {start}")
    assert [ln.strip() for ln in lines if "evil" in ln] == ([] if first == "hook" else steering)
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
    elif kind == "fifo":   # a special file: never opened for a blocking read
        os.mkfifo(path)
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
    *[(k, "hook") for k in ("unreadable", "fifo", "dangling_symlink", "symlink_loop")],
    *[(k, "git_config") for k in ("unreadable", "dangling_symlink", "symlink_loop")],   # a missing include is absent
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


def test_a_hooks_directory_over_the_cap_fails_closed_even_when_a_replaced_hook_keeps_it_over(tmp_path: Path) -> None:
    """201 entries at the start, one hook replaced and still 201: a check_error naming the directory, not a pass."""
    p = _layout(tmp_path)
    hooks = p["repo"] / ".git" / "hooks"
    for i in range(201 - len(list(hooks.iterdir()))):
        _write(hooks / f"extra-{i}", "#!/bin/sh\n")
    assert len(list(hooks.iterdir())) == 201
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    found = _turn(p["repo"], rec, lambda: _write(hooks / "extra-0", "#!/bin/sh\nevil\n"))
    [error] = [f for f in found if f["kind"] == "check_error"]
    assert error["path"] == str(real_path(hooks)) and error["class"] == "git_hook"
    assert {f["kind"] for f in found} == {"check_error", "git_probes_skipped"}
    assert tc.FLAG_POST_RUN in ws.load_record(p["repo"], rec.worker_id).flags


def test_an_unparsable_ready_through_the_worker_runner_still_ends_with_one_check_holding_the_config_change(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake executor writes a READY holding byte FF and changes the common config: the turn is not lost."""
    from specy_road import worker_adapters as wa
    from specy_road import worker_runner as wr
    p = _layout(tmp_path)
    repo = p["repo"]
    ready = ws.reviews_root(repo) / "M1.1" / "READY-opus.md"
    ready.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\ncat >/dev/null\n"
                    f"printf -- '---\\nnode_id: M1.1\\nnote: \\377\\n---\\n' > '{ready}'\n"
                    "git config specy.turn 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("do the leaf")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    assert wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(prompt, p["leaf"], "m", None)) == 0
    assert b"\xff" in ready.read_bytes()
    events = ws.events_since(repo, rec.worker_id)
    [check] = [e for e in events if e.type == "post_run_check"]
    [steer] = [f for f in check.detail["findings"] if f["kind"] == "steering_file"]
    assert steer["class"] == "git_config" and steer["path"] == str(real_path(repo / ".git" / "config"))
    [done] = [e for e in events if e.type == "completion"]
    assert done.detail == {"exit": 0, "ready": False} and "READY file invalid" in done.summary
    after = ws.load_record(repo, rec.worker_id)
    assert FLAG_STEERING in after.flags and after.state == "idle"


def _hooks_over_cap(p: dict[str, Path]) -> tuple[Callable[[], None], set[tuple[str, Path]]]:
    hooks = p["repo"] / ".git" / "hooks"
    for i in range(200 - len(list(hooks.iterdir()))):
        _write(hooks / f"extra-{i}", "#!/bin/sh\n")
    return lambda: _write(hooks / "one-more", "#!/bin/sh\n"), {("check_error", hooks)}


def _hooks_dir_becomes_fifo(p: dict[str, Path]) -> tuple[Callable[[], None], set[tuple[str, Path]]]:
    hooks = p["repo"] / ".git" / "hooks"
    _write(hooks / "pre-commit", "#!/bin/sh\n")

    def act() -> None:
        for child in hooks.iterdir():
            child.unlink()
        hooks.rmdir()
        os.mkfifo(hooks)
    return act, {("check_error", hooks)}


def _including_config_unreadable(p: dict[str, Path]) -> tuple[Callable[[], None], set[tuple[str, Path]]]:
    config, extra = p["repo"] / ".git" / "config", p["tmp"] / "extra.gitconfig"
    extra.write_text("[specy]\n\tincluded = 1\n")
    config.write_text(config.read_text() + f"[include]\n\tpath = {extra}\n")
    return lambda: config.chmod(0), {("check_error", config)}


def _include_reached_by_two_names(p: dict[str, Path]) -> tuple[Callable[[], None], set[tuple[str, Path]]]:
    config, extra, alias = p["repo"] / ".git" / "config", p["tmp"] / "extra.gitconfig", p["tmp"] / "alias.gitconfig"
    extra.write_text("[specy]\n\tincluded = 1\n")
    alias.symlink_to(extra)
    config.write_text(config.read_text() + f"[include]\n\tpath = {alias}\n\tpath = {extra}\n")
    return lambda: extra.write_text("[core]\n\tfsmonitor = true\n"), {("steering_file", extra)}


def _hooks_link_retargeted(p: dict[str, Path]) -> tuple[Callable[[], None], set[tuple[str, Path]]]:
    config, link, a, b = (p["repo"] / ".git" / "config", *(p["tmp"] / n for n in ("hooks-link", "hooks-a", "hooks-b")))
    for d in (a, b):
        _write(d / "pre-commit", "#!/bin/sh\n")
    link.symlink_to(a)
    config.write_text(config.read_text() + f"[core]\n\thooksPath = {link}\n")

    def act() -> None:
        link.unlink()
        link.symlink_to(b)
    return act, {("steering_file", link)}


def _include_deleted(p: dict[str, Path]) -> tuple[Callable[[], None], set[tuple[str, Path]]]:
    config, extra = p["repo"] / ".git" / "config", p["tmp"] / "extra.gitconfig"
    extra.write_text("[specy]\n\tincluded = 1\n")
    config.write_text(config.read_text() + f"[include]\n\tpath = {extra}\n")
    return extra.unlink, {("steering_file", extra)}


CONTAINER_ROWS = {"hooks_over_cap": _hooks_over_cap, "include_deleted": _include_deleted, "hooks_dir_becomes_fifo": _hooks_dir_becomes_fifo,
                  "including_config_unreadable": _including_config_unreadable,
                  "include_reached_by_two_names": _include_reached_by_two_names,
                  "hooks_link_retargeted": _hooks_link_retargeted}


@pytest.mark.parametrize("name", sorted(CONTAINER_ROWS))
def test_a_container_one_end_could_not_list_is_its_one_finding_and_one_file_is_one_finding(
        tmp_path: Path, name: str) -> None:
    """A hooks directory over the cap or unreadable, or a config file unreadable, after the turn: one check_error for
    it, not its former entries reported gone; one included file reached by two names: one finding; an include
    deleted under its unchanged config: one finding; the hooks-directory link retargeted: one finding for the link."""
    if name == "including_config_unreadable" and os.geteuid() == 0:
        pytest.skip("root reads a mode-000 file")
    p = _layout(tmp_path)
    act, expected = CONTAINER_ROWS[name](p)
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    found = _turn(p["repo"], rec, act)
    assert {(f["kind"], f["path"]) for f in found if "path" in f} == {(k, str(real_path(path))) for k, path in expected}
    assert "git_probes_skipped" in {f["kind"] for f in found}
