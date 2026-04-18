"""Tests for llm_throughput (OpenAI chat RPM/TPM sliding window)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

import llm_throughput
import review_node


@pytest.fixture(autouse=True)
def _reset_gate() -> None:
    llm_throughput.reset_openai_chat_throughput_gate_for_tests()
    yield
    llm_throughput.reset_openai_chat_throughput_gate_for_tests()


def test_parse_limits_specy_wins_over_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_LLM_RPM_MAX", "10")
    monkeypatch.setenv("AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE", "99")
    monkeypatch.setenv("SPECY_ROAD_LLM_TPM_MAX", "1000")
    monkeypatch.setenv("AZURE_OPENAI_MAX_TOKENS_PER_MINUTE", "999999")
    assert llm_throughput.parse_openai_chat_throughput_limits() == (10, 1000)


def test_parse_limits_azure_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECY_ROAD_LLM_RPM_MAX", raising=False)
    monkeypatch.delenv("SPECY_ROAD_LLM_TPM_MAX", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE", "5")
    monkeypatch.setenv("AZURE_OPENAI_MAX_TOKENS_PER_MINUTE", "8000")
    assert llm_throughput.parse_openai_chat_throughput_limits() == (5, 8000)


def test_parse_limits_zero_means_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_LLM_RPM_MAX", "0")
    monkeypatch.setenv("SPECY_ROAD_LLM_TPM_MAX", "0")
    assert llm_throughput.parse_openai_chat_throughput_limits() == (None, None)


def test_parse_limits_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_LLM_RPM_MAX", "nope")
    with pytest.raises(ValueError, match="SPECY_ROAD_LLM_RPM_MAX"):
        llm_throughput.parse_openai_chat_throughput_limits()


def test_gate_rpm_blocks_fourth_in_window(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"t": 0.0}

    def fake_now() -> float:
        return clock["t"]

    g = llm_throughput.OpenAiChatThroughputGate(now_fn=fake_now, window_seconds=60.0)
    g.reserve(rpm_max=3, tpm_max=None, token_estimate=1)
    g.reserve(rpm_max=3, tpm_max=None, token_estimate=1)
    g.reserve(rpm_max=3, tpm_max=None, token_estimate=1)
    with pytest.raises(llm_throughput.ThroughputExceeded, match="RPM"):
        g.reserve(rpm_max=3, tpm_max=None, token_estimate=1)
    clock["t"] = 61.0
    g.reserve(rpm_max=3, tpm_max=None, token_estimate=1)


def test_gate_tpm_blocks_heavy_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"t": 0.0}

    def fake_now() -> float:
        return clock["t"]

    g = llm_throughput.OpenAiChatThroughputGate(now_fn=fake_now, window_seconds=60.0)
    g.reserve(rpm_max=None, tpm_max=100, token_estimate=60)
    with pytest.raises(llm_throughput.ThroughputExceeded, match="TPM"):
        g.reserve(rpm_max=None, tpm_max=100, token_estimate=50)


def test_gate_adjust_last_reservation() -> None:
    clock = {"t": 0.0}

    def fake_now() -> float:
        return clock["t"]

    g = llm_throughput.OpenAiChatThroughputGate(now_fn=fake_now, window_seconds=60.0)
    g.reserve(rpm_max=10, tpm_max=500, token_estimate=400)
    g.adjust_last_reservation(120)
    with pytest.raises(llm_throughput.ThroughputExceeded, match="TPM"):
        g.reserve(rpm_max=None, tpm_max=500, token_estimate=400)


def test_estimate_tokens_min_one() -> None:
    n = llm_throughput.estimate_openai_chat_request_tokens(model="x", messages=[])
    assert n >= 1


def test_openai_chat_completions_create_respects_throughput(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_LLM_RPM_MAX", "2")
    monkeypatch.setenv("SPECY_ROAD_LLM_TPM_MAX", "1000000")
    calls = {"n": 0}

    class Msg:
        content = "hi"

    class Choice:
        message = Msg()

    class Usage:
        total_tokens = 42

    class Resp:
        choices = [Choice()]
        usage = Usage()

    class Completions:
        def create(self, **_k: object) -> Resp:
            calls["n"] += 1
            return Resp()

    class Chat:
        completions = Completions()

    client = MagicMock()
    client.chat = Chat()

    review_node._openai_chat_completions_create(client, model="m", messages=[])
    review_node._openai_chat_completions_create(client, model="m", messages=[])
    assert calls["n"] == 2
    with pytest.raises(review_node.ReviewError, match="RPM"):
        review_node._openai_chat_completions_create(client, model="m", messages=[])


def test_apply_llm_env_azure_throughput_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_MAX_TOKENS_PER_MINUTE", raising=False)
    import roadmap_gui_lib as gl

    gl.apply_llm_env_from_settings(
        {
            "backend": "azure",
            "azure_endpoint": "https://x.openai.azure.com",
            "azure_api_key": "k",
            "azure_deployment": "d",
            "azure_api_version": "",
            "azure_max_requests_per_minute": "",
            "azure_max_tokens_per_minute": "",
        },
    )
    assert os.environ["AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE"] == "250"
    assert os.environ["AZURE_OPENAI_MAX_TOKENS_PER_MINUTE"] == "250000"


def test_apply_llm_env_azure_throughput_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import roadmap_gui_lib as gl

    gl.apply_llm_env_from_settings(
        {
            "backend": "azure",
            "azure_endpoint": "https://x.openai.azure.com",
            "azure_api_key": "k",
            "azure_deployment": "d",
            "azure_max_requests_per_minute": "12",
            "azure_max_tokens_per_minute": "34000",
        },
    )
    assert os.environ["AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE"] == "12"
    assert os.environ["AZURE_OPENAI_MAX_TOKENS_PER_MINUTE"] == "34000"


def test_apply_llm_env_openai_clears_azure_throughput_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import roadmap_gui_lib as gl

    monkeypatch.setenv("AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE", "1")
    monkeypatch.setenv("AZURE_OPENAI_MAX_TOKENS_PER_MINUTE", "2")
    gl.apply_llm_env_from_settings(
        {
            "backend": "openai",
            "openai_api_key": "sk-test",
            "openai_model": "gpt-4o-mini",
        },
    )
    assert "AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE" not in os.environ
    assert "AZURE_OPENAI_MAX_TOKENS_PER_MINUTE" not in os.environ
