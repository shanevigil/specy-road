"""The ``checks:`` migration table: each legacy key row and its ``checks:`` equivalent agree.

``rows.yaml`` was recorded with the legacy keys (``baseline_cmd``, ``land_check_cmd``,
``verify_cmd``) before ``checks:`` existed. Each row names a stage, the legacy config, a
hand-written ``checks:`` equivalent and the CLI value (``--baseline-cmd`` / ``--land-check-cmd``;
``None`` is "not given", ``""`` disables). Its ``expect`` holds what that stage did:

* ``baseline``, ``land-push``, ``land-local``: each command run (its arguments, the directory it ran
  in, any environment variable the caller added), the lines announcing it, and whether the step
  passed; a refused landing also records its first error line.
* ``prompt``: the "Running tests" lines of the executor and reviewer prompts, which name the verify
  command the leaf's test paths are appended to.
* ``evidence``: what ``review packet --verify-cmd`` and ``ready --verify`` record, which no key
  changes.

Each row also holds after ``upgrade`` rewrote its legacy config. The tests after the table cover
what no single row does: both forms at once, the order of several entries, and ``upgrade`` itself.

``PROBE`` in a command stands for ``probe.py`` run by this interpreter; it is written back as
``PROBE`` in what is compared, so the table holds no machine path.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import git, make_review_repo
from tests.test_models_and_prompt import make_profile_repo

from specy_road.bundled_scripts import review_cli, review_packet, role_prompt, validate_roadmap
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.checks_config import migrate_text
from specy_road.bundled_scripts.do_next_available import run_baseline_gate
from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.finish_land_local import land_root_locally
from specy_road.review_files import PACKET_NAME, load_ready, reviews_dir
from tests.upgrade_repo_helpers import old_repo

HERE = Path(__file__).resolve().parent
ROWS = yaml.safe_load((HERE / "rows.yaml").read_text(encoding="utf-8"))["rows"]
#: The config forms every row is run in.
FORMS = ("legacy", "checks")
#: Variables a shell sets itself; not added by the caller.
SHELL_VARS = {"PWD", "OLDPWD", "SHLVL", "_"}
_SHA = re.compile(r"\b[0-9a-f]{12}\b")
_GW = "version: 1\nintegration_branch: main\nremote: origin\n"


def _probe() -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(HERE / 'probe.py'))}"


def _sub(text: str) -> str:
    return text.replace("PROBE", _probe())


def _unsub(text: str) -> str:
    return _SHA.sub("<sha>", text.replace(_probe(), "PROBE"))


def _runs(log: Path, project: Path) -> list[dict]:
    """Each probe run: its arguments, where it ran (project or land worktree), added variables."""
    if not log.is_file():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        run = json.loads(line)
        cwd = Path(run["cwd"])
        in_land_worktree = cwd.parent.name.startswith("specy-road-land-check-")
        where = ("project" if cwd.resolve() == project.resolve()
                 else "land worktree" if in_land_worktree else str(cwd))
        added = sorted(set(run["env"]) - set(os.environ) - SHELL_VARS)
        out.append({"argv": run["argv"], "cwd": where, "env_added": added})
    log.unlink()
    return out


def _announced(text: str, prefix: str) -> list[str]:
    return [_unsub(line) for line in text.splitlines() if line.startswith(prefix)]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _commit_all(cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-qm", message)


def _baseline(tmp: Path, config: str, row: dict, capsys) -> dict:
    repo = tmp / "repo"
    _git(tmp, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    (repo / "roadmap").mkdir()
    (repo / "roadmap" / "git-workflow.yaml").write_text(_GW + config, encoding="utf-8")
    (repo / ".gitignore").write_text("work/\n", encoding="utf-8")
    _commit_all(repo, "init")
    capsys.readouterr()
    try:
        run_baseline_gate(repo, "main", cli=row["cli"], warn_only=False)
        ok = True
    except SystemExit as e:
        ok = not e.code
    out = capsys.readouterr().out
    return {"runs": _runs(tmp / "probe.log", repo), "printed": _announced(out, "baseline on "),
            "ok": ok}


def _land(tmp: Path, config: str, row: dict, capsys) -> dict:
    bare, repo = tmp / "remote.git", tmp / "work"
    _git(tmp, "init", "--bare", "-q", "-b", "main", str(bare))
    _git(tmp, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "roadmap").mkdir()
    (repo / "roadmap" / "git-workflow.yaml").write_text(_GW + config, encoding="utf-8")
    _commit_all(repo, "init")
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(repo, "checkout", "-qb", "feature/rm-x")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _commit_all(repo, "feature work")
    capsys.readouterr()
    if row["stage"] == "land-push":
        ok, err = land_merge_feature_into_integration(
            repo, remote="origin", integration_branch="main", feature_branch="feature/rm-x",
            land_check_cmd=row["cli"])
    else:
        ok, err = land_root_locally(repo, integration_branch="main", feature_branch="feature/rm-x",
                                    land_check_cmd=row["cli"])
    out = capsys.readouterr().out
    result = {"runs": _runs(tmp / "probe.log", repo), "printed": _announced(out, "land check on "),
              "ok": ok}
    if not ok:
        result["error"] = _unsub(err.splitlines()[0])
    return result


def _set_config(repo: Path, config: str) -> None:
    gw = repo / "roadmap" / "git-workflow.yaml"
    gw.write_text(gw.read_text(encoding="utf-8") + config, encoding="utf-8")
    git(repo, "commit", "-q", "--allow-empty", "-am", "config")


def _running_tests(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("**Running tests:**")]


def _prompt(tmp: Path, config: str, _row: dict, _capsys) -> dict:
    repo = make_profile_repo(tmp)
    _set_config(repo, config)
    executor = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n\n- **Commit under review:** `abc`\n")
    reviewer, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    return {"executor": _running_tests(executor), "reviewer": _running_tests(reviewer)}


def _evidence(tmp: Path, config: str, _row: dict, capsys) -> dict:
    repo = make_review_repo(tmp)
    _set_config(repo, config)
    packet = review_packet.build_packet(repo, "M1.1", ref=None, verify_cmds=["echo checked"])
    with pytest.raises(SystemExit) as e:
        review_cli.main(["ready", "M1.1", "--model", "opus", "--verify", "pytest tests/x.py=0",
                         "--repo-root", str(repo)])
    assert e.value.code == 0, capsys.readouterr().err
    ready = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    return {"packet": [line for line in packet.splitlines() if line.startswith("### `")],
            "ready_verify": ready.data["verify"]}


STAGES = {"baseline": _baseline, "land-push": _land, "land-local": _land, "prompt": _prompt,
          "evidence": _evidence}


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_row_gives_its_recorded_result(row: dict, form: str, tmp_path: Path, monkeypatch,
                                       capsys) -> None:
    """A1/A3: the row's legacy config and its ``checks:`` equivalent give the recorded result."""
    monkeypatch.setenv("CHECKS_PROBE_LOG", str(tmp_path / "probe.log"))
    config = _sub(row[form] or "")
    row = {**row, "cli": None if row["cli"] is None else _sub(row["cli"])}
    assert STAGES[row["stage"]](tmp_path, config, row, capsys) == row["expect"]


