"""Schema 2 fields of :func:`specy_road.orchestration.snapshot`: ready, gate, holds, account."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from specy_road.orchestration import snapshot
from specy_road.review_files import reviews_dir
from specy_road.worker_sandbox import state_home
from specy_road.worker_state import create_record, events_since, mutate, set_state
from tests.helpers import REPO
from tests.review_repo_helpers import advance_dev, commit_file, git, make_review_repo, review_text

ONE = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
"""
TWO = """version: 1
roster:
  - {id: human, family: human, roles: [reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
policy: {reviewers_required: 2, reviewers_distinct_families: true}
"""
NOT_UTF8 = b"\xff\xfe"
NOT_MAPPING = b"---\n- not-a-mapping\n---\n"
READY_INVALID = b"---\nnode_id: M1.1\n---\n"
REVIEW_INVALID = b"---\nmodel: opus\n---\n"
_SHA = b"abc1234abc1234abc1234abc1234abc1234abc12"
READY_BLOCKED_TYPE = (
    b"---\nnode_id: M1.1\nagent: composer\nbranch: feature/rm-thing\ncommit: '" + _SHA
    + b"'\nbase: '" + _SHA + b"'\nchanged_paths: [src/a.py]\nblocked_on: waiting\n---\n"
)
REVIEW_ACCEPTANCE_LIST = b"""---
node_id: M1.1
model: human
date: '2026-10-26'
verdict: approve
commit: abc1234abc1234abc1234abc1234abc1234abc12
acceptance: []
findings:
  correctness: []
  regression: []
  boundary: []
  test_integrity: []
commands_rerun: []
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
---
notes
"""
NODE = "M1.1"
TS = REPO / "gui" / "pm-gantt" / "src" / "orchestrationSnapshot.ts"
FIXTURE = REPO / "tests" / "fixtures" / "orchestration_snapshot_v2.json"


def _ready(repo: Path, commit: str, extra: str = "") -> None:
    d = reviews_dir(repo, NODE)
    d.mkdir(parents=True, exist_ok=True)
    base = git(repo, "rev-parse", "dev")
    (d / "READY-composer.md").write_text(
        f"---\nnode_id: {NODE}\nagent: composer\nbranch: feature/rm-thing\n"
        f"commit: '{commit}'\nbase: '{base}'\nchanged_paths: [src/a.py]\n{extra}---\n",
        encoding="utf-8",
    )


def _review(repo: Path, commit: str, **kw) -> None:
    d = reviews_dir(repo, NODE)
    d.mkdir(parents=True, exist_ok=True)
    kw.setdefault("model", "opus")
    (d / f"REVIEW-{kw['model']}.md").write_text(review_text(commit, **kw), encoding="utf-8")


def _tip(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def _at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()


def _ready_value(repo: Path, commit: str, blocked: list | None) -> dict:
    row = {"commit": commit, "model": "composer", "at": _at(reviews_dir(repo, NODE) / "READY-composer.md")}
    if blocked is not None:
        row["blocked_on"] = blocked
    return row


def _gate(state: str, approvals: int = 0, blocks: int = 0, fresh: bool = True) -> dict:
    return {"state": state, "approvals": approvals, "blocks": blocks, "fresh_for_head": fresh}


def _handoff_state(repo: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "handoff", "status", NODE, "--json", "--repo-root", str(repo)],
        capture_output=True, text=True, check=False,
    )
    return json.loads(proc.stdout)["nodes"][0]["state"]


def _leaf(repo: Path) -> dict:
    return snapshot(repo)["leaves"][NODE]


