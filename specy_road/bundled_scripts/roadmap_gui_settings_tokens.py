"""Obfuscate API tokens at rest in ``gui-settings.json``.

Base64, not encryption — it keeps keys from sitting in plain sight in a file
users open in an editor, and nothing more. Split from
:mod:`roadmap_gui_settings` to keep that module under the file-line cap; this
is the one coherent piece that stands on its own.

Which fields are secret is a table rather than three hardcoded blocks, so a new
credentialed settings group (``research`` was the third) only adds a row.
"""

from __future__ import annotations

import base64
import copy
from typing import Any

_B64_PREFIX = "__b64__:"

#: Settings block -> the fields in it that hold a credential.
TOKEN_FIELDS: dict[str, tuple[str, ...]] = {
    "llm": ("openai_api_key", "azure_api_key", "anthropic_api_key"),
    "git_remote": ("token",),
    # `bing_api_key` is the pre-provider name, still obfuscated so an existing
    # settings file is not left holding a plaintext key.
    "research": ("api_key", "bing_api_key"),
}


def _b64_encode(s: str) -> str:
    return base64.standard_b64encode(s.encode("utf-8")).decode("ascii")

def _b64_decode(s: str) -> str:
    return base64.standard_b64decode(s.encode("ascii")).decode("utf-8")


def _decode_block(block: dict[str, Any], keys: tuple[str, ...]) -> None:
    """Decode in place; an unreadable token becomes empty rather than garbage."""
    for key in keys:
        v = block.get(key) or ""
        if isinstance(v, str) and v.startswith(_B64_PREFIX):
            try:
                block[key] = _b64_decode(v[len(_B64_PREFIX):])
            except (ValueError, UnicodeDecodeError):
                block[key] = ""


def _merge_token_fields(base: dict[str, Any]) -> None:
    for name, keys in TOKEN_FIELDS.items():
        block = base.get(name)
        if isinstance(block, dict):
            _decode_block(block, keys)


def _decode_tokens_in_struct(struct: dict[str, Any]) -> None:
    scopes = [struct.get("global") or {}]
    projs = struct.get("projects") or {}
    if isinstance(projs, dict):
        scopes.extend(e for e in projs.values() if isinstance(e, dict))
    for scope in scopes:
        if isinstance(scope, dict):
            _merge_token_fields(scope)


def obfuscate_block(name: str, block: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``block`` with its credential fields base64-tagged."""
    out = copy.deepcopy(block)
    for key in TOKEN_FIELDS.get(name, ()):
        v = out.get(key) or ""
        if v:
            out[key] = _B64_PREFIX + _b64_encode(str(v))
        elif key in out:
            out[key] = ""
    return out


def _obfuscate_llm_git(
    llm: dict[str, Any],
    git_remote: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return obfuscate_block("llm", llm), obfuscate_block("git_remote", git_remote)
