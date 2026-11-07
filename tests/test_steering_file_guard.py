"""M22.31: finish-this-task refuses a branch that changes a steering file no touch zone names exactly.

Public finish in merge mode, at the git root (``embedded``) and in a nested project (``nested``, project ``sr/``):
an exact zone lands; an absent, directory or glob zone refuses naming the path and leaves the branch tip and the
registry as they were; a registry-only change lands; a diff that cannot be read refuses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.helpers import REPO
from tests.review_repo_helpers import (
    commit_file,
    git,
    git_root_relative,
    make_layout_finish_repo,
    prepare_layout_merge_mode_remote,
)

from specy_road import steering_gate
from specy_road.bundled_scripts import finish_task

#: ``(path, class, from the git root)``: one representative path per class; the policy file is project-relative.
PATHS = {
    "harness": (".claude/settings.json", False),
    "policy_tree": ("roadmap/git-workflow.yaml", False),
    "shell_startup": (".bashrc", True),
}
#: Zone kind -> the zone added for each class (``None``: no zone for it).
ZONES = {
    "exact": {"harness": ".claude/settings.json", "policy_tree": "roadmap/git-workflow.yaml",
              "shell_startup": ".bashrc"},
    "absent": {"harness": None, "policy_tree": None, "shell_startup": None},
    "directory": {"harness": ".claude", "policy_tree": "roadmap"},
    "glob": {"harness": ".claude/*.json", "policy_tree": "roadmap/*.yaml", "shell_startup": ".*rc"},
}
CASES = [(cls, kind) for kind, by_cls in ZONES.items() for cls in by_cls]


def _leaf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str) -> tuple[Path, Path]:
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    git_top, project = make_layout_finish_repo(tmp_path / "x", shape)
    prepare_layout_merge_mode_remote(git_top, project, tmp_path / "lane")
    return git_top, project


def _finish(project: Path) -> int:
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(project)])
        raise SystemExit(0)
    return e.value.code or 0


def _set_zones(git_top: Path, project: Path, zones: list[str]) -> None:
    rel = git_root_relative(git_top, project, "roadmap/registry.yaml")
    doc = yaml.safe_load((git_top / rel).read_text())
    doc["entries"][0]["touch_zones"] = zones
    commit_file(git_top, rel, yaml.safe_dump(doc), "zones")


@pytest.mark.parametrize("shape", ["embedded", "nested"])
@pytest.mark.parametrize(("cls", "kind"), CASES)
def test_finish_lands_a_steering_file_only_under_an_exact_zone(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        shape: str, cls: str, kind: str) -> None:
    git_top, project = _leaf(tmp_path, monkeypatch, shape)
    path, at_git_root = PATHS[cls]
    zone = ZONES[kind][cls]
    if zone:   # as edit-node would: the claim row's zones (a registry change never counts)
        _set_zones(git_top, project, ["src", zone])
    rel = path if at_git_root else git_root_relative(git_top, project, path)
    old = (git_top / rel).read_text() if (git_top / rel).exists() else ""
    commit_file(git_top, rel, old + "# steering change\n", "steering change")
    reg = project / "roadmap" / "registry.yaml"
    before, reg_before = git(git_top, "rev-parse", "HEAD"), reg.read_text()
    code = _finish(project)
    err = capsys.readouterr().err
    if kind == "exact":
        assert code == 0 and "steering" not in err
        return
    assert code == 1 and f"{path} ({cls})" in err and "edit-node M1.1" in err
    assert git(git_top, "rev-parse", "HEAD") == before   # refused before the bookkeeping commit
    assert reg.read_text() == reg_before and not git(git_top, "status", "--porcelain", "--untracked-files=no")


def test_a_registry_only_change_lands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    git_top, project = _leaf(tmp_path, monkeypatch, "nested")
    _set_zones(git_top, project, ["src", "docs"])
    assert _finish(project) == 0 and "steering" not in capsys.readouterr().err


def test_a_diff_that_cannot_be_read_refuses_before_bookkeeping(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    git_top, project = _leaf(tmp_path, monkeypatch, "embedded")
    monkeypatch.setattr(steering_gate, "diff_paths", lambda *_a: None)   # git cannot answer
    before = git(git_top, "rev-parse", "HEAD")
    assert _finish(project) == 1
    err = capsys.readouterr().err
    assert "paths changed since the merge base" in err and "could not be read" in err
    assert git(git_top, "rev-parse", "HEAD") == before
