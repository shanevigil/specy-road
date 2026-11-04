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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from specy_road.claude_code_limits import NONE, TIMED, classify_limit
from specy_road.runtime_paths import git_root, recorded_project_root


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


def resume_form_note(cli: str | None, cli_resume: str | None) -> str | None:
    """The warning ``delegate`` prints for a custom launch command that ``message`` / ``resume`` cannot run again:
    it names no ``{session}`` or ``{session_flag}`` and the roster sets no ``channels.cli_resume``, so a resumed
    turn would run the harness's default command, with the default's permissions."""
    if not cli or cli_resume or placeholder_problem(cli) or any(ph in _SESSION for _s, _e, ph, _p in _tokens(cli)):
        return None   # a command that cannot run is refused with its own reason
    return ("warning: `worker message` and `resume` cannot reuse this launch command (it names no {session} or "
            "{session_flag}) and the roster sets no channels.cli_resume, so every resumed turn runs the harness's "
            f"default command with the default's permissions: {cli}")


#: Print-mode commands whose JSON event stream the adapters parse: (binary, print words, JSON form, its words).
_JSON_FORMS = (("claude", {"-p", "--print"}, "--output-format stream-json --verbose", None),
               ("agent", {"-p", "--print"}, "--output-format stream-json", None),
               ("cursor-agent", {"-p", "--print"}, "--output-format stream-json", None),
               ("codex", {"exec"}, "--json", {"--json", "--experimental-json"}))


def _output_format(words: list[str]) -> str | None:
    for i, w in enumerate(words):
        if w == "--output-format" and i + 1 < len(words):
            return words[i + 1]
        if w.startswith("--output-format="):
            return w.split("=", 1)[1]
    return None


def output_mode_note(cli: str | None) -> str | None:
    """The note for a command that visibly runs ``claude`` / ``agent`` in print mode, or ``codex exec``, with text
    output (``--output-format text`` or none): it prints only the final message, so the worker's events keep only
    that. A wrapper script is not looked into."""
    if not cli or placeholder_problem(cli):
        return None
    words = [w.strip("\"'") for w in _WORD.findall(cli)]
    for binary, print_words, form, json_words in _JSON_FORMS:
        at = [i for i, w in enumerate(words) if w.rsplit("/", 1)[-1] == binary]
        if not at or not print_words & set(words[at[0] + 1:]):
            continue
        rest = words[at[0] + 1:]
        streams = bool(json_words & set(rest)) if json_words else _output_format(rest) == "stream-json"
        if streams:
            return None
        return (f"note: this command prints no {binary} event stream (text output), so the worker's log keeps only "
                f"its last message; use `{form}`: {cli}")
    return None


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


def model_from_argv(argv: list[str]) -> str | None:
    """The ``--model`` / ``-m`` value from a harness launch argv, when present."""
    for i, w in enumerate(argv):
        if w in ("--model", "-m") and i + 1 < len(argv):
            return argv[i + 1]
        if w.startswith("--model="):
            return w.split("=", 1)[1]
    return None


def worktree_from_argv(argv: list[str]) -> Path | None:
    """``--workspace`` or ``-C`` from a harness launch argv, when present."""
    for i, w in enumerate(argv):
        if w in ("--workspace", "-C") and i + 1 < len(argv):
            return Path(argv[i + 1])
    return None


def project_root_from_worktree(wt: Path | None) -> Path:
    """Project root the way :func:`project_root` would from this checkout's cwd.

    ``recorded_project_root(git_root(wt))`` when ``.specyrd`` records a nested
    root; otherwise the git worktree (embedded). ``wt`` is the harness
    ``--workspace`` (a git worktree root). Does not take ``project_root(wt)``
    (that is ``--repo-root``) and does not walk ancestors with
    :func:`discover_project_root`.
    """
    start = Path(wt).resolve() if wt is not None else Path.cwd()
    top = git_root(start)
    if top is None:
        return start
    return recorded_project_root(top) or top


def _mtok_rate(value: Any) -> float | None:
    if value is None or value == "unknown":
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    return rate if rate >= 0 else None


def mtok_rates(profile_data: dict[str, Any]) -> dict[str, float | None]:
    """``cost_usd_per_mtok`` rates orchestrate plan reads, for :func:`estimate_usage_cost`."""
    raw = profile_data.get("cost_usd_per_mtok") or {}
    if not isinstance(raw, dict):
        return {}
    return {k: _mtok_rate(raw.get(k)) for k in ("input", "output", "cached_input")}


