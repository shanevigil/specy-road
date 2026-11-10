"""M11.26: effort-suffixed Cursor ids match profiles; models list reports unmatched roster ids.
M11.76: validate warns for them, and the shipped profiles alias the Cursor ids they cover.
M21.44: the shipped guidance-bypass flag, and ``guidance_bypass_refusal``'s three-argument contract on it.
M22.66: an entry whose id matches no profile matches one by its ``harness_model``, on both lookups."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from specy_road import model_profiles as mp
from specy_road.bundled_scripts import models_cli, role_prompt
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.orchestrate_plan import guidance_bypass_refusal
from specy_road.orchestration_pinned import pinned_profile_for_entry

from tests.review_repo_helpers import git, shipped_anthropic_opus_cli_yaml_line
from tests.test_models_and_prompt import ROSTER, TEMPLATE_PROFILES, commit_profile, make_profile_repo, run_main


def test_shipped_cursor_family_profiles_list_effort_suffix_aliases() -> None:
    gpt = mp.load_profile(TEMPLATE_PROFILES / "openai-gpt" / "gpt-5.6-sol.md")
    assert gpt.ok and gpt.for_id("gpt-5.6-sol-high") and gpt.for_id("gpt-5.6-sol-xhigh")
    comp = mp.load_profile(TEMPLATE_PROFILES / "cursor-composer" / "composer-2.5.md")
    assert comp.ok and comp.for_id("composer-2.5-fast") and comp.for_id("composer-2.5-fast").api_id == "composer-2.5-fast"
    grok = mp.load_profile(TEMPLATE_PROFILES / "spacexai-grok" / "grok-4.7.md")
    assert grok.for_id("grok-4.7-high")
    prev = mp.load_profile(TEMPLATE_PROFILES / "spacexai-grok" / "grok-4.6.md")
    assert prev.for_id("cursor-grok-4.6-high")


def test_models_list_names_unmatched_roster_ids_and_alias_in_json(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    assert run_main(models_cli, "models", "list", "--repo-root", str(repo)) == 0
    text = capsys.readouterr().out
    assert "roster id(s) match no profile" in text and "  sol\n" in text
    assert "  human\n" not in text
    assert run_main(models_cli, "models", "list", "--json", "--repo-root", str(repo)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["unmatched_roster_ids"] == ["sol"]
    assert "human" not in out["unmatched_roster_ids"]
    rows = {r["id"]: r for r in out["roster"]}
    assert rows["sol"]["profile"] is None


CLOSEST = "closest profile is model-profiles/anthropic-claude/claude-opus-5-5.md (api_id claude-opus-5-5)"


def _gap(mid: str) -> str:
    return f"roster entry {mid!r} in roadmap/orchestration.yaml matches no model profile by api_id, file name or alias of its id or harness_model"


def _validate_roster(tmp_path: Path, capsys, extra: str):
    repo = make_profile_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(ROSTER + extra)
    capsys.readouterr()
    validate_at(repo, no_overlap_warn=True)
    return capsys.readouterr()


def test_validate_warns_for_an_unmatched_launchable_roster_id_and_names_the_closest_profile(
        tmp_path: Path, capsys) -> None:
    """M11.76: an executor/reviewer id with a harness or channels.cli and no profile is a stderr warning."""
    cap = _validate_roster(tmp_path, capsys,
                           "  - {id: claude-opus-5-5-high, family: anthropic, harness: cursor, roles: [reviewer]}\n"
                           "  - {id: claude-opus-5.5, family: anthropic, harness: claude-code, roles: [executor]}\n"
                           "  - id: claude-opus-5.5-rev\n    family: anthropic\n    roles: [reviewer]\n"
                           "    channels: {cli: 'review.sh \"<prompt>\"'}\n"
                           "  - {id: claude-opus-5.5-chair, family: anthropic, harness: cursor, roles: [coordinator]}\n")
    for mid in ("claude-opus-5.5", "claude-opus-5.5-rev"):
        assert f"warning: {_gap(mid)}" in cap.err and _gap(mid) not in cap.out
    assert CLOSEST in cap.err
    for matched in ("'opus'", "'claude-opus-5-5-high'", "'human'", "'claude-opus-5.5-chair'"):
        assert f"roster entry {matched}" not in cap.err + cap.out


def test_validate_notes_an_unmatched_roster_id_nothing_can_launch_on_stdout(tmp_path: Path, capsys) -> None:
    """M11.76: an entry with neither harness nor channels.cli is a stdout
    notice that --strict does not count, still naming the closest profile."""
    cap = _validate_roster(tmp_path, capsys, "  - {id: claude-opus-5.5, family: anthropic, roles: [executor]}\n")
    for mid in ("claude-opus-5.5", "sol"):
        assert f"notice: {_gap(mid)}" in cap.out and _gap(mid) not in cap.err
    assert CLOSEST in cap.out


NO_CLOSE_NAME = "has a close name; add one or give the entry `profile:`"


@pytest.mark.parametrize("mid, extra, launchable, closest", [
    (mp.STARTER_PLACEHOLDER_ID, "", None, None),
    (mp.STARTER_PLACEHOLDER_ID, ", harness: cursor", True, False),
    (mp.STARTER_PLACEHOLDER_ID, ", channels: {cli: run.sh}", True, False),
    ("our-own-model", "", False, False),
    ("our-own-model", ", harness: cursor", True, False),
    ("claude-xyz", "", False, False),         # ratio 0.56 against claude-opus-5-5
    ("claude-opzzzzzz", "", False, True),     # ratio 0.6, the cutoff
    ("claude-opus-x", "", False, True),
    ("claude-opus-x", ", harness_model: unknown-zz", False, True),    # neither matches
    ("our-own-model", ", harness_model: claude-opus-5-5", None, None),  # api_id
])
def test_roster_profile_gaps_reports_and_hints_by_id_and_launchability(
        tmp_path: Path, mid: str, extra: str, launchable: bool | None, closest: bool | None) -> None:
    repo = make_profile_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(ROSTER + f"  - {{id: {mid}, family: x, roles: [executor]{extra}}}\n")

    gaps = [g for g in mp.roster_profile_gaps(repo) if _gap(mid) in g[1]]

    if launchable is None:
        assert gaps == []
        return
    [(got_launchable, msg)] = gaps
    assert got_launchable is launchable
    assert (CLOSEST in msg) is closest
    assert (NO_CLOSE_NAME in msg) is not closest
    assert closest or "claude-opus-5-5" not in msg


def test_the_template_roster_uses_the_placeholder_id_nothing_can_launch() -> None:
    template = TEMPLATE_PROFILES.parent / "roadmap" / "orchestration.yaml"
    roster = yaml.safe_load(template.read_text(encoding="utf-8"))["roster"]
    [entry] = [e for e in roster if e["id"] == mp.STARTER_PLACEHOLDER_ID]
    assert not {"harness", "channels"} & set(entry)


def test_shipped_profiles_alias_every_cursor_id_that_extends_their_api_id() -> None:
    """Each id in the shipped Cursor capture that is a profile's api_id or file name plus a suffix
    (``cursor-`` prefix aside) is one of that profile's aliases, so a roster entry using it gets its notes."""
    profiles = mp.list_profiles(TEMPLATE_PROFILES.parent)
    capture = (TEMPLATE_PROFILES / "harness-captures" / "cursor" / "inventory-models.txt").read_text()
    missing = []
    for cid in (ln.split(" - ")[0].strip() for ln in capture.splitlines() if " - " in ln):
        bare = cid.removeprefix("cursor-")
        owners = [(len(n), p) for p in profiles for n in {str(p.data.get("api_id")), p.path.stem}
                  if n != "unknown" and bare.startswith(n + "-")]
        if owners and not max(owners, key=lambda o: o[0])[1].for_id(cid):
            missing.append(cid)
    assert missing == []
    assert mp.closest_profile("claude-opus-5.5", profiles).path.name == "claude-opus-5-5.md"