def test_passed_gate_matches_handoff_status(tmp_path: Path) -> None:
    """A counted approval at the current READY is ``approved``, with the READY's fields."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    commit = _tip(repo)
    _ready(repo, commit)
    _review(repo, commit)
    leaf = _leaf(repo)
    assert leaf["gate"] == _gate("approved", approvals=1)
    assert leaf["ready"] == _ready_value(repo, commit, [])
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_counted_block_matches_handoff_status(tmp_path: Path) -> None:
    """One counted block is ``blocked`` with ``blocks`` 1."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    commit = _tip(repo)
    _ready(repo, commit)
    _review(repo, commit, verdict="block", a1="fail")
    leaf = _leaf(repo)
    assert leaf["gate"] == _gate("blocked", blocks=1)
    assert leaf["ready"] == _ready_value(repo, commit, [])
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_stale_only_review_omits_blocked_on(tmp_path: Path) -> None:
    """A READY and review left behind the tip are ``stale``; ``blocked_on`` is absent."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    old = _tip(repo)
    _ready(repo, old, "blocked_on:\n  - {acceptance: A1, reason: later}\n")
    _review(repo, old, verdict="block", a1="fail")
    commit_file(repo, "src/b.py", "x\n", "move on")
    leaf = _leaf(repo)
    assert leaf["gate"] == _gate("stale")
    assert leaf["ready"] == _ready_value(repo, old, None)
    assert "blocked_on" not in leaf["ready"]
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_insufficient_approvals(tmp_path: Path) -> None:
    """One approval where the policy wants two distinct families stays ``in-review``."""
    repo = make_review_repo(tmp_path, orchestration=TWO)
    commit = _tip(repo)
    _ready(repo, commit)
    _review(repo, commit)
    leaf = _leaf(repo)
    assert leaf["gate"] == _gate("in-review", approvals=1)
    assert leaf["ready"] == _ready_value(repo, commit, [])
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_executor_blocker_keeps_blocked_on(tmp_path: Path) -> None:
    """A current READY's ``blocked_on`` is the gate's ``executor_blocked`` label."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    commit = _tip(repo)
    _ready(repo, commit, "blocked_on:\n  - {acceptance: A1, reason: needs a path outside the zones}\n")
    leaf = _leaf(repo)
    blocked = [{"acceptance": "A1", "reason": "needs a path outside the zones"}]
    assert leaf["gate"] == _gate("executor_blocked")
    assert leaf["ready"] == _ready_value(repo, commit, blocked)
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_policy_error_keeps_the_ready(tmp_path: Path) -> None:
    """A schema-invalid orchestration file does not hide a readable READY."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    commit = _tip(repo)
    _ready(repo, commit)
    (repo / "roadmap" / "orchestration.yaml").write_text("roster: [\n", encoding="utf-8")
    leaf = _leaf(repo)
    assert leaf["gate"] == _gate("in-review")
    assert leaf["ready"] == _ready_value(repo, commit, [])
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_absent_ready_is_null(tmp_path: Path) -> None:
    """No READY file is ``ready: null`` and ``waiting``."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    leaf = _leaf(repo)
    assert leaf["ready"] is None and leaf["gate"] == _gate("waiting")
    assert leaf["gate"]["state"] == _handoff_state(repo)


def test_unreadable_ready_is_unknown_and_keeps_a_sibling_review(tmp_path: Path) -> None:
    """A non-UTF-8 READY is ``unknown``; a readable review beside it still counts, and the gate stays waiting."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    commit = _tip(repo)
    _review(repo, commit)
    (reviews_dir(repo, NODE) / "READY-composer.md").write_bytes(NOT_UTF8)
    leaf = _leaf(repo)
    assert leaf["ready"] == "unknown" and leaf["gate"] == _gate("waiting", approvals=1)
    assert leaf["reviews"] == [{
        "model": "opus", "verdict": "approve", "commit": commit, "fresh_for_head": True,
    }]
    assert leaf["gate"]["state"] == _handoff_state(repo)


@pytest.mark.parametrize(
    "payload", [NOT_UTF8, NOT_MAPPING, REVIEW_INVALID, REVIEW_ACCEPTANCE_LIST],
    ids=["utf8", "mapping", "schema", "acceptance-type"],
)
def test_a_malformed_review_is_unknown_and_keeps_its_sibling(payload: bytes, tmp_path: Path) -> None:
    """Each malformed class blanks only that review."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    commit = _tip(repo)
    _review(repo, commit)
    (reviews_dir(repo, NODE) / "REVIEW-bad.md").write_bytes(payload)
    rows = _leaf(repo)["reviews"]
    assert {"model": "unknown", "verdict": "unknown", "commit": "unknown", "fresh_for_head": "unknown"} in rows
    assert any(row["model"] == "opus" and row["commit"] == commit for row in rows)


