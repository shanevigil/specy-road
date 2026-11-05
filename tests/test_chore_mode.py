"""``specy-road chore start|close``: worker commands that take a chore slug in place of a node id (M11.28)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo
from tests.test_worker_cli import FAKE, run_worker_cli, wait_for_worker, worker_roster

from specy_road import review_delegate as rd
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import chore_cli
from specy_road.worker_orphans import orphans


def chore_repo(tmp_path: Path) -> Path:
    """A review repo whose roster runs ``opus`` on the fake harness, with ``work/`` ignored."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    return repo


def run_chore_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        chore_cli.main(list(args))
    return e.value.code or 0


def _start(repo: Path, slug: str = "fix-env", *extra: str) -> dict:
    assert run_chore_cli("chore", "start", slug, "--task", "Repair the env", "--zone", "src", "--json",
                         "--repo-root", str(repo), *extra) == 0
    return json.loads((repo / "work" / "chores" / f"{slug}.json").read_text())


def test_start_records_an_unregistered_chore(tmp_path: Path, capsys) -> None:
    repo = chore_repo(tmp_path)
    registry = (repo / "roadmap" / "registry.yaml").read_text()
    branches = git(repo, "branch", "--list")
    chore = _start(repo)
    assert chore["branch"] == "feature/rm-thing" and chore["worktree"] == str(repo.resolve())
    assert chore["base"] == git(repo, "rev-parse", "HEAD") and chore["touch_zones"] == ["src"] and not chore["review"]
    assert (repo / "roadmap" / "registry.yaml").read_text() == registry and git(repo, "branch", "--list") == branches
    assert git(repo, "status", "--porcelain") == ""                       # under work/, gitignored
    capsys.readouterr()
    assert run_chore_cli("chore", "start", "fix-env", "--task", "t", "--zone", "src", "--repo-root", str(repo)) == 1
    for bad in ("M1.1", "w-0001", "Fix"):                                 # a node id, a worker id, upper case
        assert run_chore_cli("chore", "start", bad, "--task", "t", "--zone", "src", "--repo-root", str(repo)) == 1
    assert "already exists" in capsys.readouterr().err


def test_delegate_sync_usage_message_and_close(tmp_path: Path, capsys) -> None:
    repo = chore_repo(tmp_path)
    _start(repo, "fix-env", "--model", "opus")
    capsys.readouterr()
    assert run_worker_cli("worker", "delegate", "fix-env", "--json", "--repo-root", str(repo)) == 0   # the chore's model
    out = json.loads(capsys.readouterr().out)
    assert out["created"] and out["model"] == "opus" and out["worktree"] == str(repo.resolve())
    prompt = (repo / "work" / "prompt-fix-env-executor-opus.md").read_text()
    assert "Repair the env" in prompt and "`src`" in prompt
    assert not (repo / "work" / "brief-fix-env.md").exists()
    rec = wait_for_worker(repo, out["worker_id"])
    assert rec.node_id == "fix-env" and rec.state == "idle" and rec.branch == "feature/rm-thing"

    assert run_worker_cli("worker", "sync", "--json", "--repo-root", str(repo)) == 0
    synced = json.loads(capsys.readouterr().out)
    assert [w["node_id"] for w in synced["workers"]] == ["fix-env"]
    assert orphans(repo) == {}                                            # no claim, yet not orphaned
    assert run_worker_cli("worker", "usage", "fix-env", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["node_id"] == "fix-env"
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "also x", "--repo-root", str(repo)) == 0
    assert wait_for_worker(repo, rec.worker_id).state == "idle"

    capsys.readouterr()
    assert run_chore_cli("chore", "close", "fix-env", "--summary", "Env repaired", "--repo-root", str(repo)) == 0
    text = (repo / "work" / "chores" / "fix-env.md").read_text()
    assert "Env repaired" in text and "fix-env usage (1 attempt(s)" in text and "unreviewed (no review was run)" in text
    assert ws.load_record(repo, rec.worker_id).state == "terminated"     # its idle worker ended with the chore
    assert run_worker_cli("worker", "delegate", "fix-env", "--model", "opus", "--repo-root", str(repo)) == 1
    assert run_chore_cli("chore", "close", "fix-env", "--summary", "again", "--repo-root", str(repo)) == 1
    assert "was closed" in capsys.readouterr().err


def test_close_refuses_while_a_worker_runs(tmp_path: Path, monkeypatch) -> None:
    repo = chore_repo(tmp_path)
    _start(repo)
    monkeypatch.setattr(ops, "spawn", lambda *a, **k: None)
    rec, _ = ops.delegate(repo, "fix-env", "opus")
    assert rec.state == "starting"                                       # not held: the turn has not ended
    with pytest.raises(ws.WorkerError, match="running worker"):
        chore_cli.close(repo, "fix-env", "s")


