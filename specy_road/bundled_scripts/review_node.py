#!/usr/bin/env python3
"""Advisory LLM review of a roadmap node (brief + constraints + cited docs)."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

from generate_brief import index as make_index, render_brief
from planning_sheet_bootstrap import (
    feature_sheet_structure_instruction_for_llm,
    gate_sheet_structure_instruction_for_llm,
    planning_review_expected_shape_block,
)
from roadmap_load import load_roadmap
from specy_road.git_subprocess import git_ok
from specy_road.runtime_paths import default_user_repo_root

# Deterministic `shared/` index for LLM review: bounded reads, sorted paths.
_TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".mdx",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".csv",
    },
)
_SHARED_CATALOG_SAMPLE_BYTES = 2048
_SHARED_CATALOG_MAX_BLURB_CHARS = 120
_SHARED_CATALOG_MAX_FILES = 400
_SHARED_CATALOG_MAX_CHARS = 28_000
_SHARED_CATALOG_CACHE_MAX_ENTRIES = 32

_SHARED_CATALOG_CACHE: OrderedDict[str, str] = OrderedDict()
_SHARED_CATALOG_CACHE_LOCK = threading.Lock()

ALLOWED_PREFIXES = ("shared/", "docs/", "specs/", "adr/")


class ReviewError(Exception):
    """LLM review failed (missing config, missing package, or API error)."""


def _feature_sheet_system_prompt() -> str:
    """LLM system prompt for task/milestone/phase-style feature sheets."""
    return (
        "You revise the Markdown feature sheet for one roadmap item.\n\n"
        "Output rules (strict):\n"
        "- Return ONLY the full revised feature sheet as Markdown. No preamble, "
        "title line, or closing commentary.\n"
        "- Do not wrap the document in a fenced code block.\n"
        "- Be concise: short paragraphs, tight bullets, minimal words per line.\n"
        "- "
        + feature_sheet_structure_instruction_for_llm()
        + "\n"
        "- Do not repeat the roadmap node id, display id, title, or node_key in "
        "the body—they belong in the roadmap JSON and filename.\n"
        "- Do not duplicate roadmap structure in prose: remove or rewrite "
        "sentences that name other milestones by display id (e.g. M6, M9.1), "
        "narrate parent/child relationships, or use phrases like \"gated on\" or "
        "\"blocked by\" a roadmap item—dependencies and ordering live in the graph "
        "and brief. Intent and Approach should describe what to build and how, "
        "not restate the dependency list.\n"
        "- Keep legitimate technical prerequisites (e.g. requires a shipped API, "
        "after a DB migration) when they are not the same as roadmap milestone "
        "references.\n"
        "- Do not explain what you changed; the UI will diff against the previous "
        "sheet.\n\n"
        "Context below includes the roadmap brief, a deterministic index of files "
        "under shared/ (one-line descriptions each), constraints, cited contracts, "
        "and the current planning sheet. Treat the shared/ index as optional "
        "references when improving the sheet (including ## References); it does not "
        "replace cited contract bodies. Improve clarity, checklist completeness, "
        "and alignment with constraints and citations—not generic advice."
    )


def _gate_planning_system_prompt() -> str:
    """LLM system prompt for ``type: gate`` planning sheets (PM hold, not dev work)."""
    return (
        "You revise the Markdown planning sheet for one roadmap **gate** "
        "(a PM hold or approval point, not an implementation task).\n\n"
        "Output rules (strict):\n"
        "- Return ONLY the full revised planning sheet as Markdown. No preamble, "
        "title line, or closing commentary.\n"
        "- Do not wrap the document in a fenced code block.\n"
        "- Be concise: short paragraphs, tight bullets, minimal words per line.\n"
        "- "
        + gate_sheet_structure_instruction_for_llm()
        + "\n"
        "- Do not repeat the roadmap node id, display id, title, or node_key in "
        "the body—they belong in the roadmap JSON and filename.\n"
        "- Do not duplicate roadmap structure in prose: remove or rewrite "
        "sentences that name other milestones by display id, narrate parent/child "
        "relationships, or restate dependency edges—those live in the graph and "
        "brief. Focus on why the gate exists, criteria to clear it, decisions, and "
        "resolution—not implementation task lists.\n"
        "- Do not explain what you changed; the UI will diff against the previous "
        "sheet.\n\n"
        "Context below includes the roadmap brief, a deterministic index of files "
        "under shared/ (one-line descriptions each), constraints, cited contracts, "
        "and the current planning sheet. Treat the shared/ index as optional "
        "references when improving the sheet (including ## References); it does not "
        "replace cited contract bodies. Improve clarity and alignment with constraints "
        "and citations—not generic advice."
    )


def system_prompt_for_planning_review(node_type: str | None = None) -> str:
    """System prompt for LLM planning review: gate sheet vs feature sheet."""
    if str(node_type or "").strip().lower() == "gate":
        return _gate_planning_system_prompt()
    return _feature_sheet_system_prompt()


# Default feature-sheet prompt (tests and callers that expect ``SYSTEM_PROMPT``).
SYSTEM_PROMPT = system_prompt_for_planning_review(None)


def _repo_root(ns: argparse.Namespace) -> Path:
    return Path(ns.repo_root).resolve() if ns.repo_root else default_user_repo_root()


def _constraints_text(root: Path) -> str:
    p = root / "constraints" / "README.md"
    if not p.is_file():
        return "_(no constraints/README.md)_"
    return p.read_text(encoding="utf-8", errors="replace")


def _read_file_prefix(path: Path, max_bytes: int) -> bytes:
    try:
        with path.open("rb") as f:
            return f.read(max_bytes)
    except OSError:
        return b""


def _blurb_from_decoded_text(decoded: str) -> str:
    """First ATX heading in sample, else first non-empty line; single line."""
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    chosen = ""
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            rest = line
            while rest.startswith("#"):
                rest = rest[1:]
            title = rest.strip()
            if title:
                chosen = title
                break
            continue
        chosen = line
        break
    if not chosen:
        return "_(empty file)_"
    one = " ".join(chosen.split())
    cap = _SHARED_CATALOG_MAX_BLURB_CHARS
    if len(one) > cap:
        return one[: cap - 1] + "…"
    return one


def _file_blurb_for_catalog(path: Path, size: int) -> str:
    suf = path.suffix.lower()
    if suf not in _TEXT_SUFFIXES:
        label = suf if suf else "file"
        return f"`{size}` bytes ({label})"

    sample = _read_file_prefix(path, _SHARED_CATALOG_SAMPLE_BYTES)
    if b"\x00" in sample:
        return f"`{size}` bytes (binary)"

    decoded = sample.decode("utf-8", errors="replace")
    return _blurb_from_decoded_text(decoded)


def _shared_catalog_cache_clear() -> None:
    """Drop all cached ``shared/`` catalog strings (tests / rare tooling only)."""
    with _SHARED_CATALOG_CACHE_LOCK:
        _SHARED_CATALOG_CACHE.clear()


def _iter_shared_repo_relative_paths(root_res: Path) -> list[str]:
    """Sorted repo-relative POSIX paths for regular files under ``shared/``."""
    shared = root_res / "shared"
    if not shared.is_dir():
        return []
    rel_posix: list[str] = []
    for p in shared.rglob("*"):
        if not p.is_file():
            continue
        try:
            resolved = p.resolve()
            resolved.relative_to(root_res)
        except ValueError:
            continue
        rel_posix.append(resolved.relative_to(root_res).as_posix())
    rel_posix.sort()
    return rel_posix


def _stat_fingerprint_shared_paths(root_res: Path) -> str:
    """Stable hash from path + mtime + size (no file reads)."""
    parts: list[str] = []
    for rel in _iter_shared_repo_relative_paths(root_res):
        p = root_res / rel
        try:
            st = p.stat()
            parts.append(f"{rel}\t{st.st_mtime_ns}\t{st.st_size}")
        except OSError:
            parts.append(f"{rel}\t\t")
    raw = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _shared_catalog_cache_key(root_res: Path) -> str:
    """
    Cache key when ``shared/`` is unchanged.

    Prefer ``git rev-parse HEAD:shared`` when the worktree matches HEAD for
    everything under ``shared/`` (including untracked and ignored — otherwise
    we fall back to a stat fingerprint so the catalog cannot go stale).
    """
    root_key = str(root_res)
    shared = root_res / "shared"
    if not shared.is_dir():
        return f"{root_key}\0missing"

    ok_stat, porcelain = git_ok(
        ["status", "--porcelain=v1", "--ignored", "--", "shared"],
        root_res,
        3.0,
    )
    if ok_stat and not porcelain.strip():
        ok_tree, tree_out = git_ok(["rev-parse", "HEAD:shared"], root_res, 2.0)
        if ok_tree and tree_out.strip():
            tree_id = tree_out.strip().splitlines()[0]
            if tree_id:
                return f"{root_key}\0git:{tree_id}"

    return f"{root_key}\0stat:{_stat_fingerprint_shared_paths(root_res)}"


def _shared_catalog_build(root_res: Path) -> str:
    """
    Sorted recursive listing under ``shared/`` with deterministic one-line blurbs.

    Truncation: if there are more than ``_SHARED_CATALOG_MAX_FILES`` paths, only
    the first paths in sorted order are listed and the rest are counted in a
    footer. If the section would exceed ``_SHARED_CATALOG_MAX_CHARS``, listing
    stops early with a footer (sorted order, earliest paths win).
    """
    shared = root_res / "shared"
    if not shared.is_dir():
        return "_(`shared/` directory not present — nothing to index)_\n"

    rel_posix = _iter_shared_repo_relative_paths(root_res)
    total_files = len(rel_posix)
    if total_files == 0:
        body = "- _(empty `shared/` directory — no files to index)_\n"
    else:
        capped = rel_posix[:_SHARED_CATALOG_MAX_FILES]
        omitted_by_cap = total_files - len(capped)

        lines: list[str] = []
        char_budget = _SHARED_CATALOG_MAX_CHARS
        intro = (
            "Sorted paths under `shared/` (deterministic one-line blurbs from a "
            f"prefix of at most {_SHARED_CATALOG_SAMPLE_BYTES} bytes per text "
            "file). Optional references for this task—not a substitute for cited "
            "snippets.\n\n"
        )
        remaining = char_budget - len(intro)
        truncated_mid_list = False
        for rel in capped:
            abs_path = root_res / rel
            try:
                size = abs_path.stat().st_size
            except OSError:
                size = 0
            blurb = _file_blurb_for_catalog(abs_path, size)
            line = f"- `{rel}` — {blurb}\n"
            if len(line) > remaining:
                truncated_mid_list = True
                break
            lines.append(line)
            remaining -= len(line)

        body = intro + "".join(lines)
        footers: list[str] = []
        if omitted_by_cap > 0:
            footers.append(
                f"\n_({omitted_by_cap} more path(s) under `shared/` omitted; "
                "listing is lexicographic by path.)_\n",
            )
        if truncated_mid_list:
            listed = len(lines)
            footers.append(
                f"\n_(Catalog truncated at ~{_SHARED_CATALOG_MAX_CHARS} characters "
                f"after {listed} path(s); see remaining files in the repo.)_\n",
            )
        body += "".join(footers)

    return body + "\nUse this index only for optional references; cited contracts appear in their own section.\n"


def _shared_catalog(root: Path) -> str:
    """Like :func:`_shared_catalog_build` but memoized while ``shared/`` is stable."""
    root_res = root.resolve()
    key = _shared_catalog_cache_key(root_res)
    with _SHARED_CATALOG_CACHE_LOCK:
        hit = _SHARED_CATALOG_CACHE.get(key)
        if hit is not None:
            _SHARED_CATALOG_CACHE.move_to_end(key)
            return hit

    text = _shared_catalog_build(root_res)

    with _SHARED_CATALOG_CACHE_LOCK:
        _SHARED_CATALOG_CACHE[key] = text
        _SHARED_CATALOG_CACHE.move_to_end(key)
        while len(_SHARED_CATALOG_CACHE) > _SHARED_CATALOG_CACHE_MAX_ENTRIES:
            _SHARED_CATALOG_CACHE.popitem(last=False)
    return text


def _normalize_review_markdown_output(text: str) -> str:
    """Strip accidental ```markdown fences some models wrap around the sheet."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if not lines:
        return t
    first = lines[0].strip()
    if not first.startswith("```"):
        return t
    rest = lines[1:]
    while rest and rest[-1].strip() == "```":
        rest = rest[:-1]
    return "\n".join(rest).strip()


