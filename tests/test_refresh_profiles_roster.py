"""M13.5: refresh-profiles writes only the profiles the roster names; a near-miss roster id names its fix."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road import model_profiles as mp
from specy_road.bundled_scripts import refresh_profiles as rp
from specy_road.bundled_scripts.validate_roadmap import validate_at

from tests.test_models_and_prompt import ROSTER, TEMPLATE_PROFILES, make_profile_repo, run_main

README = "model-profiles/README.md"
OPUS = "model-profiles/anthropic-claude/claude-opus-5-5.md"


def _roster(repo: Path, entries: str) -> None:
    (repo / "roadmap").mkdir(parents=True, exist_ok=True)
    (repo / "roadmap" / "orchestration.yaml").write_text(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n" + entries)


def test_roster_default_writes_only_the_named_profiles_and_the_readme(tmp_path: Path, capsys) -> None:
    _roster(tmp_path, "  - {id: claude-opus-5-5, family: anthropic, roles: [executor]}\n"
                      "  - {id: gpt-5.6-sol-high, family: openai, roles: [reviewer]}\n"
                      "  - id: mine\n    family: x\n    roles: [reviewer]\n"
                      "    profile: model-profiles/spacexai-grok/grok-4.7.md\n")
    assert run_main(rp, "--repo-root", str(tmp_path)) == 0
    written = {p.relative_to(tmp_path).as_posix() for p in (tmp_path / "model-profiles").rglob("*.md")}
    assert written == {README, OPUS, "model-profiles/openai-gpt/gpt-5.6-sol.md",
                       "model-profiles/spacexai-grok/grok-4.7.md"}
    assert "--profiles all" not in capsys.readouterr().out


def test_no_roster_writes_the_readme_and_names_profiles_all(tmp_path: Path, capsys) -> None:
    assert rp.refresh_profiles(tmp_path) == ([README], [])
    assert run_main(rp, "--repo-root", str(tmp_path)) == 0
    assert "`specy-road refresh-profiles --profiles all` adds every one" in capsys.readouterr().out
    assert [p.name for p in (tmp_path / "model-profiles").rglob("*.md")] == ["README.md"]


def test_profiles_all_writes_every_bundled_profile(tmp_path: Path, capsys) -> None:
    _roster(tmp_path, "  - {id: claude-opus-5-5, family: anthropic, roles: [executor]}\n")
    assert run_main(rp, "--profiles", "all", "--repo-root", str(tmp_path)) == 0
    shipped = {p.relative_to(TEMPLATE_PROFILES).as_posix() for p in TEMPLATE_PROFILES.rglob("*.md")}
    assert {p.relative_to(tmp_path / "model-profiles").as_posix()
            for p in (tmp_path / "model-profiles").rglob("*.md")} == shipped
    assert "--profiles all` adds" not in capsys.readouterr().out


def test_force_writes_a_named_profile_the_roster_does_not_name(tmp_path: Path) -> None:
    written, _ = rp.refresh_profiles(tmp_path, force=[OPUS])
    assert written == [README, OPUS]


@pytest.mark.parametrize(("mid", "api_id", "rel"), [
    ("claude-opus-5.5", "claude-opus-5-5", OPUS),
    ("cursor-gpt-5.6-sol-high", "gpt-5.6-sol", "model-profiles/openai-gpt/gpt-5.6-sol.md"),
])
def test_unmatched_roster_id_names_its_near_miss_and_the_roster_line(
        tmp_path: Path, capsys, mid: str, api_id: str, rel: str) -> None:
    repo = make_profile_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(
        ROSTER + f"  - {{id: {mid}, family: x, harness: cursor, roles: [executor]}}\n")
    capsys.readouterr()
    validate_at(repo, no_overlap_warn=True)
    err = capsys.readouterr().err
    assert (f"roster entry {mid!r} in roadmap/orchestration.yaml matches no model profile" in err)
    assert (f"it differs from bundled api_id {api_id} only in punctuation or a vendor/effort prefix or suffix: "
            f"add `profile: {rel}` to that entry") in err


def test_unrelated_roster_id_keeps_todays_text(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(
        ROSTER + "  - {id: totally-unrelated-9, family: x, harness: cursor, roles: [executor]}\n")
    [(_, msg)] = [g for g in mp.roster_profile_gaps(repo) if "totally-unrelated-9" in g[1]]
    assert msg.endswith("list the id in its `aliases` or give the entry `profile:`")
    assert "differs from bundled api_id" not in msg
