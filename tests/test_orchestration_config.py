"""Tests for roadmap/orchestration.yaml loading, defaults, and substitutions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road import orchestration_config as oc
from specy_road.bundled_scripts.validate_roadmap import validate_orchestration_contract

TEMPLATE = (
    Path(oc.__file__).resolve().parent / "templates" / "project" / "roadmap" / "orchestration.yaml"
)


def _write(root: Path, text: str) -> None:
    (root / "roadmap").mkdir(parents=True, exist_ok=True)
    (root / "roadmap" / "orchestration.yaml").write_text(text, encoding="utf-8")


def test_missing_file_yields_default_policy(tmp_path: Path) -> None:
    assert oc.load_orchestration_config(tmp_path) == (None, None)
    cfg, err = oc.effective_config(tmp_path)
    assert err is None
    assert cfg["policy"] == oc.DEFAULT_POLICY
    assert oc.is_rostered_reviewer(cfg, "human")
    assert oc.family_of(cfg, "human") == "human"


def test_template_validates_and_matches_defaults(tmp_path: Path) -> None:
    _write(tmp_path, TEMPLATE.read_text(encoding="utf-8"))
    data, err = oc.load_orchestration_config(tmp_path)
    assert err is None
    cfg, _ = oc.effective_config(tmp_path)
    assert cfg["policy"] == oc.DEFAULT_POLICY
    human, executor = cfg["roster"]
    assert [human] == oc.DEFAULT_CONFIG["roster"]
    assert executor["roles"] == ["executor"]
    assert data["substitutions"] == []


def test_init_writes_the_starter_and_validate_generates_it_when_missing(tmp_path: Path, monkeypatch) -> None:
    from specy_road.bundled_scripts import validate_roadmap
    from specy_road.init_project import run_init_project

    assert run_init_project(tmp_path) == 0
    dest = tmp_path / "roadmap" / "orchestration.yaml"
    assert dest.read_text(encoding="utf-8") == TEMPLATE.read_text(encoding="utf-8")
    argv = ["validate", "--generate-orchestration", "--repo-root", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    dest.unlink()
    validate_roadmap.main()
    assert dest.read_text(encoding="utf-8") == TEMPLATE.read_text(encoding="utf-8")
    dest.write_text("version: 1\n", encoding="utf-8")
    validate_roadmap.main()
    assert dest.read_text(encoding="utf-8") == "version: 1\n"


def test_dogfood_fixture_validates() -> None:
    validate_orchestration_contract(DOGFOOD)


def test_partial_policy_is_filled_from_defaults(tmp_path: Path) -> None:
    _write(tmp_path, "version: 1\npolicy:\n  reviewers_required: 2\n")
    cfg, err = oc.effective_config(tmp_path)
    assert err is None
    assert cfg["policy"]["reviewers_required"] == 2
    assert cfg["policy"]["reviewers_distinct_families"] is False
    assert cfg["roster"] == []


@pytest.mark.parametrize(
    "body, fragment",
    [
        ("version: 1\npolicy:\n  reviewers_required: 0\n", "reviewers_required"),
        ("version: 1\nroster:\n  - id: x\n", "family"),
        ("version: 1\nroster:\n  - {id: x, family: y, roles: [boss]}\n", "roles"),
        ("version: 2\n", "version"),
        ("- not a mapping\n", "must be a mapping"),
    ],
)
def test_invalid_config_reports_error(tmp_path: Path, body: str, fragment: str) -> None:
    _write(tmp_path, body)
    data, err = oc.load_orchestration_config(tmp_path)
    assert data is None
    assert err and fragment in err
    cfg, err2 = oc.effective_config(tmp_path)
    assert err2 == err
    assert cfg["policy"] == oc.DEFAULT_POLICY
    with pytest.raises(SystemExit):
        validate_orchestration_contract(tmp_path)


_SUBS = """version: 1
roster:
  - {id: gpt-6-astra, family: openai, roles: [executor]}
  - {id: gemini-3.8-flash, family: google, roles: [executor]}
substitutions:
  - slot: reviewer-openai
    use: gpt-6-astra
    scope: [M2.3]
    decided: 2026-01-15
    expires: 2026-03-01
  - slot: reviewer-google
    use: gemini-3.8-flash
    decided: 2026-01-15
    expires_when: google reviewer is back
