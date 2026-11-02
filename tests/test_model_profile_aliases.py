"""M11.26: effort-suffixed Cursor ids match profiles; models list reports unmatched roster ids."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road import model_profiles as mp
from specy_road.bundled_scripts import models_cli

from tests.test_models_and_prompt import TEMPLATE_PROFILES, make_profile_repo, run_main


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
    assert "roster id(s) match no profile" in text and "  human\n" in text and "  sol\n" in text
    assert run_main(models_cli, "models", "list", "--json", "--repo-root", str(repo)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["unmatched_roster_ids"] == ["human", "sol"]
    rows = {r["id"]: r for r in out["roster"]}
    assert rows["sol"]["profile"] is None
