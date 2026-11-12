"""The LLM client shared by review-node and the PM GUI's providers.

One place builds the provider client from the environment (Azure OpenAI,
Anthropic, or OpenAI and OpenAI-compatible endpoints), sends a chat through the
throughput gate, and redacts provider errors. Callers are the ones principle 4
allows: ``review_node`` (advisory planning review), the GUI's Test LLM button
and the brainstorm panel's chat.

Tests replace :func:`make_client` to supply a fake provider client; every
request goes through it.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from specy_road.errors import SpecyError, inherited_init

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class ReviewError(SpecyError):
    """LLM review failed (missing config, missing package, or API error)."""

    __init__ = inherited_init


def normalize_azure_endpoint(raw: str) -> str:
    """
    Reduce pasted portal URLs to the resource root ``https://<resource>.openai.azure.com``.

    Drops path, query, and fragment so the OpenAI SDK builds
    ``.../openai/deployments/...`` without duplicated path segments.
    """
    s = raw.strip()
    if not s:
        return s
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    scheme = p.scheme or "https"
    netloc = p.netloc
    if not netloc:
        return raw.strip()
    return f"{scheme}://{netloc}".rstrip("/")


def _env_first_nonempty(specy_key: str, azure_aliases: tuple[str, ...]) -> str:
    v = os.environ.get(specy_key, "").strip()
    if v:
        return v
    for k in azure_aliases:
        t = os.environ.get(k, "").strip()
        if t:
            return t
    return ""


def azure_openai_settings_from_env() -> tuple[str, str, str, str]:
    """(endpoint_raw, api_key, deployment, api_version); SPECY_ vars win over AZURE_*."""
    ep = _env_first_nonempty(
        "SPECY_ROAD_AZURE_OPENAI_ENDPOINT",
        ("AZURE_OPENAI_ENDPOINT",),
    )
    key = _env_first_nonempty(
        "SPECY_ROAD_AZURE_OPENAI_API_KEY",
        ("AZURE_OPENAI_API_KEY",),
    )
    dep = _env_first_nonempty(
        "SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT",
        ("AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_DEPLOYMENT"),
    )
    ver = (
        os.environ.get("SPECY_ROAD_OPENAI_API_VERSION", "").strip()
        or os.environ.get("AZURE_OPENAI_API_VERSION", "").strip()
        or "2024-02-15-preview"
    )
    return ep, key, dep, ver


def _azure_openai_client_timeout() -> object | None:
    """Long read timeout for Azure chat (default 300s); ``None`` if httpx missing."""
    try:
        import httpx
    except ImportError:
        return None
    raw = os.environ.get("SPECY_ROAD_AZURE_OPENAI_TIMEOUT_S", "").strip()
    try:
        total = float(raw) if raw else 300.0
    except ValueError:
        total = 300.0
    total = max(total, 1.0)
    return httpx.Timeout(total, connect=10.0)


def _azure_chat_completion_extra_params() -> dict[str, int]:
    """
    Optional ``max_completion_tokens`` for newer Azure chat deployments.

    Set ``SPECY_ROAD_AZURE_CHAT_USE_MAX_COMPLETION_TOKENS`` to ``1``/``true``
    and ``SPECY_ROAD_AZURE_MAX_COMPLETION_TOKENS`` (or ``AZURE_OPENAI_MAX_TOKENS``)
    to a positive integer. Omit both ``max_tokens`` and ``max_completion_tokens``
    when the flag is unset (provider defaults).
    """
    flag = os.environ.get(
        "SPECY_ROAD_AZURE_CHAT_USE_MAX_COMPLETION_TOKENS",
        "",
    ).strip().lower() in ("1", "true", "yes")
    if not flag:
        return {}
    raw = (
        os.environ.get("SPECY_ROAD_AZURE_MAX_COMPLETION_TOKENS", "").strip()
        or os.environ.get("AZURE_OPENAI_MAX_TOKENS", "").strip()
    )
    if not raw:
        raise ReviewError(
            "SPECY_ROAD_AZURE_CHAT_USE_MAX_COMPLETION_TOKENS is enabled but "
            "SPECY_ROAD_AZURE_MAX_COMPLETION_TOKENS (or AZURE_OPENAI_MAX_TOKENS) "
            "is not set.",
        )
    try:
        n = int(raw)
    except ValueError as e:
        raise ReviewError(
            f"SPECY_ROAD_AZURE_MAX_COMPLETION_TOKENS must be an integer, got {raw!r}",
        ) from e
    if n < 1:
        raise ReviewError("SPECY_ROAD_AZURE_MAX_COMPLETION_TOKENS must be at least 1")
    return {"max_completion_tokens": n}


def _safe_error_message(exc: BaseException) -> str:
    """Trim provider errors; redact obvious secret-like substrings."""
    msg = str(exc).strip()
    msg = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", msg)
    msg = re.sub(
        r"(api[_-]?key|apikey)\s*[:=]\s*\S+",
        r"\1: [REDACTED]",
        msg,
        flags=re.IGNORECASE,
    )
    if len(msg) > 400:
        msg = msg[:400] + "…"
    return msg or type(exc).__name__


def openai_chat_completions_create(client: object, **kwargs: object) -> object:
    """``client.chat.completions.create`` behind the RPM/TPM gate, errors redacted."""
    from specy_road.bundled_scripts.llm_throughput import (
        ThroughputExceeded,
        estimate_openai_chat_request_tokens,
        get_openai_chat_throughput_gate,
        parse_openai_chat_throughput_limits,
    )

    try:
        rpm, tpm = parse_openai_chat_throughput_limits()
    except ValueError as e:
        raise ReviewError(str(e)) from e
    throttled = rpm is not None or tpm is not None
    if throttled:
        est = estimate_openai_chat_request_tokens(**kwargs)
        try:
            get_openai_chat_throughput_gate().reserve(
                rpm_max=rpm,
                tpm_max=tpm,
                token_estimate=est,
            )
        except ThroughputExceeded as e:
            raise ReviewError(str(e)) from e
    try:
        resp = client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
    except ReviewError:
        raise
    except Exception as e:
        raise ReviewError(_safe_error_message(e)) from e
    if throttled:
        usage = getattr(resp, "usage", None)
        total = getattr(usage, "total_tokens", None) if usage is not None else None
        get_openai_chat_throughput_gate().adjust_last_reservation(
            int(total) if total is not None else None,
        )
    return resp


def _chat_completion_message_content(resp: object) -> str:
    choices = getattr(resp, "choices", None)
    if not choices:
        raise ReviewError("LLM returned no choices (empty completion).")
    ch0 = choices[0]
    message = getattr(ch0, "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if content is None:
        raise ReviewError("LLM returned no message content.")
    return str(content)


def _azure_deployment_for_request() -> str:
    d = _env_first_nonempty(
        "SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT",
        ("AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_DEPLOYMENT"),
    )
    if not d:
        raise ReviewError(
            "Azure deployment is not configured "
            "(SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT_NAME).",
        )
    return d


def make_client():
    """The provider client the environment selects: Azure, then Anthropic, then OpenAI."""
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as e:
        raise ReviewError(
            "openai package not installed. Run: pip install "
            "'specy-road[review]' or 'specy-road[gui]'",
        ) from e

    ep_raw, key, dep, ver = azure_openai_settings_from_env()
    if ep_raw.strip():
        ep = normalize_azure_endpoint(ep_raw)
        if not key or not dep:
            raise ReviewError(
                "Azure mode needs API key and deployment name "
                "(SPECY_ROAD_AZURE_OPENAI_API_KEY / SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT "
                "or AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT_NAME; see "
                "docs/pm-workflow.md).",
            )
        client_kw: dict[str, object] = {
            "azure_endpoint": ep,
            "api_key": key,
            "api_version": ver,
        }
        t = _azure_openai_client_timeout()
        if t is not None:
            client_kw["timeout"] = t
        return AzureOpenAI(**client_kw)

    ak = os.environ.get("SPECY_ROAD_ANTHROPIC_API_KEY", "").strip()
    if ak:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ReviewError(
                "anthropic package not installed. Run: pip install "
                "'specy-road[review]' or 'specy-road[gui-next]'",
            ) from e
        return Anthropic(api_key=ak)

    key = os.environ.get("SPECY_ROAD_OPENAI_API_KEY", "").strip()
    if not key:
        raise ReviewError(
            "set SPECY_ROAD_OPENAI_API_KEY, SPECY_ROAD_ANTHROPIC_API_KEY, "
            "or Azure variables (see docs/pm-workflow.md)",
        )
    base = os.environ.get("SPECY_ROAD_OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=key, base_url=base)


def _anthropic_text(resp: object) -> str:
    parts: list[str] = []
    for block in getattr(resp, "content", ()) or ():
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def anthropic_max_completion_tokens() -> int:
    """
    Anthropic's Messages API requires ``max_tokens`` (completion budget).

    The toolkit does not choose a default cap; set
    ``SPECY_ROAD_ANTHROPIC_MAX_TOKENS`` to the maximum completion tokens you
    want per request (see Anthropic docs for model limits).
    """
    raw = os.environ.get("SPECY_ROAD_ANTHROPIC_MAX_TOKENS", "").strip()
    if not raw:
        raise ReviewError(
            "Anthropic requires SPECY_ROAD_ANTHROPIC_MAX_TOKENS (completion "
            "token budget for the Messages API). Set it in the environment or "
            "your shell profile; see docs/pm-workflow.md.",
        )
    try:
        n = int(raw)
    except ValueError as e:
        raise ReviewError(
            f"SPECY_ROAD_ANTHROPIC_MAX_TOKENS must be an integer, got {raw!r}",
        ) from e
    if n < 1:
        raise ReviewError("SPECY_ROAD_ANTHROPIC_MAX_TOKENS must be at least 1")
    return n


def _complete_anthropic(
    client: object,
    messages: list[dict],
    system_prompt: str | None,
) -> str:
    kwargs: dict[str, object] = {
        "model": os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
        "max_tokens": anthropic_max_completion_tokens(),
        "messages": messages,
    }
    if system_prompt is not None:
        kwargs["system"] = system_prompt
    try:
        resp = client.messages.create(**kwargs)  # type: ignore[union-attr]
    except ReviewError:
        raise
    except Exception as e:
        raise ReviewError(_safe_error_message(e)) from e
    return _anthropic_text(resp)


def complete(messages: list[dict], *, system_prompt: str | None = None) -> str:
    """One model call over ``messages`` (user/assistant turns); the reply text.

    The client comes from :func:`make_client`. ``system_prompt`` of ``None``
    sends no system instruction. Configuration and provider failures raise
    :class:`ReviewError` with secret-like text redacted.
    """
    client = make_client()
    if type(client).__module__.startswith("anthropic"):
        return _complete_anthropic(client, messages, system_prompt)

    from openai import AzureOpenAI

    if isinstance(client, AzureOpenAI):
        model = _azure_deployment_for_request()
        extra = _azure_chat_completion_extra_params()
    else:
        model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        extra = {}
    system = [] if system_prompt is None else [{"role": "system", "content": system_prompt}]
    resp = openai_chat_completions_create(
        client,
        model=model,
        messages=[*system, *messages],
        **extra,
    )
    return _chat_completion_message_content(resp) or ""


def ping_llm() -> None:
    """Minimal request to verify credentials (used by Test LLM in GUIs)."""
    complete([{"role": "user", "content": "ping"}])
