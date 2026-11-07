"""M22.40: a Cursor display name with a context size and an effort matches the catalog id it names."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.model_names import same_model
from specy_road.model_profiles import Profile


@pytest.mark.parametrize(("reported", "slug", "same"), [
    ("Claude Opus 5.5 300K High", "claude-opus-5-5-high", True),
    ("Claude Opus 5.5 1M High", "claude-opus-5-5-high", True),
    ("GPT-5.6 Sol 300K High", "gpt-5.6-sol-high", True),
    ("GPT-5.6 Sol 1M High", "gpt-5.6-sol-high", True),
    ("Grok 4.7 300K High", "grok-4.7-high", True),
    ("Grok 4.7 1M High", "grok-4.7-high", True),
    ("Claude Opus 5.5 300K Extra High", "claude-opus-5-5-xhigh", True),
    ("Claude Opus 5.5 300K Medium", "claude-opus-5-5-high", False),   # a different effort
    ("Claude Opus 5.5 300K Extra High", "claude-opus-5-5-high", False),
    ("Grok 4.7 1M High", "grok-4.6-high", False),   # a different model
    ("GPT-5.6 Sol 1M High", "claude-opus-5-5-high", False),
])
def test_cursor_display_name_matches_the_catalog_id_it_names(reported: str, slug: str, same: bool) -> None:
    assert same_model(reported, slug) is same


def test_a_context_size_without_an_effort_word_does_not_match_another_effort() -> None:
    """``GPT-5.6 Sol 1M`` is the medium display name. It must not match high through the profile's model name."""
    prof = Profile(Path("gpt-5.6-sol.md"), {
        "api_id": "gpt-5.6-sol", "model": "GPT-5.6 Sol",
        "aliases": ["gpt-5.6-sol-high", "gpt-5.6-sol-medium"],
    })
    assert same_model("GPT-5.6 Sol 1M High", "gpt-5.6-sol-high", profile=prof) is True
    assert same_model("GPT-5.6 Sol 1M", "gpt-5.6-sol-high", profile=prof) is False
