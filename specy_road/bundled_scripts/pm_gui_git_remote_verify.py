"""Persisted Git-remote "Test Git" flag and identity compare for registry overlay gating.

``roadmap_gui_settings`` is imported inside functions so its save path can call here
without a circular import at module load.
"""

from __future__ import annotations

from typing import Any


def git_remote_identity(gr: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        (gr.get("provider") or "").strip().lower(),
        (gr.get("repo") or "").strip(),
        (gr.get("token") or "").strip(),
        (gr.get("base_url") or "").strip(),
    )


def get_git_remote_tested_ok(repo_root) -> bool:
    import roadmap_gui_settings as m

    struct = m._read_settings_file_struct()
    rid = m.repo_settings_id(repo_root)
    p = (struct.get("projects") or {}).get(rid)
    if not isinstance(p, dict):
        return False
    return bool(p.get("git_remote_tested_ok"))


def set_git_remote_tested_ok(repo_root, ok: bool) -> None:
    import roadmap_gui_settings as m

    struct = m._read_settings_file_struct()
    rid = m.repo_settings_id(repo_root)
    if "projects" not in struct or not isinstance(struct["projects"], dict):
        struct["projects"] = {}
    entry = struct["projects"].get(rid)
    if not isinstance(entry, dict):
        entry = {
            "inherit_llm": True,
            "inherit_git_remote": True,
            "inherit_pm_gui": True,
            "llm": {},
            "git_remote": {},
            "pm_gui": {},
        }
    entry["git_remote_tested_ok"] = ok
    struct["projects"][rid] = entry
    m._write_settings_file_struct(struct)


def clear_git_remote_tested_ok_if_identity_changed(
    repo_root,
    old_git_remote: dict[str, Any],
    struct_after: dict[str, Any],
) -> None:
    """Clear ``git_remote_tested_ok`` if effective git remote identity changed vs ``old_git_remote``."""
    import roadmap_gui_settings as m

    rid = m.repo_settings_id(repo_root)
    new_eff = m._effective_from_struct(struct_after, rid)
    if git_remote_identity(old_git_remote) != git_remote_identity(
        new_eff.get("git_remote") or {},
    ):
        entry = struct_after.get("projects", {}).get(rid)
        if isinstance(entry, dict):
            entry["git_remote_tested_ok"] = False