def _feature_sheet_for_prompt(
    root: Path,
    node: dict,
    planning_body: str | None,
) -> str:
    """Current sheet text: live editor wins, else on-disk planning_dir."""
    if planning_body is not None:
        return planning_body
    pd = (node.get("planning_dir") or "").strip()
    if not pd:
        return "_(no planning_dir on this node — save a feature sheet first.)_"
    path = root / pd
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return f"_(planning file not found on disk: `{pd}`)_"


def _cited_snippets(root: Path, node: dict) -> str:
    ac = node.get("agentic_checklist") or {}
    citation = ac.get("contract_citation", "") or ""
    parts: list[str] = []
    root_res = root.resolve()
    for raw in citation.split(";"):
        token = raw.strip()
        if not token:
            continue
        path_part = token.split()[0] if token else ""
        if not any(path_part.startswith(p) for p in ALLOWED_PREFIXES):
            continue
        rel = Path(path_part)
        if rel.is_absolute():
            continue
        target = (root / rel).resolve()
        try:
            target.relative_to(root_res)
        except ValueError:
            parts.append(f"### (skipped path outside repo) `{path_part}`\n")
            continue
        if target.is_file():
            text = target.read_text(encoding="utf-8", errors="replace")
            cap = 12000
            if len(text) > cap:
                text = text[:cap] + "\n\n…(truncated)…"
            parts.append(f"### `{path_part}`\n\n{text}\n")
    if not parts:
        return "_(no readable cited files parsed from contract_citation)_"
    return "\n".join(parts)


