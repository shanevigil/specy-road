"""Text the harness adapters parse: roster command templates and CLI output lines.

A roster ``channels.cli`` / profile ``access.cli`` is a shell command with
placeholders (``{prompt}``, ``<prompt>``, ``{session}``, ``{session_flag}``);
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
PLACEHOLDERS = ("<prompt>", "{prompt}", "{session}", "{session_flag}")
_SESSION = frozenset({"{session}", "{session_flag}"})
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
                      session_flag: list[str] | None = None) -> str:
    """``{prompt}`` → the quoted file path; ``<prompt>`` (the profiles' form) → the quoted text;
    ``{session_flag}`` → ``session_flag`` as quoted words (nothing when ``None``).

    Per token, whole words only: substituted text is never rescanned, and a
    placeholder embedded in a larger word is refused by
    :func:`placeholder_problem` before this runs.
    """
    values = {"{session}": lambda: shlex.quote(session or ""), "{prompt}": lambda: shlex.quote(str(prompt_path)),
              "<prompt>": lambda: shlex.quote(_text(prompt_path)),
              "{session_flag}": lambda: shlex.join(session_flag or [])}
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
                    '("<prompt>", {prompt}, "{session}", {session_flag}), not part of a larger word')
        if ph == "{session_flag}" and _prefix:
            return f"{tok!r}: {{session_flag}} is arguments, not a file to redirect from"
    if not any(ph in ("<prompt>", "{prompt}") for _s, _e, ph, _p in toks):
        return 'the prompt placeholder must be a whole argument ("<prompt>" or {prompt}), not part of a larger word'
    return None


def has_prompt_placeholder(cli: str | None) -> bool:
    return placeholder_problem(cli) is None


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
