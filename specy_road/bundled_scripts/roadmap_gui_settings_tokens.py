"""Obfuscate API tokens at rest in ``gui-settings.json``.

Base64, not encryption — it keeps keys from sitting in plain sight in a file
users open in an editor, and nothing more. Split from
:mod:`roadmap_gui_settings` to keep that module under the file-line cap; this
is the one coherent piece that stands on its own.
"""

from __future__ import annotations

import base64
import copy
from typing import Any

_B64_PREFIX = "__b64__:"


def _b64_encode(s: str) -> str:
    return base64.standard_b64encode(s.encode("utf-8")).decode("ascii")

def _b64_decode(s: str) -> str:
    return base64.standard_b64decode(s.encode("ascii")).decode("utf-8")

def _merge_token_fields(base: dict[str, Any]) -> None:
    for key in ("openai_api_key", "azure_api_key", "anthropic_api_key"):
        v = base["llm"].get(key) or ""
        if isinstance(v, str) and v.startswith(_B64_PREFIX):
            try:
                base["llm"][key] = _b64_decode(v[len(_B64_PREFIX):])
            except (ValueError, UnicodeDecodeError):
                base["llm"][key] = ""
    tok = base["git_remote"].get("token") or ""
    if isinstance(tok, str) and tok.startswith(_B64_PREFIX):
        try:
            base["git_remote"]["token"] = _b64_decode(tok[len(_B64_PREFIX):])
        except (ValueError, UnicodeDecodeError):
            base["git_remote"]["token"] = ""

def _decode_tokens_in_struct(struct: dict[str, Any]) -> None:
    g = struct.get("global") or {}
    gl_ok = isinstance(g.get("llm"), dict)
    gr_ok = isinstance(g.get("git_remote"), dict)
    if gl_ok and gr_ok:
        pair = {"llm": g["llm"], "git_remote": g["git_remote"]}
        _merge_token_fields(pair)
        g["llm"], g["git_remote"] = pair["llm"], pair["git_remote"]
    projs = struct.get("projects") or {}
    if not isinstance(projs, dict):
        return
    for _pid, entry in list(projs.items()):
        if not isinstance(entry, dict):
            continue
        el_ok = isinstance(entry.get("llm"), dict)
        er_ok = isinstance(entry.get("git_remote"), dict)
        if el_ok and er_ok:
            pair = {"llm": entry["llm"], "git_remote": entry["git_remote"]}
            _merge_token_fields(pair)
            entry["llm"], entry["git_remote"] = pair["llm"], pair["git_remote"]

def _obfuscate_llm_git(
    llm: dict[str, Any],
    git_remote: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    out_l = copy.deepcopy(llm)
    out_g = copy.deepcopy(git_remote)
    for key in ("openai_api_key", "azure_api_key", "anthropic_api_key"):
        v = out_l.get(key) or ""
        if v:
            out_l[key] = _B64_PREFIX + _b64_encode(str(v))
        elif key in out_l and not out_l[key]:
            out_l[key] = ""
    tok = out_g.get("token") or ""
    if tok:
        out_g["token"] = _B64_PREFIX + _b64_encode(str(tok))
    elif "token" in out_g and not out_g["token"]:
        out_g["token"] = ""
    return out_l, out_g
