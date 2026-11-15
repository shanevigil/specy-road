"""The grind-session settings under ``grind:``: the migration table, ``upgrade`` and validate.

Each row of ``TABLE`` is one form of ``roadmap/git-workflow.yaml`` (no setting, the old top-level
``grind_session_*`` keys only, ``grind:`` only, both, and old keys beside an existing ``grind:``
block) with the effective values grind-session reads from it. Each row gives those values as
written and again after ``upgrade``'s rewrite, which a second run leaves alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import validate_roadmap
from specy_road.bundled_scripts.upgrade import migrate_grind_text, run_upgrade
from specy_road.git_workflow_config import validate_git_workflow_dict
from specy_road.grind_status import watch_seconds
from specy_road.orchestration.grind.grind_session import resolve_implement_limits
from tests.review_repo_helpers import git, make_review_repo
from tests.upgrade_repo_helpers import old_repo

_GW = "version: 1\nintegration_branch: main\nremote: origin\n"
DEFAULTS = {"max_resumes": 3, "max_wait_seconds": 6 * 3600, "grace_seconds": 120,
            "max_empty_retries": 2, "watch_seconds": 30 * 60}
OLD_ALL = ("grind_session_max_limit_waits: 5\ngrind_session_max_limit_wait_hours: 8\n"
           "grind_session_limit_wait_grace_seconds: 30\ngrind_session_max_empty_retries: 1\n"
           "grind_session_status_interval_minutes: 10\n")
NEW_ALL = ("grind:\n  max_limit_waits: 5\n  max_limit_wait_hours: 8\n"
           "  limit_wait_grace_seconds: 30\n  max_empty_retries: 1\n  status_interval_minutes: 10\n")
SET_ALL = {"max_resumes": 5, "max_wait_seconds": 8 * 3600, "grace_seconds": 30,
           "max_empty_retries": 1, "watch_seconds": 10 * 60}

#: id -> (config after the core keys, effective values, ``grind:`` after upgrade or None).
TABLE = {
    "absent": ("", DEFAULTS, None),
    "old form only": (OLD_ALL, SET_ALL, {"max_limit_waits": 5, "max_limit_wait_hours": 8,
                                         "limit_wait_grace_seconds": 30, "max_empty_retries": 1,
                                         "status_interval_minutes": 10}),
    "new form only": (NEW_ALL, SET_ALL, None),
    "both, new wins": (
        "grind_session_max_limit_waits: 9\ngrind_session_status_interval_minutes: 99\n"
        "grind:\n  max_limit_waits: 5\n  status_interval_minutes: 10\n",
        {**DEFAULTS, "max_resumes": 5, "watch_seconds": 10 * 60},
        {"max_limit_waits": 5, "status_interval_minutes": 10}),
    "existing grind: block kept and merged": (
        "grind:\n  # zones that never overlap\n  shared_zones: [docs/]\n  max_empty_retries: 0\n"
        "grind_session_max_limit_wait_hours: 8\ngrind_session_max_empty_retries: 4\n",
        {**DEFAULTS, "max_wait_seconds": 8 * 3600, "max_empty_retries": 0},
        {"shared_zones": ["docs/"], "max_empty_retries": 0, "max_limit_wait_hours": 8}),
}


def _effective(root: Path, text: str) -> dict[str, int]:
    gw = root / "roadmap" / "git-workflow.yaml"
    gw.parent.mkdir(parents=True, exist_ok=True)
    gw.write_text(text, encoding="utf-8")
    limits = resolve_implement_limits(root)
    return {"max_resumes": limits.max_resumes, "max_wait_seconds": limits.max_wait_seconds,
            "grace_seconds": limits.grace_seconds, "max_empty_retries": limits.max_empty_retries,
            "watch_seconds": watch_seconds(root, True)}


@pytest.mark.parametrize("row", TABLE)
def test_each_form_gives_its_values_before_and_after_upgrade(row: str, tmp_path: Path) -> None:
    """A1/A2: each form's effective values, unchanged by upgrade's rewrite; a second run is a no-op."""
    config, values, grind_after = TABLE[row]
    text = _GW + config
    assert _effective(tmp_path, text) == values
    done = migrate_grind_text(text)
    if grind_after is None:
        assert done is None
        return
    assert done.layout_kept
    after = yaml.safe_load(done.text)
    assert after["grind"] == grind_after
    assert not [k for k in after if k.startswith("grind_session_")]
    assert validate_git_workflow_dict(after) is None
    assert ("# zones that never overlap" in done.text) is ("shared_zones" in grind_after)
    assert _effective(tmp_path, done.text) == values
    assert migrate_grind_text(done.text) is None


@pytest.mark.parametrize(("text", "kept"), [
    (_GW + "grind: {shared_zones: []}\ngrind_session_max_limit_waits: 5\n", False),
    (_GW + "on_complete: merge  # land locally\ngrind_session_max_limit_waits: 5\n", True),
])
def test_upgrade_keeps_every_value_when_the_line_edit_cannot(text: str, kept: bool) -> None:
    """A flow ``grind:`` mapping is written again in block style; a block layout keeps comments."""
    done = migrate_grind_text(text)
    assert done is not None and done.layout_kept is kept
    after = yaml.safe_load(done.text)
    assert after["grind"]["max_limit_waits"] == 5 and "grind_session_max_limit_waits" not in after
    assert ("# land locally" in done.text) is kept


@pytest.mark.parametrize("text", ["grind_session_max_limit_waits: [5\n",
                                  _GW + "grind: 3\ngrind_session_max_limit_waits: 5\n"])
def test_upgrade_leaves_a_file_validate_rejects(text: str) -> None:
    """Not YAML, or ``grind:`` not a mapping: left as it is, for validate to report."""
    assert migrate_grind_text(text) is None


def test_upgrade_moves_the_keys_once_and_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    """A2: ``--dry-run`` writes nothing; upgrade moves the keys, and running it again changes
    nothing."""
    root = old_repo(tmp_path / "repo")
    gw = root / "roadmap" / "git-workflow.yaml"
    gw.write_text(gw.read_text(encoding="utf-8") + "grind_session_max_limit_waits: 5\n",
                  encoding="utf-8")
    before = gw.read_text(encoding="utf-8")
    assert run_upgrade(root, dry_run=True) == 0
    assert gw.read_text(encoding="utf-8") == before
    assert "would write roadmap/git-workflow.yaml (grind_session_* keys move under grind:)" \
        in capsys.readouterr().out
    assert run_upgrade(root) == 0
    after = gw.read_text(encoding="utf-8")
    assert yaml.safe_load(after)["grind"] == {"max_limit_waits": 5}
    assert run_upgrade(root) == 0
    assert gw.read_text(encoding="utf-8") == after


@pytest.mark.parametrize(("config", "notices"), [
    ("grind_session_max_limit_waits: 5\n", 1),
    ("grind_session_max_limit_waits: 5\ngrind:\n  max_limit_waits: 4\n", 1),
    ("grind:\n  max_limit_waits: 4\n", 0),
])
def test_validate_accepts_both_forms_with_one_notice_for_the_old(
        config: str, notices: int, tmp_path: Path, capsys) -> None:
    """A2: validate passes with either form and prints one notice while an old key is present."""
    repo = make_review_repo(tmp_path)
    gw = repo / "roadmap" / "git-workflow.yaml"
    gw.write_text(gw.read_text(encoding="utf-8") + config, encoding="utf-8")
    git(repo, "commit", "-q", "-am", "config")
    capsys.readouterr()
    validate_roadmap.main(["--repo-root", str(repo)])
    found = [line for line in capsys.readouterr().out.splitlines()
             if "grind_session_max_limit_waits" in line]
    assert len(found) == notices, found