@pytest.mark.parametrize(
    "payload", [NOT_UTF8, NOT_MAPPING, READY_INVALID, READY_BLOCKED_TYPE],
    ids=["utf8", "mapping", "schema", "blocked-on-type"],
)
def test_each_malformed_ready_class_is_unknown(payload: bytes, tmp_path: Path) -> None:
    """A non-UTF-8, non-mapping or schema-invalid READY sets ``ready`` to unknown."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    (reviews_dir(repo, NODE)).mkdir(parents=True)
    (reviews_dir(repo, NODE) / "READY-composer.md").write_bytes(payload)
    assert _leaf(repo)["ready"] == "unknown"


def test_worker_flags_activity_and_account_name_a_label_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``paused_by_limit`` is a flag; activity is the newer stamp; the account is not a path or env value."""
    secret, config = "seeded-secret-value", "/accounts/seeded-secret-value/work/claude"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", config)
    repo = make_review_repo(tmp_path, orchestration=ONE)
    rec = create_record(repo, NODE, "generic", "opus", repo, branch="feature/rm-thing")
    set_state(repo, rec, "paused_by_limit")
    later = "2099-01-01T00:00:00+00:00"
    mutate(repo, rec, lambda r: setattr(r, "last_output_at", later))
    home = state_home(repo, rec.worker_id)
    home.mkdir(parents=True)
    (home / "claude-config-dir").write_text(config + "\n", encoding="utf-8")
    worker = _leaf(repo)["workers"][0]
    assert worker["account"] == "work"
    assert worker["flags"] == ["paused_by_limit"]
    assert worker["last_activity"] == later
    assert events_since(repo, rec.worker_id)
    blob = json.dumps(snapshot(repo))
    assert secret not in blob and config not in blob


def test_roster_cli_names_the_profile_when_the_record_does_not(tmp_path: Path) -> None:
    """A quoted ``CLAUDE_CONFIG_DIR`` with spaces names ``work``, and the path stays out of the snapshot."""
    config = "/Accounts/My Accounts/work/claude"
    roster = ONE.replace(
        "roles: [reviewer]}",
        "roles: [reviewer], channels: {cli: 'CLAUDE_CONFIG_DIR=\"" + config + "\" claude'}}",
        1,
    )
    repo = make_review_repo(tmp_path, orchestration=roster)
    create_record(repo, NODE, "generic", "opus", repo, branch="feature/rm-thing")
    blob = json.dumps(snapshot(repo))
    assert _leaf(repo)["workers"][0]["account"] == "work"
    assert config not in blob and "My Accounts" not in blob


def test_missing_integration_ref_is_unknown_ahead_and_behind(tmp_path: Path) -> None:
    """With ``dev`` present the counts are integers; deleting the ref makes both unknown."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    before = _leaf(repo)["worktrees"][0]
    assert isinstance(before["ahead"], int) and isinstance(before["behind"], int)
    git(repo, "update-ref", "-d", "refs/heads/dev")
    after = _leaf(repo)["worktrees"][0]
    assert after["ahead"] == "unknown" and after["behind"] == "unknown"


def test_fsmonitor_in_a_worktree_does_not_run_and_the_main_checkout_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every list-form git call snapshot makes carries the read-only settings, and the main status is unchanged."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    leaf = tmp_path / "leaf"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-side", str(leaf), "HEAD")
    sentinel = tmp_path / "sentinel"
    script = tmp_path / "fsmon"
    script.write_text(f"#!/bin/sh\necho ran > {sentinel}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    create_record(repo, NODE, "generic", "opus", leaf, branch="feature/rm-side")
    porcelain = git(repo, "status", "--porcelain", "--untracked-files=all")
    git(repo, "config", "core.fsmonitor", str(script))
    git(repo, "config", "extensions.worktreeConfig", "true")
    git(leaf, "config", "--worktree", "core.fsmonitor", str(script))
    log = tmp_path / "git-invocations"
    real = shutil.which("git")
    wrapper = tmp_path / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"LOCKS=${{GIT_OPTIONAL_LOCKS-}}\" >> {shlex.quote(str(log))}\n"
        f"printf '%s\\n' \"$@\" >> {shlex.quote(str(log))}\n"
        f"printf '\\n' >> {shlex.quote(str(log))}\n"
        f"exec {shlex.quote(str(real))} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    original_path = os.environ["PATH"]
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{original_path}")
    snapshot(repo)
    assert not sentinel.exists()
    blocks = [b for b in log.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    assert blocks
    for block in blocks:
        lines = block.splitlines()
        assert lines[0] == "LOCKS=0"
        assert "core.fsmonitor=false" in lines and "core.hooksPath=/dev/null" in lines
    assert any(isinstance(row["ahead"], int) for row in _leaf(repo)["worktrees"])
    git(repo, "config", "--unset", "core.fsmonitor")
    monkeypatch.setenv("PATH", original_path)
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == porcelain


def test_snapshot_writes_no_objects_when_the_leaf_is_behind(tmp_path: Path) -> None:
    """A leaf behind the integration branch does not gain objects or ``work/`` files."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    advance_dev(repo, "docs/later.md", "later\n")
    before = git(repo, "count-objects", "-v")
    files = _tree(repo / "work")
    snapshot(repo)
    assert git(repo, "count-objects", "-v") == before
    assert _tree(repo / "work") == files