def test_roster_free_model_needs_a_harness(tmp_path: Path, monkeypatch) -> None:
    repo = chore_repo(tmp_path)
    _start(repo, "a")
    with pytest.raises(ws.WorkerError, match="pass --harness"):
        ops.delegate(repo, "a", "gpt-x")
    with pytest.raises(ws.WorkerError, match="not in the roster"):   # a leaf still needs a rostered model
        ops.delegate(repo, "M1.1", "gpt-x", harness="codex")
    launched = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **k: launched.append(launch))
    _start(repo, "b", "--model", "gpt-x", "--harness", "codex")
    rec, created = ops.delegate(repo, "b", None)
    assert created and rec.harness == "codex" and rec.model == "gpt-x"
    assert "gpt-x" in launched[0].argv


def test_reconcile_enforces_the_chore_zones(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = chore_repo(tmp_path)
    for zones in ([" "], ["/"], ["src", "//"]):   # reconcile's normalisation empties these: the guard would be off
        args = [a for z in zones for a in ("--zone", z)]
        assert run_chore_cli("chore", "start", "x", "--task", "t", *args, "--repo-root", str(repo)) == 1
        assert "every --zone must name a path" in capsys.readouterr().err
    assert chore_cli.load_chore(repo, "x") is None
    _start(repo)
    monkeypatch.setattr(ops, "spawn", lambda *a, **k: None)
    rec, _ = ops.delegate(repo, "fix-env", "opus")
    commit_file(repo, "src/b.py", "b = 1\n", "in zone")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["changed"] == ["src/b.py"] and not delta["outside_touch_zones"] and not delta["needs_reconcile"]
    assert not delta["contract_changed"]
    commit_file(repo, "docs/y.md", "# y\n", "out of zone")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == ["docs/y.md"] and delta["needs_reconcile"]


def _filed_review(prompt: str) -> tuple[Path, str]:
    """The path and template the chore reviewer prompt names, filled in."""
    path = Path(prompt.split("Write your verdict to\n\n`")[1].split("`")[0])
    template = prompt.split("```\n")[1].split("```")[0].replace("YYYY-MM-DD", "2026-11-03")
    return path, template


def test_review_delegate_takes_a_chore_started_with_review(tmp_path: Path) -> None:
    repo = chore_repo(tmp_path)
    _start(repo, "plain")
    with pytest.raises(rd.DelegateError, match="without --review"):
        rd.delegate(repo, "plain", "opus")
    chore = _start(repo, "fix-env", "--review")
    # The record the reviewer prompt describes, filed as the reviewer would; the fake harness then runs the turn.
    head = git(repo, "rev-parse", "HEAD")
    path, template = _filed_review(chore_cli.chore_prompt(chore, "reviewer", "opus", repo, commit=head))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template)
    run = rd.delegate(repo, "fix-env", "opus")
    assert "Write your verdict to" in (repo / "work" / "prompt-fix-env-reviewer-opus.md").read_text()
    assert run["state"] == "complete" and run["commit"] == git(repo, "rev-parse", "HEAD")
    chore_cli.close(repo, "fix-env", "done")
    assert "- opus: approve at " in (repo / "work" / "chores" / "fix-env.md").read_text()
    assert chore_cli.load_chore(repo, "fix-env")["closed_at"]


# --- chore garden (M12.3) ---------------------------------------------------------------------------

from datetime import date, timedelta  # noqa: E402

from specy_road.agent_ignores import apply_agent_ignores  # noqa: E402
from specy_road.bundled_scripts import chore_garden  # noqa: E402
from specy_road.bundled_scripts.role_prompt_rca import dirty_check  # noqa: E402
from specy_road.bundled_scripts.roadmap_load import load_roadmap  # noqa: E402

_RULES = ("# Rules\n\nRead the docs.\n<!-- prevents: drift | enforced: advisory | ref: x -->\n"
          "Run validate.\n<!-- prevents: bad graphs | enforced: specy-road validate | ref: y -->\n")
_GARDEN_LINES = [
    "stale-command: docs/guide.md:3: `specy-road grind` is not a command in specy-road "
    f"{chore_garden.__version__}; use `specy-road grind-session`",
    "stale-command: AGENTS.md:3: `specy-road nope` is not a command in specy-road "
    f"{chore_garden.__version__}; see `specy-road --help`",
    "advisory-rule: .specyrd/AGENTS.md:4: prevents: drift",
    "ratchet-grew: constraints/base.txt: +2 line(s) since v1",
]