def _normalize_azure_endpoint(raw: str) -> str:
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


def _azure_openai_settings_from_env() -> tuple[str, str, str, str]:
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


def _openai_safe_error_message(exc: BaseException) -> str:
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


def _openai_chat_completions_create(client: object, **kwargs: object) -> object:
    from llm_throughput import (
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
        raise ReviewError(_openai_safe_error_message(e)) from e
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


def _make_client():
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as e:
        raise ReviewError(
            "openai package not installed. Run: pip install "
            "'specy-road[review]' or 'specy-road[gui]'",
        ) from e

    ep_raw, key, dep, ver = _azure_openai_settings_from_env()
    if ep_raw.strip():
        ep = _normalize_azure_endpoint(ep_raw)
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


def _anthropic_max_completion_tokens() -> int:
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
    user_content: str,
    *,
    system_prompt: str,
) -> str:
    default_m = "claude-sonnet-4-20250514"
    model = os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL", default_m)
    resp = client.messages.create(  # type: ignore[union-attr]
        model=model,
        max_tokens=_anthropic_max_completion_tokens(),
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return _anthropic_text(resp)


def _complete(
    client,
    user_content: str,
    *,
    system_prompt: str,
) -> str:
    cls_mod = type(client).__module__
    if cls_mod.startswith("anthropic"):
        return _complete_anthropic(client, user_content, system_prompt=system_prompt)

    from openai import AzureOpenAI

    if isinstance(client, AzureOpenAI):
        model = _azure_deployment_for_request()
        extra = _azure_chat_completion_extra_params()
    else:
        model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", "gpt-4o-mini")
        extra = {}
    resp = _openai_chat_completions_create(
        client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        **extra,
    )
    return _chat_completion_message_content(resp) or ""


def ping_llm() -> None:
    """Minimal request to verify credentials (used by Test LLM in GUIs)."""
    client = _make_client()
    cls_mod = type(client).__module__
    if cls_mod.startswith("anthropic"):
        default_m = "claude-sonnet-4-20250514"
        model = os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL", default_m)
        r = client.messages.create(  # type: ignore[union-attr]
            model=model,
            max_tokens=_anthropic_max_completion_tokens(),
            messages=[{"role": "user", "content": "ping"}],
        )
        _ = _anthropic_text(r)
        return
    from openai import AzureOpenAI

    if isinstance(client, AzureOpenAI):
        model = _azure_deployment_for_request()
        extra = _azure_chat_completion_extra_params()
    else:
        model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", "gpt-4o-mini")
        extra = {}
    resp = _openai_chat_completions_create(
        client,
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        **extra,
    )
    _ = _chat_completion_message_content(resp)


def run_review(
    node_id: str,
    repo_root: Path | None = None,
    *,
    planning_body: str | None = None,
) -> str:
    """
    Build context (brief, shared/ index, constraints, cited docs, current
    sheet) and return the revised planning Markdown from the LLM (feature-sheet
    or gate-sheet shape, depending on ``node.type``).

    ``planning_body`` — when not ``None`` (including empty string), used as the
    current planning sheet instead of reading ``planning_dir`` from disk (live
    editor in the GUI).

    Raises ``ReviewError`` on configuration or API failure, ``ValueError`` if
    ``node_id`` is unknown.
    """
    root = (repo_root or default_user_repo_root()).resolve()
    nodes = load_roadmap(root)["nodes"]
    by_id = make_index(nodes)
    if node_id not in by_id:
        raise ValueError(f"unknown node {node_id!r}")
    node = by_id[node_id]
    brief = render_brief(node_id, by_id, repo_root=root)
    shared_index = _shared_catalog(root)
    constraints = _constraints_text(root)
    cited = _cited_snippets(root, node)
    sheet = _feature_sheet_for_prompt(root, node, planning_body)
    nt = node.get("type")
    system_prompt = system_prompt_for_planning_review(
        nt if isinstance(nt, str) else None,
    )
    user_content = "\n\n".join(
        [
            "## Brief\n\n" + brief,
            "## shared/ index (possible references)\n\n" + shared_index,
            "## constraints/README.md\n\n" + constraints,
            "## Cited documents (from contract_citation)\n\n" + cited,
            "## Current planning sheet\n\n" + sheet,
            "## Expected shape\n\n" + planning_review_expected_shape_block(
                nt if isinstance(nt, str) else None,
            ),
        ],
    )
    client = _make_client()
    raw = _complete(client, user_content, system_prompt=system_prompt)
    return _normalize_review_markdown_output(raw)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("node_id", metavar="NODE_ID")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write Markdown report to this file (default: stdout)",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: git root or cwd).",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = _repo_root(args)
    try:
        report = run_review(args.node_id, root)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except ReviewError as e:
        print(f"error: {e}", file=sys.stderr)
        code = 2 if "not installed" in str(e).lower() else 1
        raise SystemExit(code) from e
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