def test_holds_are_the_hold_list_plus_open_gates(tmp_path: Path) -> None:
    """A hold-file line and an open gate the leaf depends on are both holds."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    _write_gate(repo)
    hold = repo / "work" / "grind-hold.txt"
    hold.parent.mkdir(parents=True, exist_ok=True)
    hold.write_text(f"# note\n{NODE} # waiting on the maintainer\nOTHER\n", encoding="utf-8")
    assert _leaf(repo)["holds"] == [
        {"source": "hold_list", "id": NODE, "reason": "waiting on the maintainer"},
        {"source": "gate", "id": "M0", "reason": "Sign-off"},
    ]


def test_an_unreadable_hold_file_is_unknown(tmp_path: Path) -> None:
    """A hold path that is not a regular file sets ``holds`` to unknown."""
    repo = make_review_repo(tmp_path, orchestration=ONE)
    path = repo / "work" / "grind-hold.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    assert _leaf(repo)["holds"] == "unknown"


def test_v2_fixture_key_paths_match_the_typescript_lists() -> None:
    """The committed snapshot's key paths are ``requiredKeys`` plus ``optionalKeys``."""
    src = TS.read_text(encoding="utf-8")
    listed = _export_keys(src, "requiredKeys") + _export_keys(src, "optionalKeys")
    assert _key_paths(json.loads(FIXTURE.read_text(encoding="utf-8"))) == set(listed)


def _tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _write_gate(repo: Path) -> None:
    gate_key = "00000000-0000-5000-8000-000000000000"
    leaf = json.loads((repo / "roadmap" / "phases" / "M1.json").read_text(encoding="utf-8"))["nodes"][0]
    leaf["dependencies"] = [gate_key]
    gate = {
        "id": "M0", "node_key": gate_key, "title": "Sign-off", "type": "gate",
        "status": "Not Started", "dependencies": [],
    }
    (repo / "roadmap" / "phases" / "M1.json").write_text(
        json.dumps({"nodes": [gate, leaf]}), encoding="utf-8",
    )


def _quoted(block: str) -> list[str]:
    return re.findall(r'"([^"]*)"', block)


def _const_list(src: str, name: str) -> list[str]:
    match = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
    assert match is not None
    return _quoted(match.group(1))


def _export_keys(src: str, name: str) -> list[str]:
    match = re.search(rf"export const {name}:.*?= \[(.*?)\];", src, re.S)
    assert match is not None
    known = {"WORKER_REQUIRED": _const_list(src, "WORKER_REQUIRED"), "WORKER_OPTIONAL": _const_list(src, "WORKER_OPTIONAL")}
    out: list[str] = []
    for raw in match.group(1).splitlines():
        line = raw.strip().rstrip(",")
        spread = re.match(r"\.\.\.under\(\"([^\"]+)\",\s*(\[[^\]]*\]|[A-Z_]+)\)", line)
        if spread:
            prefix, keys = spread.group(1), spread.group(2)
            names = _quoted(keys) if keys.startswith("[") else known[keys]
            out.extend(f"{prefix}.{item}" for item in names)
        elif _quoted(line):
            out.append(_quoted(line)[0])
    return out


def _key_paths(value: object, path: str = "", found: set[str] | None = None) -> set[str]:
    found = found if found is not None else set()
    if isinstance(value, list):
        for item in value:
            _key_paths(item, f"{path}[]", found)
    elif isinstance(value, dict):
        for key, item in value.items():
            seg = "*" if path == "leaves" else key
            child = f"{path}.{seg}" if path else seg
            found.add(child)
            _key_paths(item, child, found)
    return found
