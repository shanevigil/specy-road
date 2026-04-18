"""Per-checkout Git scoping and one-time migration from legacy global git_remote."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def blank_llm_base() -> dict[str, Any]:
    """Same keys as default LLM settings; empty strings (backend stays openai for UI)."""
    import roadmap_gui_settings as m

    d = m.default_settings()["llm"]
    return {k: ("openai" if k == "backend" else "") for k in d}


def git_effective(
    d_git: dict[str, Any],
    proj_overlay: dict[str, Any],
) -> dict[str, Any]:
    pg = proj_overlay if isinstance(proj_overlay, dict) else {}
    return {**d_git, **pg}


def migrate_global_git_into_project_if_needed(
    struct: dict[str, Any],
    repo_id: str,
) -> bool:
    """Copy legacy global git_remote into this project if the project had no saved identity."""
    import roadmap_gui_settings as m

    d = m.default_settings()
    d_git = d["git_remote"]
    g = struct.get("global") or {}
    gg = g.get("git_remote") if isinstance(g.get("git_remote"), dict) else {}
    g_full = {**d_git, **gg}
    if g_full == d_git:
        return False
    raw = struct.get("projects") or {}
    if not isinstance(raw, dict):
        raw = {}
    proj = raw.get(repo_id)
    if not isinstance(proj, dict):
        proj = {
            "inherit_llm": True,
            "inherit_git_remote": False,
            "inherit_pm_gui": True,
            "llm": {},
            "git_remote": {},
            "pm_gui": {},
        }
    pg = proj.get("git_remote") if isinstance(proj.get("git_remote"), dict) else {}
    p_full = git_effective(d_git, pg)
    if p_full != d_git:
        return False
    proj["inherit_git_remote"] = False
    proj["git_remote"] = m._overlay_diff(g_full, d_git)
    if "projects" not in struct or not isinstance(struct["projects"], dict):
        struct["projects"] = {}
    struct["projects"][repo_id] = proj
    return True


def read_settings_file_struct_with_git_migration(repo_root: Path) -> dict[str, Any]:
    import roadmap_gui_settings as m

    struct = m._read_settings_file_struct()
    rid = m.repo_settings_id(repo_root)
    if migrate_global_git_into_project_if_needed(struct, rid):
        m._write_settings_file_struct(struct)
    return struct
