"""PM GUI persisted settings: gui-settings.json (v2, global + per-repo)."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from roadmap_gui_settings_scope import (
    blank_llm_base as _blank_llm_base,
    git_effective as _git_effective,
    read_settings_file_struct_with_git_migration as _read_settings_file_struct_with_git_migration,
)

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
        "pm_gui": {
            "registry_remote_overlay": False,
            "integration_branch_auto_ff": False,
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
    return hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()

def _empty_settings_file_struct() -> dict[str, Any]:
    return {
        "version": SETTINGS_FILE_VERSION,
        "global": {"llm": {}, "git_remote": {}, "pm_gui": {}},
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
        if not isinstance(g.get("pm_gui"), dict):
            g["pm_gui"] = {}
        return out
    llm = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    gr = (
        raw.get("git_remote") if isinstance(raw.get("git_remote"), dict) else {}
    )
    pm = raw.get("pm_gui") if isinstance(raw.get("pm_gui"), dict) else {}
    return {
        "version": SETTINGS_FILE_VERSION,
        "global": {
            "llm": copy.deepcopy(llm),
            "git_remote": copy.deepcopy(gr),
            "pm_gui": copy.deepcopy(pm),
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

def _merged_global_pm_gui(struct: dict[str, Any]) -> dict[str, Any]:
    d, g = default_settings(), struct.get("global") or {}
    gp = g.get("pm_gui") if isinstance(g.get("pm_gui"), dict) else {}
    return {**d["pm_gui"], **gp}


def _get_project_entry(struct: dict[str, Any], repo_id: str) -> dict[str, Any]:
    raw = struct.get("projects") or {}
    if not isinstance(raw, dict):
        raw = {}
    p = raw.get(repo_id)
    if not isinstance(p, dict):
        return {
            "inherit_llm": True,
            "inherit_git_remote": False,
            "inherit_pm_gui": True,
            "llm": {},
            "git_remote": {},
            "pm_gui": {},
        }
    plm = p["llm"] if isinstance(p.get("llm"), dict) else {}
    pgr = p["git_remote"] if isinstance(p.get("git_remote"), dict) else {}
    ppm = p["pm_gui"] if isinstance(p.get("pm_gui"), dict) else {}
    return {
        "inherit_llm": bool(p.get("inherit_llm", True)),
        "inherit_git_remote": bool(p.get("inherit_git_remote", False)),
        "inherit_pm_gui": bool(p.get("inherit_pm_gui", True)),
        "llm": plm,
        "git_remote": pgr,
        "pm_gui": ppm,
    }

def _effective_from_struct(struct: dict[str, Any], repo_id: str) -> dict[str, Any]:
    d = default_settings()
    g_llm = _merged_global_llm_git(struct)[0]
    g_pm = _merged_global_pm_gui(struct)
    proj = _get_project_entry(struct, repo_id)
    pl = proj["llm"]
    pg = proj["git_remote"]
    pp = proj["pm_gui"]
    if proj["inherit_llm"]:
        out_llm = g_llm
    else:
        blank = _blank_llm_base()
        out_llm = {**blank, **pl}
    # Git remote: always this checkout only (never global or cross-project).
    out_git = _git_effective(d["git_remote"], pg)
    if proj["inherit_pm_gui"]:
        out_pm = g_pm
    else:
        out_pm = {**g_pm, **pp}
    return {"llm": out_llm, "git_remote": out_git, "pm_gui": out_pm}

def effective_settings_for_repo(repo_root: Path) -> dict[str, Any]:
    struct = _read_settings_file_struct_with_git_migration(repo_root)
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
    from pm_gui_git_remote_verify import get_git_remote_tested_ok

    struct = _read_settings_file_struct_with_git_migration(repo_root)
    rid = repo_settings_id(repo_root)
    proj = _get_project_entry(struct, rid)
    g_llm, g_git = _merged_global_llm_git(struct)
    eff = _effective_from_struct(struct, rid)
    g_pm = _merged_global_pm_gui(struct)
    return {
        "version": SETTINGS_FILE_VERSION,
        "repo_id": rid,
        "repo_root": str(repo_root.resolve()),
        "inherit_llm": proj["inherit_llm"],
        "inherit_git_remote": False,
        "inherit_pm_gui": proj["inherit_pm_gui"],
        "llm": eff["llm"],
        "git_remote": eff["git_remote"],
        "pm_gui": eff["pm_gui"],
        "git_remote_tested_ok": get_git_remote_tested_ok(repo_root),
        "global_llm": g_llm,
        "global_git_remote": g_git,
        "global_pm_gui": g_pm,
        "project_llm": proj["llm"],
        "project_git_remote": proj["git_remote"],
        "project_pm_gui": proj["pm_gui"],
    }

def save_settings_for_repo(
    repo_root: Path,
    *,
    inherit_llm: bool,
    inherit_git_remote: bool = False,
    inherit_pm_gui: bool = True,
    llm: dict[str, Any],
    git_remote: dict[str, Any],
    pm_gui: dict[str, Any] | None = None,
) -> None:
    """Persist settings: global LLM when inheriting; project-only LLM overlay otherwise.

    Git remote is always stored per repository only (``inherit_git_remote`` is ignored).
    """
    old_git_eff = effective_settings_for_repo(repo_root)["git_remote"]
    struct = _read_settings_file_struct_with_git_migration(repo_root)
    rid = repo_settings_id(repo_root)
    d = default_settings()
    if "global" not in struct or not isinstance(struct["global"], dict):
        struct["global"] = {"llm": {}, "git_remote": {}, "pm_gui": {}}
    if "projects" not in struct or not isinstance(struct["projects"], dict):
        struct["projects"] = {}
    if not isinstance(struct["global"].get("pm_gui"), dict):
        struct["global"]["pm_gui"] = {}

    g_base_pm = {**d["pm_gui"], **(struct["global"].get("pm_gui") or {})}
    blank_llm = _blank_llm_base()
    pm_in = pm_gui if isinstance(pm_gui, dict) else {}

    entry = struct["projects"].get(rid)
    if not isinstance(entry, dict):
        entry = {
            "inherit_llm": True,
            "inherit_git_remote": False,
            "inherit_pm_gui": True,
            "llm": {},
            "git_remote": {},
            "pm_gui": {},
        }
    if "inherit_pm_gui" not in entry:
        entry["inherit_pm_gui"] = True
    if not isinstance(entry.get("pm_gui"), dict):
        entry["pm_gui"] = {}

    if inherit_llm:
        struct["global"]["llm"] = {**d["llm"], **llm}
        entry["inherit_llm"] = True
        entry["llm"] = {}
    else:
        entry["inherit_llm"] = False
        entry["llm"] = _overlay_diff(llm, blank_llm)

    # Git remote: always per-repository (never write global.git_remote from the GUI).
    entry["inherit_git_remote"] = False
    entry["git_remote"] = _overlay_diff(git_remote, d["git_remote"])

    if inherit_pm_gui:
        struct["global"]["pm_gui"] = {**d["pm_gui"], **pm_in}
        entry["inherit_pm_gui"] = True
        entry["pm_gui"] = {}
    else:
        entry["inherit_pm_gui"] = False
        entry["pm_gui"] = _overlay_diff(pm_in, g_base_pm)

    struct["projects"][rid] = entry
    from pm_gui_git_remote_verify import clear_git_remote_tested_ok_if_identity_changed

    clear_git_remote_tested_ok_if_identity_changed(
        repo_root,
        old_git_eff,
        struct,
    )
    _write_settings_file_struct(struct)

def load_settings(repo_root: Path | None = None) -> dict[str, Any]:
    if repo_root is not None:
        return effective_settings_for_repo(repo_root)
    struct = _read_settings_file_struct()
    d = default_settings()
    g = struct.get("global") or {}
    gl = g.get("llm") if isinstance(g.get("llm"), dict) else {}
    gg = g.get("git_remote") if isinstance(g.get("git_remote"), dict) else {}
    gpm = g.get("pm_gui") if isinstance(g.get("pm_gui"), dict) else {}
    base = copy.deepcopy(d)
    base["llm"] = {**d["llm"], **gl}
    base["git_remote"] = {**d["git_remote"], **gg}
    base["pm_gui"] = {**d["pm_gui"], **gpm}
    return base

def save_settings(data: dict[str, Any]) -> None:
    struct = _read_settings_file_struct()
    if "global" not in struct or not isinstance(struct["global"], dict):
        struct["global"] = {"llm": {}, "git_remote": {}, "pm_gui": {}}
    d = default_settings()
    llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    gr = data.get("git_remote") if isinstance(data.get("git_remote"), dict) else {}
    pm = data.get("pm_gui") if isinstance(data.get("pm_gui"), dict) else {}
    g = struct["global"]
    g["llm"], g["git_remote"] = {**d["llm"], **llm}, {**d["git_remote"], **gr}
    g["pm_gui"] = {**d["pm_gui"], **pm}
    struct["version"] = SETTINGS_FILE_VERSION
    _write_settings_file_struct(struct)