"""


def test_unquoted_yaml_dates_validate(tmp_path: Path) -> None:
    _write(tmp_path, _SUBS)
    data, err = oc.load_orchestration_config(tmp_path)
    assert err is None
    assert data["substitutions"][0]["decided"] == "2026-01-15"


def test_active_substitutions_respect_scope_and_expiry(tmp_path: Path) -> None:
    _write(tmp_path, _SUBS)
    cfg, _ = oc.effective_config(tmp_path)
    before = date(2026, 2, 1)
    after = date(2026, 3, 2)
    assert oc.substitute_for(cfg, "M2.3", "gpt-6-astra", before)
    assert oc.substitute_for(cfg, "M2.3", "gpt-6-astra", date(2026, 3, 1))
    assert oc.substitute_for(cfg, "M2.3", "gpt-6-astra", after) is None
    assert oc.substitute_for(cfg, "M2.4", "gpt-6-astra", before) is None
    # No scope covers every node; no expires never lapses.
    assert oc.substitute_for(cfg, "M9", "gemini-3.8-flash", after)


@pytest.mark.parametrize(
    "body, fragment",
    [
        ("version: 1\nroster:\n  - {id: a, family: x}\n  - {id: a, family: y}\n", "duplicate id(s) a"),
        ("version: 1\nsubstitutions:\n  - {slot: s, use: ghost, decided: 2026-01-01, expires: 2026-02-01}\n",
         "must be a roster entry"),
        ("version: 1\nroster:\n  - {id: a, family: x}\nsubstitutions:\n"
         "  - {slot: s, use: a, scope: [], decided: 2026-01-01, expires: 2026-02-01}\n", "scope"),
        ("version: 1\nroster:\n  - {id: a, family: x}\nsubstitutions:\n"
         "  - {slot: s, use: a, decided: 2026-01-01}\n", "substitutions/0"),
    ],
)
def test_substitution_and_roster_rules(tmp_path: Path, body: str, fragment: str) -> None:
    _write(tmp_path, body)
    _data, err = oc.load_orchestration_config(tmp_path)
    assert err and fragment in err, err


def test_substitution_decided_in_the_future_is_not_active(tmp_path: Path) -> None:
    _write(tmp_path, _SUBS)
    cfg, _ = oc.effective_config(tmp_path)
    assert oc.substitute_for(cfg, "M2.3", "gpt-6-astra", date(2026, 1, 14)) is None


def test_effective_config_reads_a_git_ref(tmp_path: Path) -> None:
    import subprocess

    def git(*a: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    git("init", "-q", "-b", "dev")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    _write(tmp_path, "version: 1\npolicy: {reviewers_required: 2}\n")
    git("add", "-A")
    git("commit", "-qm", "strict")
    _write(tmp_path, "version: 1\npolicy: {reviewers_required: 1}\n")
    assert oc.effective_config(tmp_path)[0]["policy"]["reviewers_required"] == 1
    assert oc.effective_config(tmp_path, "dev")[0]["policy"]["reviewers_required"] == 2
    git("rm", "-qf", "roadmap/orchestration.yaml")
    git("commit", "-qm", "drop")
    assert oc.effective_config(tmp_path, "dev")[0]["policy"] == oc.DEFAULT_POLICY


def test_roster_harness_and_policy_max_workers(tmp_path: Path) -> None:
    _write(tmp_path, "version: 1\nroster:\n  - {id: opus, family: anthropic, harness: claude-code, billing_route: claude_subscription}\n"
                     "policy: {max_workers: 3}\n")
    cfg, err = oc.effective_config(tmp_path)
    assert err is None and cfg["policy"]["max_workers"] == 3
    assert oc.roster_entry(cfg, "opus")["harness"] == "claude-code"
    assert oc.effective_config(tmp_path / "none")[0]["policy"]["max_workers"] == 2
    _write(tmp_path, "version: 1\nroster:\n  - {id: opus, family: anthropic, harness: copilot}\n")
    assert "harness" in (oc.load_orchestration_config(tmp_path)[1] or "")
    _write(tmp_path, "version: 1\npolicy: {max_workers: 0}\n")
    assert "max_workers" in (oc.load_orchestration_config(tmp_path)[1] or "")
