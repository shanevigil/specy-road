"""M22.40: a Cursor display name with a context size and an effort matches the catalog id it names."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.model_names import same_model
from specy_road.model_profiles import Profile
from specy_road.review_model_check import check
from specy_road.worker_models import mismatch_note


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


# Every effort the comparison treats as identity, including the ones a shipped profile lists beside high.
_SOL = Profile(Path("gpt-5.6-sol.md"), {
    "api_id": "gpt-5.6-sol", "model": "GPT-5.6 Sol",
    "aliases": [
        "gpt-5.6-sol-none", "gpt-5.6-sol-minimal", "gpt-5.6-sol-low", "gpt-5.6-sol-medium",
        "gpt-5.6-sol-high", "gpt-5.6-sol-high-fast", "gpt-5.6-sol-xhigh", "gpt-5.6-sol-max",
    ],
})
_GROK = Profile(Path("grok-4.7.md"), {
    "api_id": "grok-4.7", "model": "Grok 4.7",
    "aliases": ["grok-4.7-low", "grok-4.7-medium", "grok-4.7-high", "grok-4.7-high-fast", "grok-4.7-xhigh"],
})


@pytest.mark.parametrize(("reported", "slug", "profile", "same"), [
    ("GPT-5.6 Sol 1M Medium", "gpt-5.6-sol-high", _SOL, False),
    ("GPT-5.6 Sol 300K Low", "gpt-5.6-sol-high", _SOL, False),
    ("GPT-5.6 Sol 1M Max", "gpt-5.6-sol-high", _SOL, False),
    ("GPT-5.6 Sol 1M None", "gpt-5.6-sol-high", _SOL, False),
    ("GPT-5.6 Sol 1M Minimal", "gpt-5.6-sol-high", _SOL, False),
    ("GPT-5.6 Sol 1M Extra High", "gpt-5.6-sol-high", _SOL, False),
    ("GPT-5.6 Sol 1M High Fast", "gpt-5.6-sol-high", _SOL, False),
    ("Grok 4.7 1M Low", "grok-4.7-high", _GROK, False),
    ("Grok 4.7 300K Medium", "grok-4.7-high", _GROK, False),
    ("GPT-5.6 Sol 1M High", "gpt-5.6-sol-high", _SOL, True),
    ("GPT-5.6 Sol 1M Extra High", "gpt-5.6-sol-xhigh", _SOL, True),
    ("GPT-5.6 Sol 1M High Fast", "gpt-5.6-sol-high-fast", _SOL, True),
    ("Grok 4.7 300K High", "grok-4.7-high", _GROK, True),
])
def test_a_profile_alias_for_another_effort_does_not_match(
        reported: str, slug: str, profile: Profile, same: bool) -> None:
    """A High request keeps its effort when the profile lists every effort. Medium with a context size does not match."""
    assert same_model(reported, slug, slug, profile) is same
    entry = {"id": slug, "harness_model": slug}
    assert check(reported, entry, profile) == ("match" if same else "mismatch")
    assert (mismatch_note({"requested_model": slug, "observed_model": reported}, slug, profile) == "") is same
