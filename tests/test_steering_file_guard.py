"""M21.7: executors cannot change the files that steer harnesses and specy-road unnoticed.

One fake executor turn per steering class (a linked worktree, the main checkout beside it, ``.venv`` linked by
``env_setup.link``, a second worktree holding the integration branch), the clean turn, the sticky flag and its
listing by ``worker reconcile``, and finish's refusal paired with the Claude Code launch denies.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import commit_file, delegate_layout, git, make_review_repo

from specy_road import worker_adapters as wa
from specy_road import worker_reconcile as wrc
from specy_road import worker_state as ws
from specy_road import worker_turn_check as tc
from specy_road.bundled_scripts import finish_task
from specy_road.git_config_text import parse_config
from specy_road.steering_paths import FLAG_STEERING


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


def _registry_add_other(leaf: Path) -> None:
    path = leaf / "roadmap" / "registry.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["entries"].append({"codename": "other", "node_id": "M1.2", "branch": "feature/rm-other", "touch_zones": ["lib"]})
    path.write_text(yaml.safe_dump(doc))


def _link(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def _commit_policy_from_second(second: Path) -> None:
    _write(second / "roadmap" / "orchestration.yaml", "version: 1\n# the executor approves itself\n")
    git(second, "add", "roadmap/orchestration.yaml")
    git(second, "commit", "-qm", "roster")


CASES = {   # name: (the turn, the finding's class, the end of its path)
    "claude_settings": (lambda p: _write(p["leaf"] / ".claude" / "settings.json", "{}\n"), "harness", ".claude/settings.json"),
    "cursor_hooks": (lambda p: _write(p["leaf"] / ".cursor" / "hooks.json", "{}\n"), "harness", ".cursor/hooks.json"),
    "common_git_hook": (lambda p: _write(p["repo"] / ".git" / "hooks" / "pre-commit", "#!/bin/sh\n"), "git_hook",
                        "/.git/hooks/pre-commit"),
    "envrc": (lambda p: _write(p["leaf"] / ".envrc", "export X=1\n"), "shell_startup", ".envrc"),
    "venv_write_through_link": (lambda p: (p["leaf"] / ".venv" / "bin" / "python").write_text("evil\n"), "env_bin",
                                ".venv/bin/python"),
    "symlink_leaving_worktree": (lambda p: (p["leaf"] / "leak").symlink_to(p["tmp"] / "base-python3"), "symlink", "leak"),
    "other_leaf_registry_entry": (lambda p: _registry_add_other(p["leaf"]), "registry", "roadmap/registry.yaml#M1.2"),
    "forged_review_in_worktree": (lambda p: _write(p["leaf"] / "work" / "reviews" / "M1.1" / "REVIEW-sol.md", "x\n"),
                                  "review_file", "work/reviews/M1.1/REVIEW-sol.md"),
    "escaping_symlink_at_harness_path": (lambda p: _link(p["leaf"] / ".claude" / "settings.json", p["tmp"] / "base-python3"),
                                         "harness", ".claude/settings.json"),
    "forged_review": (lambda p: _write(ws.reviews_root(p["repo"]) / "M1.1" / "REVIEW-sol.md", "verdict: approve\n"),
                      "review_file", "work/reviews/M1.1/REVIEW-sol.md"),
    "policy_blob_from_second_worktree": (lambda p: _commit_policy_from_second(p["second"]), "policy_blob",
                                         "dev:roadmap/orchestration.yaml"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_each_steering_class_is_exactly_one_steering_file_finding(tmp_path: Path, name: str) -> None:
    act, cls, tail = CASES[name]
    p = _layout(tmp_path)
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    found = _turn(p["repo"], rec, lambda: act(p))
    [steer] = [f for f in found if f["kind"] == "steering_file"]
    assert steer["class"] == cls and steer["path"].endswith(tail) and steer["before"] != steer["after"]
    named = [x for f in found if f["kind"] in ("porcelain", "committed_outside_zones") for x in f["paths"]]
    assert not [x for x in named if x.endswith(tail.rsplit("/", 1)[-1])], found   # replaced, not reported twice
    assert ("git_probes_skipped" in {f["kind"] for f in found}) == (cls == "git_hook")
    assert FLAG_STEERING in ws.load_record(p["repo"], rec.worker_id).to_dict()["flags"]   # worker status --json


HOOKS_PATH_SPELLINGS = {   # name: (the hooks directory's name, core.hooksPath as written, {d} its absolute path)
    "trailing_comment": ("hooks", "{d} # managed by ops"),
    "quoted_hash_then_comment": ("hooks #x;y", '"{d}" ; note'),
    "escaped_quote_and_continuation": ('ho"oks', '"{d_escaped}"'),
}


@pytest.mark.parametrize("name", sorted(HOOKS_PATH_SPELLINGS))
def test_a_hook_in_the_configured_hooks_path_is_found_however_git_config_spells_it(tmp_path: Path, name: str) -> None:
    dirname, spelling = HOOKS_PATH_SPELLINGS[name]
    p = _layout(tmp_path)
    d = tmp_path / dirname
    d.mkdir()
    escaped = str(d).replace('"', '\\"')
    value = spelling.format(d=d, d_escaped=escaped[:len(escaped) // 2] + "\\\n" + escaped[len(escaped) // 2:])
    config = p["repo"] / ".git" / "config"
    config.write_text(config.read_text() + f"[core]\n\thooksPath = {value}\n")
    assert git(p["repo"], "config", "--file", str(config), "--get", "core.hooksPath") == str(d)   # git's reading
    assert dict(parse_config(config.read_text()))["core.hookspath"] == str(d)                   # is the check's
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    found = _turn(p["repo"], rec, lambda: _write(d / "pre-commit", "#!/bin/sh\n"))
    [steer] = [f for f in found if f["kind"] == "steering_file"]
    assert steer["class"] == "git_hook" and steer["path"] == str(d / "pre-commit") and steer["before"] == "absent"


def test_a_changed_fsmonitor_is_reported_before_any_git_command_could_run_it(tmp_path: Path) -> None:
    p = _layout(tmp_path)
    sentinel = tmp_path / "fsmonitor-ran"
    rec = ws.create_record(p["repo"], "M1.1", "claude-code", "opus", p["leaf"], branch="feature/rm-thing")
    found = _turn(p["repo"], rec, lambda: git(p["leaf"], "config", "core.fsmonitor", f"touch {sentinel}"))
    [steer] = [f for f in found if f["kind"] == "steering_file"]
    assert steer["class"] == "git_config" and steer["path"].endswith("/.git/config")
    assert "core.fsmonitor=unset" in steer["before"] and f"core.fsmonitor=touch {sentinel}" in steer["after"]
    assert "git_probes_skipped" in {f["kind"] for f in found} and not sentinel.exists()
    subprocess.run(["git", "status"], cwd=p["leaf"], capture_output=True, check=False)
    assert sentinel.exists()   # the scenario is real: the probe the check skipped would have run it


def test_a_clean_turn_has_no_findings_and_leaves_the_flag_reconcile_lists_and_clears(tmp_path: Path) -> None:
    p = _layout(tmp_path)
    repo, leaf = p["repo"], p["leaf"]
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", leaf, branch="feature/rm-thing")
    _turn(repo, rec, lambda: _write(leaf / ".claude" / "settings.json", "{}\n"))

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
    steering = [ln.strip() for ln in wrc.reconcile_lines(o) if ln.strip().startswith(".claude/")]
    assert len(steering) == 1 and steering[0].startswith(".claude/settings.json harness absent ")
    assert FLAG_STEERING not in ws.load_record(repo, rec.worker_id).flags
    assert wrc.reconcile(repo, rec.worker_id)[1]["steering"] == []


# --- finish and the launch argv ------------------------------------------------------------------------------


def _finish(root: Path) -> int:
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(root)])
        raise SystemExit(0)
    return e.value.code or 0


def _set_zones(root: Path, zones: list[str]) -> None:
    reg = root / "roadmap" / "registry.yaml"
    doc = yaml.safe_load(reg.read_text())
    doc["entries"][0]["touch_zones"] = zones
    commit_file(root, "roadmap/registry.yaml", yaml.safe_dump(doc), "zones")


def _denies(leaf: Path, repo: Path) -> list[str]:
    argv = wa.adapter_for("claude-code").launch(leaf / "prompt.md", leaf, "m", None, node_id="M1.1", repo_root=repo).argv
    resumed = wa.adapter_for("claude-code").resume("sid", leaf / "prompt.md", leaf, "m", None, node_id="M1.1",
                                                   repo_root=repo).argv
    rules = argv[argv.index("--disallowedTools") + 1:argv.index("--allowedTools")]
    assert rules == resumed[resumed.index("--disallowedTools") + 1:resumed.index("--allowedTools")]
    assert all(r.startswith(("Edit(./", "Write(./")) and "*" not in r for r in rules)   # per file, no parent glob
    return rules


@pytest.mark.parametrize("zoned", [False, True])
def test_finish_refuses_an_unzoned_steering_file_and_the_argv_denies_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], zoned: bool) -> None:
    repo, leaf, _bare = delegate_layout(tmp_path, monkeypatch)
    (leaf / "prompt.md").write_text("do the leaf")
    if zoned:   # as edit-node would: the claim row on the integration branch, merged into the leaf
        _set_zones(repo, ["src", ".claude/settings.json"])
        git(leaf, "merge", "-q", "--no-edit", "dev")
        git(repo, "push", "-q", "origin", "dev")
    commit_file(leaf, ".claude/settings.json", '{"hooks": {}}\n', "harness settings")
    rules = _denies(leaf, repo)
    assert ("Edit(./.claude/settings.json)" in rules) is not zoned and ("Write(./.claude/settings.json)" in rules) is not zoned
    assert "Edit(./roadmap/orchestration.yaml)" in rules and "Write(./.claude/settings.local.json)" in rules
    before = git(leaf, "rev-parse", "HEAD")
    code = _finish(leaf)
    err = capsys.readouterr().err
    if zoned:
        assert code == 0 and "steering" not in err
    else:
        assert code == 1 and ".claude/settings.json (harness)" in err and "edit-node M1.1" in err
        assert git(leaf, "rev-parse", "HEAD") == before   # refused before the bookkeeping commit


def test_a_custom_cli_argv_is_left_as_written(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    launch = wa.adapter_for("claude-code").launch(repo / "p.md", repo, "m", "claude -p {prompt}",
                                                  node_id="M1.1", repo_root=repo)
    assert "--disallowedTools" not in launch.argv