def test_only_composer_2_5_records_guidance_bypass() -> None:
    """M21.44: the shipped composer-2.5 profile records the §9 finding; no other does (composer-2 included)."""
    flagged = {p.path.name: p.data["guidance_bypass_observed"] for p in mp.list_profiles(TEMPLATE_PROFILES.parent)
               if "guidance_bypass_observed" in p.data}
    assert list(flagged) == ["composer-2.5.md"]
    record = flagged["composer-2.5.md"]
    assert (str(record["date"]), record["harness"]) == ("2026-11-06", "cursor")
    assert all(case in record["evidence"] for case in ("CR1", "CR3", "CR5", "2 of 5"))


def test_the_refusal_needs_only_config_entry_and_profile() -> None:
    """A2's three-argument form, with no repository: the bundled flags and the profile's own decide, and ``config``
    stands for the committed roster."""
    def config(opt_in: bool) -> dict:
        return {"policy": {"signed_reviews": True},
                "roster": [{"id": "w", "allow_guidance_bypass_model": True}] if opt_in else []}
    flagged, plain = {"id": "w", "harness_model": "composer-2.5"}, {"id": "w", "harness_model": "composer-2"}
    assert guidance_bypass_refusal(config(False), plain, None) is None
    assert "w (model composer-2.5) is excluded from executor and reviewer roles" in guidance_bypass_refusal(
        config(False), flagged, None)
    assert guidance_bypass_refusal(config(True), flagged, None) is None
    assert guidance_bypass_refusal({"policy": {}, "roster": []}, flagged, None) is None