def estimate_usage_cost(usage: dict[str, Any], rates: dict[str, float | None]) -> float | None:
    """USD for one turn from token counts and profile list prices; ``None`` when a required rate is missing."""
    inp, out = usage.get("input_tokens"), usage.get("output_tokens")
    if inp is None and out is None:
        return None
    in_rate, out_rate = rates.get("input"), rates.get("output")
    if in_rate is None or out_rate is None:
        return None
    cached = usage.get("cached_input_tokens") or 0
    inp, out = inp or 0, out or 0
    cached_rate = rates.get("cached_input")
    non_cached = inp - cached if inp >= cached else inp
    usd = (non_cached * in_rate + cached * (cached_rate if cached_rate is not None else in_rate) + out * out_rate) / 1_000_000
    return round(usd, 6)


def apply_roster_price_estimate(usage: dict[str, Any], model_id: str, repo_root: Path) -> dict[str, Any]:
    """Fill ``cost_usd`` and ``cost_is_estimate`` from the pinned roster profile when the harness reported none.

    ``model_id`` is what production puts on argv (``Profile.api_id`` or an alias), not necessarily
    the roster ``id``. Each entry's pinned profile is matched with :meth:`Profile.for_id`.
    """
    if usage.get("cost_usd") is not None or not model_id:
        return usage
    from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry  # noqa: PLC0415

    config, err = pinned_config(repo_root)
    if err:
        return usage
    prof = next((m for e in config.get("roster") or []
                 if (p := pinned_profile_for_entry(repo_root, e)) and p.ok and (m := p.for_id(model_id))), None)
    if not prof:
        return usage
    cost = estimate_usage_cost(usage, mtok_rates(prof.data))
    if cost is None:
        return usage
    return {**usage, "cost_usd": cost, "cost_is_estimate": True}


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


#: Codex names a limit's reset in free text (harness-facts quota): "try again in 2 days 3 hours 5 minutes", or
#: "try again at 3:05 PM", with a date before the clock when it is not today; the clock is the machine's local time.
_TRY_IN = re.compile(r"try again in\s+((?:\d+\s*[a-z]+[\s,]*(?:and\s+)?)+)", re.IGNORECASE)
_UNIT = re.compile(r"(\d+)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.IGNORECASE)
_TRY_AT = re.compile(r"try again (?:at|after)\s+(?:([a-z]{3})[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4}),? )?"
                     r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _try_again(text: str, now: datetime) -> datetime | None:
    """The UTC instant a "try again in <duration>" or "try again at <time>" message names, or ``None``."""
    if m := _TRY_IN.search(text):
        secs = sum(int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u[0].lower()] for n, u in _UNIT.findall(m.group(1)))
        return now + timedelta(seconds=secs) if secs else None
    if not (m := _TRY_AT.search(text)):
        return None
    mon, day, year, hh, mm, ap = m.groups()
    local = now.astimezone()
    try:
        at = local.replace(hour=int(hh) % 12 + (12 if ap.lower() == "p" else 0), minute=int(mm), second=0, microsecond=0)
        if year:
            at = at.replace(year=int(year), month=_MONTHS[mon.lower()], day=int(day))
        elif at <= local:   # a bare clock time is its next occurrence
            at += timedelta(days=1)
    except (KeyError, ValueError):
        return None
    return at.astimezone(timezone.utc)


def limit_detail(text: str, *, failed: bool, now: datetime | None = None) -> dict[str, Any] | None:
    """``{"reset_at": UTC ISO time or None, "evidence": text}`` when a turn's text says a usage limit stopped it.

    Read from the text, never the exit code. A failed turn needs limit wording (:func:`classify_limit`); a
    successful one needs a stated reset time as well (Claude reports some limits as subtype success, exit 0), so
    a reply that only mentions rate limits is not read as one. Codex's "try again" time is read when Claude's
    "resets" wording is absent.
    """
    now = now or datetime.now(timezone.utc)
    verdict = classify_limit(text, now=now)
    if verdict.kind == NONE or not (failed or verdict.kind == TIMED):
        return None
    reset = verdict.reset_at if verdict.kind == TIMED else _try_again(text, now)
    return {"reset_at": reset.isoformat() if reset else None, "evidence": _snip(verdict.evidence or text, 300)}