@pytest.mark.parametrize("row", [r for r in ROWS if r["legacy"]], ids=lambda r: r["id"])
def test_upgraded_row_gives_its_recorded_result(row: dict, tmp_path: Path, monkeypatch,
                                                capsys) -> None:
    """A4: the row's legacy config after ``upgrade``'s rewrite gives the recorded result, once."""
    upgraded = migrate_text(_GW + _sub(row["legacy"]))
    assert upgraded is not None and migrate_text(upgraded) is None   # a second run changes nothing
    monkeypatch.setenv("CHECKS_PROBE_LOG", str(tmp_path / "probe.log"))
    row = {**row, "cli": None if row["cli"] is None else _sub(row["cli"])}
    config = upgraded.removeprefix(_GW)
    assert STAGES[row["stage"]](tmp_path, config, row, capsys) == row["expect"]


MIXED = ("baseline_cmd: PROBE old\n"
         "checks:\n  - {name: baseline, run: PROBE baseline, when: baseline}\n")


def _validate_notices(tmp: Path, config: str, capsys) -> list[str]:
    repo = make_review_repo(tmp)
    _set_config(repo, config)
    capsys.readouterr()
    validate_roadmap.main(["--repo-root", str(repo)])
    return [line for line in capsys.readouterr().out.splitlines() if "checks:" in line]