def garden_repo(tmp_path: Path, *, tag: bool = True, cadence: int | None = None) -> Path:
    """A repo on ``dev`` with one finding of each class in its last commit; ``.gitignore`` is the managed lines only."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    (repo / ".gitignore").unlink()
    apply_agent_ignores(repo)                                             # as init project writes it
    git(repo, "add", ".gitignore", ".cursorindexingignore")
    git(repo, "commit", "-qm", "managed ignores")
    policy = "version: 1\npolicy:\n  ratchet_paths:\n    - constraints/base.txt\n" + (
        f"  garden_cadence_days: {cadence}\n" if cadence else "")
    for rel, text in (("roadmap/orchestration.yaml", policy), ("constraints/base.txt", "a\n")):
        commit_file(repo, rel, text, f"add {rel}")
    if tag:
        git(repo, "tag", "v1")
    for rel, text in (("constraints/base.txt", "a\nb\nc\n"),
                      ("docs/guide.md", "# Guide\n\nRun `specy-road grind` then run `specy-road validate`.\n"),
                      ("AGENTS.md", "# Agents\n\n- specy-road nope --flag\n"), (".specyrd/AGENTS.md", _RULES)):
        commit_file(repo, rel, text, f"drift in {rel}")
    return repo


def _roadmap_bytes(repo: Path) -> dict[str, bytes]:
    return {p.relative_to(repo).as_posix(): p.read_bytes()
            for base in ("roadmap", "planning") if (repo / base).is_dir()
            for p in sorted((repo / base).rglob("*")) if p.is_file()}


def test_garden_prints_one_line_per_finding_and_writes_nothing_tracked(tmp_path: Path, capsys) -> None:
    repo = garden_repo(tmp_path)
    capsys.readouterr()
    assert run_chore_cli("chore", "garden", "--repo-root", str(repo)) == 0
    assert capsys.readouterr().out.splitlines() == _GARDEN_LINES
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""   # the managed lines ignore the record
    assert git(repo, "check-ignore", "work/chores/.garden.json") == "work/chores/.garden.json"
    clean = subprocess.run(dirty_check("", "M1.1"), shell=True, cwd=repo, capture_output=True, text=True, check=True)
    assert clean.stdout == ""                                             # delegate's clean-tree check passes
    assert json.loads(chore_garden.record_path(repo).read_text()) == {"last_run": date.today().isoformat()}
    assert run_chore_cli("chore", "garden", "--json", "--repo-root", str(repo)) == 0
    report = json.loads(capsys.readouterr().out)
    assert [f["cls"] for f in report["findings"]] == ["stale-command", "stale-command", "advisory-rule", "ratchet-grew"]
    assert report["notes"] == [] and report["chores"] == []


def test_garden_without_a_tag_skips_the_ratchet_scan_and_says_why_once(tmp_path: Path, capsys) -> None:
    repo = garden_repo(tmp_path, tag=False)
    capsys.readouterr()
    assert run_chore_cli("chore", "garden", "--repo-root", str(repo)) == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == _GARDEN_LINES[:3]
    assert out.err.count("no tag to compare against") == 1


def test_open_chores_adds_one_leaf_per_class_then_nothing(tmp_path: Path, capsys) -> None:
    repo = garden_repo(tmp_path)
    capsys.readouterr()
    assert run_chore_cli("chore", "garden", "--open-chores", "--repo-root", str(repo)) == 1
    assert "--open-chores needs --under" in capsys.readouterr().err
    assert run_chore_cli("chore", "garden", "--open-chores", "--under", "M1.1", "--repo-root", str(repo)) == 0
    added = {n["codename"]: n for n in load_roadmap(repo)["nodes"] if n.get("parent_id") == "M1.1"}
    assert sorted(added) == ["garden-advisory-rule", "garden-ratchet-grew", "garden-stale-command"]
    stale = added["garden-stale-command"]
    assert stale["title"] == "Garden: stale command mentions" and stale["touch_zones"] == ["AGENTS.md", "docs/guide.md"]
    assert stale["acceptance"] == [
        "`docs/guide.md` names no specy-road command this version does not register (now: line 3)",
        "`AGENTS.md` names no specy-road command this version does not register (now: line 3)"]
    assert added["garden-ratchet-grew"]["acceptance"][0].endswith("(now: +2 line(s) since v1)")
    before = _roadmap_bytes(repo)
    capsys.readouterr()
    assert run_chore_cli("chore", "garden", "--open-chores", "--under", "M1.1", "--repo-root", str(repo)) == 0
    assert _roadmap_bytes(repo) == before
    assert f"stale-command: {stale['id']} is still open; added nothing" in capsys.readouterr().out


def test_open_chores_files_a_numbered_leaf_once_the_last_is_complete(tmp_path: Path) -> None:
    repo = garden_repo(tmp_path)
    assert run_chore_cli("chore", "garden", "--open-chores", "--under", "M1.1", "--repo-root", str(repo)) == 0
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    for n in doc["nodes"]:
        if n.get("codename") == "garden-stale-command":
            n["status"] = "Complete"
    chunk.write_text(json.dumps(doc, indent=2))
    assert run_chore_cli("chore", "garden", "--open-chores", "--under", "M1.1", "--repo-root", str(repo)) == 0
    codenames = [n.get("codename") for n in load_roadmap(repo)["nodes"]]
    assert codenames.count("garden-stale-command-2") == 1 and codenames.count("garden-advisory-rule") == 1
    assert "Garden: stale command mentions (2)" in [n["title"] for n in load_roadmap(repo)["nodes"]]


def test_garden_cadence_warns_when_due_and_names_the_command(tmp_path: Path, capsys) -> None:
    assert chore_garden.garden_due(garden_repo(tmp_path / "unset"), date.today()) is None
    repo = garden_repo(tmp_path / "set", cadence=7)
    today = date.today()
    assert chore_garden.garden_due(repo, today) == (
        "gardening due: never run, every 7 days; run `specy-road chore garden`")
    record = chore_garden.record_path(repo)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"last_run": (today - timedelta(days=7)).isoformat()}))
    assert chore_garden.garden_due(repo, today) is None                  # due only past the cadence
    record.write_text(json.dumps({"last_run": (today - timedelta(days=8)).isoformat()}))
    assert chore_garden.garden_due(repo, today) == (
        f"gardening due: last run {today - timedelta(days=8)}, every 7 days; run `specy-road chore garden`")
    capsys.readouterr()
    from specy_road.bundled_scripts.validate_roadmap import validate_at  # noqa: PLC0415
    validate_at(repo)
    assert "garden: warning — gardening due: last run" in capsys.readouterr().err
    assert run_chore_cli("chore", "garden", "--repo-root", str(repo)) == 0
    assert chore_garden.garden_due(repo, today) is None                  # the run reset the clock


def test_a_chore_named_garden_survives_a_garden_run(tmp_path: Path, capsys) -> None:
    """R2: the run record is a dot-file, so ``chore garden`` never overwrites a chore's record."""
    repo = chore_repo(tmp_path)
    chore = _start(repo, "garden", "--model", "opus")
    assert run_chore_cli("chore", "garden", "--repo-root", str(repo)) == 0
    assert chore_cli.load_chore(repo, "garden") == chore and chore_garden.record_path(repo).is_file()
    capsys.readouterr()
    assert run_worker_cli("worker", "delegate", "garden", "--json", "--repo-root", str(repo)) == 0
    rec = wait_for_worker(repo, json.loads(capsys.readouterr().out)["worker_id"])
    assert rec.node_id == "garden" and rec.state == "idle"
    assert run_chore_cli("chore", "close", "garden", "--summary", "Garden chore done", "--repo-root", str(repo)) == 0
    assert "Garden chore done" in (repo / "work" / "chores" / "garden.md").read_text()
    assert ws.load_record(repo, rec.worker_id).state == "terminated"


