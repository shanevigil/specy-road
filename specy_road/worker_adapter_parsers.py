"""Text the harness adapters parse: roster command templates and CLI output lines.

A roster ``channels.cli`` / profile ``access.cli`` is a shell command with
placeholders (``{prompt}``, ``<prompt>``, ``{session}``, ``{session_flag}``, ``{effort}``);
this module validates and substitutes them. It also holds the small helpers
the adapters use to read a prompt file and a JSON output line.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any


def _text(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


#: A placeholder must be a whole shell word, bare or wrapped in exactly one
#: pair of quotes, optionally behind a ``<`` redirection. Inside a larger
#: word (``"prefix <prompt> suffix"``, ``--session-id={session}``) the quoting
#: ``shlex.quote`` adds would land inside still-open quotes, where ``$(…)``
#: runs; and an embedded ``{session}`` would never be substituted at all.
#: Validation and substitution walk the same tokens, so they cannot disagree.
PLACEHOLDERS = ("<prompt>", "{prompt}", "{session}", "{session_flag}", "{effort}")
_SESSION = frozenset({"{session}", "{session_flag}"})
_ARGS = frozenset({"{session_flag}", "{effort}"})   # expand to arguments, never a file to redirect from
_WORD = re.compile(r'''(?:[^\s"']+|"[^"]*"|'[^']*')+''')   # a shell word: bare runs and whole quoted spans
_ANY_PROMPT = re.compile(r"<prompt>|\{prompt\}")


def _placeholder_of(token: str) -> tuple[str | None, str]:
    """``(placeholder, prefix)``: the placeholder a token *is* (bare, ``"ph"`` or ``'ph'``, optionally
    behind a ``<`` redirection that is the prefix), or ``(None, "")``."""
    forms = {f: p for p in PLACEHOLDERS for f in (p, f'"{p}"', f"'{p}'")}
    if token in forms:
        return forms[token], ""
    if token.startswith("<") and token[1:] in forms:
        return forms[token[1:]], "<"
    return None, ""


def _tokens(cli: str) -> list[tuple[int, int, str | None, str]]:
    """``(start, end, placeholder-or-None, prefix)`` per shell word; ``ValueError`` on an unbalanced quote."""
    if _WORD.sub("", cli).strip():
        raise ValueError("unbalanced quote")
    return [(m.start(), m.end(), *_placeholder_of(m.group(0))) for m in _WORD.finditer(cli)]


def substitute_prompt(cli: str, prompt_path: Path, session: str | None = None,
                      session_flag: list[str] | None = None, effort: list[str] | None = None) -> str:
    """``{prompt}`` → the quoted file path; ``<prompt>`` (the profiles' form) → the quoted text;
    ``{session_flag}`` and ``{effort}`` → ``session_flag`` / ``effort`` as quoted words (nothing when ``None``).

    Per token, whole words only: substituted text is never rescanned, and a
    placeholder embedded in a larger word is refused by
    :func:`placeholder_problem` before this runs.
    """
    values = {"{session}": lambda: shlex.quote(session or ""), "{prompt}": lambda: shlex.quote(str(prompt_path)),
              "<prompt>": lambda: shlex.quote(_text(prompt_path)),
              "{session_flag}": lambda: shlex.join(session_flag or []), "{effort}": lambda: shlex.join(effort or [])}
    out, pos = [], 0
    for start, end, ph, prefix in _tokens(cli):
        if ph is None:
            continue
        out.append(cli[pos:start] + prefix + values[ph]())
        pos = end
    return "".join(out) + cli[pos:]


def placeholder_problem(cli: str | None) -> str | None:
    """Why ``cli`` cannot be run: no prompt placeholder, or one that is not a whole word."""
    if not cli or not _ANY_PROMPT.search(cli):
        return "no {prompt} (the prompt file path) or <prompt> (the prompt text) placeholder"
    try:
        toks = _tokens(cli)
    except ValueError as e:
        return str(e)
    for start, end, ph, _prefix in toks:
        tok = cli[start:end]
        if ph is None and any(p in tok for p in PLACEHOLDERS):
            return (f"placeholder in {tok!r} must be a whole argument — bare or in one pair of quotes "
                    '("<prompt>", {prompt}, "{session}", {session_flag}, {effort}), not part of a larger word')
        if ph in _ARGS and _prefix:
            return f"{tok!r}: {ph} is arguments, not a file to redirect from"
    if not any(ph in ("<prompt>", "{prompt}") for _s, _e, ph, _p in toks):
        return 'the prompt placeholder must be a whole argument ("<prompt>" or {prompt}), not part of a larger word'
    return None


def has_prompt_placeholder(cli: str | None) -> bool:
    return placeholder_problem(cli) is None


def effort_note(cli: str | None, level: str | None) -> str | None:
    """The one note for a profile that sets this role's effort when ``cli`` names no ``{effort}``."""
    if not cli or not level or placeholder_problem(cli) or any(ph == "{effort}" for _s, _e, ph, _p in _tokens(cli)):
        return None   # a command that cannot run is refused with its own reason
    return f"note: the profile sets effort {level} for this role, but the command takes no effort (no {{effort}}): {cli}"


def _snip(s: str, n: int = 200) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _json(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


#: The tools `claude -p --bare` starts with: "Bash, file read, and file edit"
#: (code.claude.com/docs/en/headless, read 2026-11-01).
CLAUDE_BARE_TOOLS = frozenset({"Bash", "Read", "Edit"})


def _names(items: Any) -> list[str]:
    """The ``name`` of each ``{name, ...}`` entry (``mcp_servers``, ``plugins``), or the entry itself."""
    return [str(i.get("name") if isinstance(i, dict) else i) for i in items] if isinstance(items, list) else []


def _init_detail(d: dict[str, Any]) -> dict[str, Any]:
    """What a Claude ``system/init`` line says the harness loaded, and the discovery mode that implies."""
    detail: dict[str, Any] = {"tools": _names(d.get("tools")), "mcp_servers": _names(d.get("mcp_servers")),
                              "plugins": _names(d.get("plugins"))}
    version = d.get("claude_code_version") or d.get("version")   # the SDK's field name, then the short one
    if version:
        detail["version"] = str(version)
    if isinstance(d.get("tools"), list):   # no tool list reported: no evidence either way
        detail["inferred_mode"] = "bare" if set(detail["tools"]) <= CLAUDE_BARE_TOOLS else "full"
    return detail


#: The ``usage`` event's detail, in this order; a field the harness did not report is ``None``, never 0.
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "cost_usd",
                "cost_is_estimate", "num_turns", "harness_version")


def _num(v: Any, *, whole: bool = False) -> int | float | None:
    """``v`` when it is a non-negative number (an integral one for ``whole``), else ``None``: the line is the model's."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        return None
    if whole:
        return int(v) if float(v).is_integer() else None
    return v


def usage_fields(u: Any, *, cost: Any = None, num_turns: Any = None, estimate: bool | None = None) -> dict[str, Any]:
    """A harness's token counts in the vendor-neutral shape of :data:`USAGE_FIELDS`.

    ``input_tokens`` counts every input token, cached ones included, and
    ``cached_input_tokens`` the part read from cache: Codex reports it that
    way; Claude's (and Cursor's) ``input_tokens`` leaves out the cache reads
    and writes, which are added back. Snake and camel case keys are both read;
    Claude reports reasoning as ``output_tokens_details.thinking_tokens``.
    """
    u = u if isinstance(u, dict) else {}
    details = u.get("output_tokens_details") if isinstance(u.get("output_tokens_details"), dict) else {}

    def get(*keys: str, src: dict[str, Any] = u) -> int | None:
        return next((n for n in (_num(src.get(k), whole=True) for k in keys) if n is not None), None)

    inp, cached = get("input_tokens", "inputTokens"), get("cached_input_tokens", "cachedInputTokens")
    read, write = get("cache_read_input_tokens", "cacheReadTokens"), get("cache_creation_input_tokens", "cacheWriteTokens")
    if cached is None and (read is not None or write is not None):   # separate cache buckets, as Anthropic reports them
        inp, cached = (None if inp is None else inp + (read or 0) + (write or 0)), read
    reasoning = get("reasoning_output_tokens", "reasoning_tokens", "reasoningTokens")
    if reasoning is None:
        reasoning = get("thinking_tokens", src=details)
    cost = _num(cost)
    return {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": get("output_tokens", "outputTokens"),
            "reasoning_tokens": reasoning,
            "cost_usd": cost, "cost_is_estimate": estimate if cost is not None else None,
            "num_turns": _num(num_turns, whole=True), "harness_version": None}


def usage_text(u: dict[str, Any]) -> str:
    """``in 1200 (800 cached), out 300, reasoning ?, $0.0123 est.``: ``?`` is a figure the harness did not report."""
    def n(k: str) -> str:
        return "?" if u.get(k) is None else str(u[k])
    cost = "$?" if u.get("cost_usd") is None else f"${u['cost_usd']:.4f}" + (" est." if u.get("cost_is_estimate") else "")
    return (f"in {n('input_tokens')} ({n('cached_input_tokens')} cached), out {n('output_tokens')}, "
            f"reasoning {n('reasoning_tokens')}, {cost}")