OPUS_REL = "model-profiles/anthropic-claude/claude-opus-5-5.md"
NOTES = "## Model notes (Claude Opus 5.5"


def _harness_model_repo(tmp_path: Path, entries: str, cli: str | None = None) -> Path:
    """M22.66: a profile repo whose opus profile runs ``cli``, with a second profile ``b-model`` (no aliases) that
    sorts before it, and ``entries`` added to the roster, all landed on ``dev``."""
    repo = make_profile_repo(tmp_path)
    opus = repo / OPUS_REL
    text = opus.read_text()   # its aliases include claude-opus-5-5-high
    opus.write_text(text if cli is None else text.replace(shipped_anthropic_opus_cli_yaml_line(), f"  cli: {cli}"))
    other = repo / "model-profiles" / "aaa-vendor" / "b-model.md"
    other.parent.mkdir()
    other.write_text(re.sub(r"api_id: claude-opus-5-5\naliases:\n(  - .*\n)*", "api_id: b-model\n", text, count=1))
    (repo / "roadmap" / "orchestration.yaml").write_text(ROSTER + entries)
    git(repo, "add", "model-profiles")
    commit_profile(repo)
    return repo


@pytest.mark.parametrize("key", ["claude-opus-5-5", "claude-opus-5-5-high"])
def test_an_entry_matches_its_profile_by_harness_model(tmp_path: Path, capsys, key: str) -> None:
    """api_id and alias rows: no warning, and the prompt holds the profile's rules; the pinned row: with the
    working-tree copy gone, the prompt still reads the profile from the integration branch."""
    repo = _harness_model_repo(
        tmp_path, f"  - {{id: my-opus, family: anthropic, harness: cursor, harness_model: {key}, roles: [executor]}}\n")
    capsys.readouterr()
    validate_at(repo, no_overlap_warn=True)
    cap = capsys.readouterr()
    assert "'my-opus'" not in cap.out + cap.err
    text, prof, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="my-opus")
    assert err is None and NOTES in text and "Set effort explicitly" in text and prof.api_id == key
    (repo / OPUS_REL).unlink()
    assert mp.profile_for_entry(repo, {"id": "my-opus", "harness_model": key}) is None
    text, prof, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="my-opus")
    assert err is None and NOTES in text and prof.ok


@pytest.mark.parametrize("entry, name", [
    ({"id": "claude-opus-5-5", "harness_model": "b-model"}, "claude-opus-5-5.md"),   # id wins, B sorts first
    ({"id": "no-such", "harness_model": "b-model"}, "b-model.md"),
    ({"id": "no-such", "harness_model": "  "}, None),   # blank is no key
    ({"id": "no-such"}, None),
    ({"id": "opus", "profile": OPUS_REL, "harness_model": "b-model"}, "claude-opus-5-5.md"),   # explicit
])
def test_an_id_match_beats_a_harness_model_match_on_both_lookups(tmp_path: Path, entry: dict, name: str | None) -> None:
    repo = _harness_model_repo(tmp_path, "")
    assert [p.path.name for p in mp.list_profiles(repo)] == ["b-model.md", "claude-opus-5-5.md"]
    for found in (mp.profile_for_entry(repo, entry), pinned_profile_for_entry(repo, entry)):
        assert (found.path.name if found else None) == name


@pytest.mark.parametrize("key", ["claude-opus-5-5", "claude-opus-5-5-high"])
def test_a_drifted_profile_matched_by_harness_model_is_refused_and_runs_nothing(
        tmp_path: Path, capsys, key: str) -> None:
    repo = _harness_model_repo(
        tmp_path, f"  - {{id: my-opus, family: anthropic, harness_model: {key}, roles: [executor]}}\n",
        cli="touch ran.txt; cat {prompt}")
    (repo / OPUS_REL).write_text((repo / OPUS_REL).read_text().replace("touch ran.txt", "touch other.txt"))
    found = pinned_profile_for_entry(repo, {"id": "my-opus", "harness_model": key})
    assert found is not None and not found.ok
    assert "differs from the copy on the integration branch" in found.errors[0]
    assert run_main(role_prompt, "M1.1", "--model", "my-opus", "--role", "executor", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 1
    assert "differs from the copy on the integration branch" in capsys.readouterr().err
    assert not (repo / "ran.txt").exists() and not (repo / "other.txt").exists()