@pytest.mark.parametrize(("config", "notices"), [
    ("baseline_cmd: make test\n", ["uses baseline_cmd, read until the release after 0.3.1"]),
    (MIXED, ["has checks:, so baseline_cmd (removed in the release after 0.3.1) is ignored"]),
    ("checks:\n  - {name: b, run: make test, when: baseline}\n", []),
])
def test_validate_prints_one_notice_for_the_old_form(config: str, notices: list[str],
                                                      tmp_path: Path, capsys) -> None:
    """A3/A4: one validate notice for the old form, alone or beside ``checks:``; else none."""
    found = _validate_notices(tmp_path, config, capsys)
    assert len(found) == len(notices), found
    assert all(n in line for n, line in zip(notices, found, strict=True)), found


def test_with_both_forms_the_checks_entry_runs(tmp_path: Path, monkeypatch, capsys) -> None:
    """A3: with both forms present the ``checks:`` entry runs, not the legacy key."""
    monkeypatch.setenv("CHECKS_PROBE_LOG", str(tmp_path / "probe.log"))
    expect = next(r["expect"] for r in ROWS if r["id"] == "baseline-set")
    assert _baseline(tmp_path, _sub(MIXED), {"cli": None}, capsys) == expect


@pytest.mark.parametrize("stage", ["baseline", "land-push", "land-local"])
def test_entries_run_in_file_order_until_one_fails(stage: str, tmp_path: Path, monkeypatch,
                                                   capsys) -> None:
    """Several entries of one stage run in file order, and the first failure stops the stage."""
    when = "baseline" if stage == "baseline" else "land"
    config = _sub(f"checks:\n  - {{name: a, run: PROBE first, when: {when}}}\n"
                  f"  - {{name: b, run: PROBE second fail, when: [{when}, prompt]}}\n"
                  f"  - {{name: c, run: PROBE third, when: {when}}}\n")
    monkeypatch.setenv("CHECKS_PROBE_LOG", str(tmp_path / "probe.log"))
    got = STAGES[stage](tmp_path, config, {"stage": stage, "cli": None}, capsys)
    assert [r["argv"] for r in got["runs"]] == [["first"], ["second", "fail"]]
    assert got["ok"] is False


def test_upgrade_rewrites_the_keys_once_and_leaves_the_review_switch(tmp_path: Path,
                                                                     capsys) -> None:
    """A4: ``--dry-run`` writes nothing; upgrade rewrites the keys once, keeping other lines."""
    root = old_repo(tmp_path / "repo")
    gw = root / "roadmap" / "git-workflow.yaml"
    legacy = "baseline_cmd: make test\nland_check_cmd: make all  # full gate\nverify_cmd: '  '\n"
    gw.write_text(gw.read_text(encoding="utf-8") + legacy, encoding="utf-8")
    before = gw.read_text(encoding="utf-8")
    assert run_upgrade(root, dry_run=True) == 0
    assert gw.read_text(encoding="utf-8") == before
    out = capsys.readouterr().out
    assert "would write roadmap/git-workflow.yaml (baseline_cmd, land_check_cmd" in out
    assert run_upgrade(root) == 0
    after = gw.read_text(encoding="utf-8")
    data = yaml.safe_load(after)
    assert data["checks"] == [{"name": "baseline", "run": "make test", "when": "baseline"},
                              {"name": "land check", "run": "make all", "when": "land"}]
    assert not {"baseline_cmd", "land_check_cmd", "verify_cmd"} & set(data)
    assert data["require_implementation_review_before_finish"] is True
    assert after[:after.index("\nchecks:\n") + 1] == before.replace(legacy, "")
    assert run_upgrade(root) == 0
    assert gw.read_text(encoding="utf-8") == after


def test_upgrade_leaves_a_file_that_is_not_yaml_to_validate() -> None:
    """A file that is not YAML is left as it is, for validate to report."""
    assert migrate_text("baseline_cmd: [make test\n") is None
