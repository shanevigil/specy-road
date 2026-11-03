"""Helpers for ``specyrd init`` (split from specyrd_init for the file limit, M8.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def init_repo_context(
    target: Path,
    agent: str,
    ai_commands_dir: Path | None,
    role: str | None,
) -> tuple[Path, Path, list[str], list[str], dict[str, Any], tuple[str, ...], set[str]]:
    from specy_road import specyrd_init as si

    if agent not in si.AGENT_CHOICES:
        raise ValueError(f"unknown agent: {agent}")
    if role is not None and role not in si.ROLE_CHOICES:
        raise ValueError(f"unknown role: {role!r}; choose pm, dev, or both")
    if agent == "generic":
        if ai_commands_dir is None:
            raise ValueError("--ai-commands-dir is required when --ai generic")
        rel_dest = ai_commands_dir
    else:
        rel_dest = si.AGENT_REL_DEST[agent]
        assert rel_dest is not None
    repo_root = si.resolve_repo_root(target)
    if agent == "generic":
        rel_dest = si._validate_generic_commands_dir(repo_root, rel_dest)
    written: list[str] = []
    skipped: list[str] = []
    manifest = si._load_manifest(repo_root)
    files_to_install = si.ROLE_COMMAND_FILES[role] if role in ("pm", "dev") else si.COMMAND_FILES
    already_owned = {p for paths in (manifest.get("agents") or {}).values() for p in paths}
    return repo_root, rel_dest, written, skipped, manifest, files_to_install, already_owned


def maybe_install_specyrd_hooks(
    repo_root: Path,
    agent: str,
    *,
    install_guard_hooks: bool,
    install_pre_push: bool,
    dry_run: bool,
    written: list[str],
) -> None:
    from specy_road.specyrd_hooks import install_orchestration_hooks, install_pre_push_hook

    if install_guard_hooks and agent in ("claude-code", "codex", "cursor"):
        install_orchestration_hooks(repo_root, agent, dry_run=dry_run, written=written)
    if install_pre_push:
        install_pre_push_hook(repo_root, dry_run=dry_run, written=written)
