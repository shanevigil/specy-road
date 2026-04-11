"""PM GUI persisted settings: gui-settings.json (v2, global + per-repo)."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SETTINGS_DIR = Path.home() / ".specy-road"
SETTINGS_PATH = SETTINGS_DIR / "gui-settings.json"
SETTINGS_FILE_VERSION = 2
_B64_PREFIX = "__b64__:"


def _b64_encode(s: str) -> str:
    return base64.standard_b64encode(s.encode("utf-8")).decode("ascii")


def _b64_decode(s: str) -> str:
    return base64.standard_b64decode(s.encode("ascii")).decode("utf-8")


def default_settings() -> dict[str, Any]:
    return {
        "llm": {
            "backend": "openai",
            "openai_api_key": "",
            "openai_model": "gpt-4o-mini",
            "openai_base_url": "",
            "azure_endpoint": "",
            "azure_api_key": "",
            "azure_deployment": "",
            "azure_api_version": "2024-02-15-preview",
            "anthropic_api_key": "",
            "anthropic_model": "",
        },
        "git_remote": {
            "provider": "github",
            "repo": "",
            "token": "",
            "base_url": "",
        },
    }


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


def repo_settings_id(repo_root: Path) -> str:
    """Stable id for the ``projects`` map in gui-settings.json."""
    return hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()


def _empty_settings_file_struct() -> dict[str, Any]:
    return {
        "version": SETTINGS_FILE_VERSION,
        "global": {"llm": {}, "git_remote": {}},
        "projects": {},
    }


def _migrate_raw_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("version") == SETTINGS_FILE_VERSION and isinstance(
        raw.get("global"),
        dict,
    ):
        out = copy.deepcopy(raw)
        if "projects" not in out or not isinstance(out["projects"], dict):
            out["projects"] = {}
        g = out["global"]
        if not isinstance(g.get("llm"), dict):
            g["llm"] = {}
        if not isinstance(g.get("git_remote"), dict):
            g["git_remote"] = {}
        return out
    llm = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    gr = (
        raw.get("git_remote") if isinstance(raw.get("git_remote"), dict) else {}
    )
    return {
        "version": SETTINGS_FILE_VERSION,
        "global": {
            "llm": copy.deepcopy(llm),
            "git_remote": copy.deepcopy(gr),
        },
        "projects": {},
    }


def _read_settings_file_struct() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return _empty_settings_file_struct()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_settings_file_struct()
    if not isinstance(raw, dict):
        return _empty_settings_file_struct()
    struct = _migrate_raw_to_v2(raw)
    _decode_tokens_in_struct(struct)
    return struct


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


def _write_settings_file_struct(struct: dict[str, Any]) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = copy.deepcopy(struct)
    out["version"] = SETTINGS_FILE_VERSION
    g = out.get("global") or {}
    gl_ok = isinstance(g.get("llm"), dict)
    gr_ok = isinstance(g.get("git_remote"), dict)
    if gl_ok and gr_ok:
        g["llm"], g["git_remote"] = _obfuscate_llm_git(g["llm"], g["git_remote"])
    projs = out.get("projects") or {}
    if isinstance(projs, dict):
        for _pid, entry in projs.items():
            if not isinstance(entry, dict):
                continue
            el_ok = isinstance(entry.get("llm"), dict)
            er_ok = isinstance(entry.get("git_remote"), dict)
            if el_ok and er_ok:
                entry["llm"], entry["git_remote"] = _obfuscate_llm_git(
                    entry["llm"],
                    entry["git_remote"],
                )
    SETTINGS_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def _merged_global_llm_git(
    struct: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    d = default_settings()
    g = struct.get("global") or {}
    gl = g.get("llm") if isinstance(g.get("llm"), dict) else {}
    gg = g.get("git_remote") if isinstance(g.get("git_remote"), dict) else {}
    m_llm = {**d["llm"], **gl}
    m_gr = {**d["git_remote"], **gg}
    return m_llm, m_gr


def _get_project_entry(struct: dict[str, Any], repo_id: str) -> dict[str, Any]:
    raw = struct.get("projects") or {}
    if not isinstance(raw, dict):
        raw = {}
    p = raw.get(repo_id)
    if not isinstance(p, dict):
        return {
            "inherit_llm": True,
            "inherit_git_remote": True,
            "llm": {},
            "git_remote": {},
        }
    plm = p["llm"] if isinstance(p.get("llm"), dict) else {}
    pgr = p["git_remote"] if isinstance(p.get("git_remote"), dict) else {}
    return {
        "inherit_llm": bool(p.get("inherit_llm", True)),
        "inherit_git_remote": bool(p.get("inherit_git_remote", True)),
        "llm": plm,
        "git_remote": pgr,
    }


def _effective_from_struct(struct: dict[str, Any], repo_id: str) -> dict[str, Any]:
    g_llm, g_git = _merged_global_llm_git(struct)
    proj = _get_project_entry(struct, repo_id)
    pl = proj["llm"]
    pg = proj["git_remote"]
    if proj["inherit_llm"]:
        out_llm = g_llm
    else:
        out_llm = {**g_llm, **pl}
    if proj["inherit_git_remote"]:
        out_git = g_git
    else:
        out_git = {**g_git, **pg}
    return {"llm": out_llm, "git_remote": out_git}


def effective_settings_for_repo(repo_root: Path) -> dict[str, Any]:
    """Merged effective LLM + git_remote dicts for this git worktree."""
    struct = _read_settings_file_struct()
    rid = repo_settings_id(repo_root)
    return _effective_from_struct(struct, rid)


def _overlay_diff(eff: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in set(eff) | set(base):
        ev = eff.get(k, "")
        bv = base.get(k, "")
        if str(ev) != str(bv):
            out[k] = eff[k] if k in eff else ""
    return out


def settings_api_payload(repo_root: Path) -> dict[str, Any]:
    """JSON for ``GET /api/settings`` (effective values + inheritance flags)."""
    struct = _read_settings_file_struct()
    rid = repo_settings_id(repo_root)
    proj = _get_project_entry(struct, rid)
    g_llm, g_git = _merged_global_llm_git(struct)
    eff = _effective_from_struct(struct, rid)
    return {
        "version": SETTINGS_FILE_VERSION,
        "repo_id": rid,
        "repo_root": str(repo_root.resolve()),
        "inherit_llm": proj["inherit_llm"],
        "inherit_git_remote": proj["inherit_git_remote"],
        "llm": eff["llm"],
        "git_remote": eff["git_remote"],
        "global_llm": g_llm,
        "global_git_remote": g_git,
        "project_llm": proj["llm"],
        "project_git_remote": proj["git_remote"],
    }


def save_settings_for_repo(
    repo_root: Path,
    *,
    inherit_llm: bool,
    inherit_git_remote: bool,
    llm: dict[str, Any],
    git_remote: dict[str, Any],
) -> None:
    """Persist settings: global and/or per-repo overlays from inheritance flags."""
    struct = _read_settings_file_struct()
    rid = repo_settings_id(repo_root)
    d = default_settings()
    if "global" not in struct or not isinstance(struct["global"], dict):
        struct["global"] = {"llm": {}, "git_remote": {}}
    if "projects" not in struct or not isinstance(struct["projects"], dict):
        struct["projects"] = {}

    g_base_llm = {**d["llm"], **(struct["global"].get("llm") or {})}
    g_base_gr = {**d["git_remote"], **(struct["global"].get("git_remote") or {})}

    entry = struct["projects"].get(rid)
    if not isinstance(entry, dict):
        entry = {
            "inherit_llm": True,
            "inherit_git_remote": True,
            "llm": {},
            "git_remote": {},
        }

    if inherit_llm:
        struct["global"]["llm"] = {**d["llm"], **llm}
        entry["inherit_llm"] = True
        entry["llm"] = {}
    else:
        entry["inherit_llm"] = False
        entry["llm"] = _overlay_diff(llm, g_base_llm)

    if inherit_git_remote:
        struct["global"]["git_remote"] = {**d["git_remote"], **git_remote}
        entry["inherit_git_remote"] = True
        entry["git_remote"] = {}
    else:
        entry["inherit_git_remote"] = False
        entry["git_remote"] = _overlay_diff(git_remote, g_base_gr)

    struct["projects"][rid] = entry
    _write_settings_file_struct(struct)


def load_settings(repo_root: Path | None = None) -> dict[str, Any]:
    """Global-only merged dict, or per-repo effective dict when ``repo_root`` set."""
    if repo_root is not None:
        return effective_settings_for_repo(repo_root)
    struct = _read_settings_file_struct()
    d = default_settings()
    g = struct.get("global") or {}
    gl = g.get("llm") if isinstance(g.get("llm"), dict) else {}
    gg = g.get("git_remote") if isinstance(g.get("git_remote"), dict) else {}
    base = copy.deepcopy(d)
    base["llm"] = {**d["llm"], **gl}
    base["git_remote"] = {**d["git_remote"], **gg}
    return base


def save_settings(data: dict[str, Any]) -> None:
    """Write global LLM/git_remote only; keeps per-repo ``projects`` entries."""
    struct = _read_settings_file_struct()
    if "global" not in struct or not isinstance(struct["global"], dict):
        struct["global"] = {"llm": {}, "git_remote": {}}
    d = default_settings()
    llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    gr = data.get("git_remote") if isinstance(data.get("git_remote"), dict) else {}
    struct["global"]["llm"] = {**d["llm"], **llm}
    struct["global"]["git_remote"] = {**d["git_remote"], **gr}
    struct["version"] = SETTINGS_FILE_VERSION
    _write_settings_file_struct(struct)
