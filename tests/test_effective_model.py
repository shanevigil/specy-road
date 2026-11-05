"""M15.3 root-cause round: one effective model per roster entry (``review_model_check.resolve_effective_model``),
which ``prompt`` shows and launches with and the harness-reported model is compared against, and nothing else."""

from __future__ import annotations

import pytest

from tests.test_models_and_prompt import OPUS

from specy_road.bundled_scripts.role_prompt_cli import model_problem
from specy_road.model_profiles import load_profile
from specy_road.review_model_check import check, resolve_effective_model


# --- One effective model per roster entry: resolution and comparison (root-cause round) ----------------------------

def _profile(kind: str):
    """``None``, the shipped Opus profile, or a copy whose ``api_id`` is the ``unknown`` sentinel."""
    if kind == "none":
        return None
    prof = load_profile(OPUS)
    if kind == "unknown":
        prof.data["api_id"] = "unknown"
    return prof


@pytest.mark.parametrize("entry, profile, effective, reported, state", [
    # no harness_model: the profile's api_id, whose own names count
    ({"id": "opus"}, "opus", "claude-opus-5-5", "Claude Opus 5.5", "match"),
    ({"id": "opus"}, "opus", "claude-opus-5-5", "gpt-6.1-sol", "mismatch"),
    ({"id": "opus"}, "opus", "claude-opus-5-5", "opus", "mismatch"),                 # the roster label is no model
    # harness_model selects another model: only it counts, never the profile's identities
    ({"id": "opus", "harness_model": "gpt-6.1-sol"}, "opus", "gpt-6.1-sol", "claude-opus-5-5", "mismatch"),
    ({"id": "opus", "harness_model": "gpt-6.1-sol"}, "opus", "gpt-6.1-sol", "Claude Opus 5.5", "mismatch"),
    ({"id": "opus", "harness_model": "gpt-6.1-sol"}, "opus", "gpt-6.1-sol", "GPT 6.1 Sol", "match"),
    # harness_model naming the profile's own model keeps its names
    ({"id": "opus", "harness_model": "claude-opus-5-5"}, "unknown", "claude-opus-5-5", "Claude Opus 5.5", "match"),
    # no profile: harness_model, else the roster id
    ({"id": "review-label", "harness_model": "gpt-6.1-sol"}, "none", "gpt-6.1-sol", "review-label", "mismatch"),
    ({"id": "review-label", "harness_model": "gpt-6.1-sol"}, "none", "gpt-6.1-sol", "gpt-6.1-sol", "match"),
    ({"id": "opus"}, "none", "opus", "opus", "match"),
    ({"id": "opus"}, "none", "opus", "claude-opus-5-5", "mismatch"),
    ({"id": "opus", "harness_model": ""}, "opus", "claude-opus-5-5", "claude-opus-5-5", "match"),  # empty: unset
    # the unknown sentinel, from any step, resolves to no model: nothing matches it
    ({"id": "opus", "harness_model": "unknown"}, "opus", None, "claude-opus-5-5", "mismatch"),
    ({"id": "opus", "harness_model": "Unknown"}, "none", None, "unknown", "mismatch"),
    ({"id": "opus"}, "unknown", None, "claude-opus-5-5", "mismatch"),
    ({"id": "unknown"}, "none", None, "unknown", "mismatch"),
    # nothing reported: a warning whatever the entry
    ({"id": "opus"}, "opus", "claude-opus-5-5", None, "unreported"),
    ({"id": "unknown"}, "none", None, None, "unreported"),
])
def test_one_effective_model_resolves_and_is_the_only_thing_compared(entry: dict, profile: str, effective: str | None,
                                                                    reported: str | None, state: str) -> None:
    prof = _profile(profile)
    assert resolve_effective_model(entry, prof) == effective
    resolved, err = model_problem(prof, entry)                # what the preview and the launch use
    assert resolved == effective and bool(err) is (effective is None)
    assert check(reported, entry, prof) == state
