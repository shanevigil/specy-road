"""The ``checks:`` migration table: each legacy key row, and its ``checks:`` equivalent, give one result.

``rows.yaml`` was recorded with the legacy keys (``baseline_cmd``, ``land_check_cmd``,
``verify_cmd``) before ``checks:`` existed. Each row names a stage, the legacy config, a
hand-written ``checks:`` equivalent and the CLI value (``--baseline-cmd`` / ``--land-check-cmd``;
``None`` is "not given", ``""`` disables). Its ``expect`` holds what that stage did:

* ``baseline``, ``land-push``, ``land-local``: each command run (its arguments, the directory it ran
  in, any environment variable the caller added), the lines announcing it, and whether the step
  passed; a refused landing also records its first error line.
* ``prompt``: the "Running tests" lines of the executor and reviewer prompts, which name the verify
  command the leaf's test paths are appended to.
* ``evidence``: what ``review packet --verify-cmd`` and ``ready --verify`` record, which no key changes.

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

from specy_road.bundled_scripts import review_cli, review_packet, role_prompt
from specy_road.bundled_scripts.do_next_available import run_baseline_gate
from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.finish_land_local import land_root_locally
from specy_road.review_files import PACKET_NAME, load_ready, reviews_dir

HERE = Path(__file__).resolve().parent
ROWS = yaml.safe_load((HERE / "rows.yaml").read_text(encoding="utf-8"))["rows"]
#: The config forms every row is run in.
FORMS = ("legacy",)
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
    """Each probe run: arguments, ``project`` or ``land worktree`` for where it ran, added variables."""
    if not log.is_file():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        run = json.loads(line)
        cwd = Path(run["cwd"])
        where = ("project" if cwd.resolve() == project.resolve()
                 else "land worktree" if cwd.parent.name.startswith("specy-road-land-check-") else str(cwd))
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
    return {"runs": _runs(tmp / "probe.log", repo), "printed": _announced(out, "baseline on "), "ok": ok}


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
    result = {"runs": _runs(tmp / "probe.log", repo), "printed": _announced(out, "land check on "), "ok": ok}
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
def test_row_gives_its_recorded_result(row: dict, form: str, tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CHECKS_PROBE_LOG", str(tmp_path / "probe.log"))
    config = _sub(row[form] or "")
    row = {**row, "cli": None if row["cli"] is None else _sub(row["cli"])}
    assert STAGES[row["stage"]](tmp_path, config, row, capsys) == row["expect"]