def test_garden_reports_stale_commands_in_the_managed_rules_file(tmp_path: Path, capsys) -> None:
    """R1: ``.specyrd/AGENTS.md`` is in garden's stale-command set; validate's own set is unchanged."""
    from specy_road.bundled_scripts.validate_stale_commands import agent_files  # noqa: PLC0415

    repo = garden_repo(tmp_path)
    commit_file(repo, ".specyrd/AGENTS.md", _RULES + "Run `specy-road nonexistent-garden-probe`.\n", "probe")
    capsys.readouterr()
    assert run_chore_cli("chore", "garden", "--json", "--repo-root", str(repo)) == 0
    stale = [f for f in json.loads(capsys.readouterr().out)["findings"] if f["cls"] == "stale-command"]
    assert {"cls": "stale-command", "path": ".specyrd/AGENTS.md", "line": 7,
            "detail": f"`specy-road nonexistent-garden-probe` is not a command in specy-road {chore_garden.__version__}; "
                      "see `specy-road --help`"} in stale
    assert repo.resolve() / ".specyrd" / "AGENTS.md" not in agent_files(repo)


@pytest.mark.parametrize("state", ["active", "pending_mr"])
def test_open_chores_refuses_a_parent_in_a_locked_milestone(tmp_path: Path, capsys, state: str) -> None:
    """R3: the milestone lock add-node honours; the graph and planning files stay as they were."""
    repo = garden_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["milestone_execution"] = {"state": state, "rollup_branch": "feature/rm-thing",
                                              "integration_branch": "dev", "remote": "origin"}
    chunk.write_text(json.dumps(doc))
    before = _roadmap_bytes(repo)
    capsys.readouterr()
    assert run_chore_cli("chore", "garden", "--open-chores", "--under", "M1.1", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "error: --under M1.1: roadmap node 'M1.1' is inside milestone subtree 'M1.1'" in err
    assert "Pass another --under parent, or run after the milestone closes." in err
    assert _roadmap_bytes(repo) == before
