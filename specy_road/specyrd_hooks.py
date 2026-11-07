"""Install checked-in orchestration guard hooks and optional git pre-push (M8.5)."""

from __future__ import annotations

import json
import os
import stat
from importlib import resources
from pathlib import Path
from typing import Any

from specy_road import safe_write
from specy_road.specyrd_skills import _package_templates_dir

HOOKS_REL = Path("templates/specyrd/hooks")
PRE_PUSH_NAME = "pre-push"
_HARNESS_HOOK_FILES = {
    "claude-code": (Path("claude-code") / "settings.json", Path(".claude") / "settings.json"),
    "codex": (Path("codex") / "hooks.json", Path(".codex") / "hooks.json"),
    "cursor": (Path("cursor") / "hooks.json", Path(".cursor") / "hooks.json"),
}


def hook_destinations(repo_root: Path, agent: str, *, guard_hooks: bool, pre_push: bool) -> list[Path]:
    """Every path the opt-in hook installs would write, for a preflight before ``specyrd init`` changes anything."""
    out: list[Path] = []
    if guard_hooks and agent in _HARNESS_HOOK_FILES:
        out += [repo_root / _HARNESS_HOOK_FILES[agent][1], repo_root / ".specyrd" / "hooks" / agent / "README.md"]
    if pre_push:
        out.append(repo_root / ".git" / "hooks" / PRE_PUSH_NAME)
    return out


def _hooks_template_dir() -> Path:
    pkg = _package_templates_dir()
    d = pkg / "hooks"
    if d.is_dir():
        return d
    return Path(str(resources.files("specy_road").joinpath("templates", "specyrd", "hooks")))


def _merge_json_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in patch.items():
        if key not in out:
            out[key] = val
            continue
        if isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _merge_json_dict(out[key], val)
        elif isinstance(out[key], list) and isinstance(val, list):
            out[key] = out[key] + val
        else:
            out[key] = val
    return out


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(repo_root: Path, path: Path, data: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    safe_write.write(repo_root, path, json.dumps(data, indent=2) + "\n")


def install_orchestration_hooks(
    repo_root: Path,
    agent: str,
    *,
    dry_run: bool = False,
    written: list[str] | None = None,
) -> None:
    """Merge the one shipped hook snippet for ``agent`` (role comes from the environment)."""
    written = written if written is not None else []
    pair = _HARNESS_HOOK_FILES.get(agent)
    if pair is None:
        return
    src_rel, dest_rel = pair
    snippet = _load_json(_hooks_template_dir() / src_rel)
    dest = safe_write.check(repo_root, repo_root / dest_rel)   # read below only once it is no link
    merged = _merge_json_dict(_load_json(dest), snippet)
    _write_json(repo_root, dest, merged, dry_run=dry_run)
    written.append(str(dest.relative_to(repo_root)))
    readme = _hooks_template_dir() / "README.md"
    if readme.is_file():
        target = repo_root / ".specyrd" / "hooks" / agent / "README.md"
        if not dry_run:
            safe_write.write(repo_root, target, readme.read_text(encoding="utf-8"))
        written.append(str(target.relative_to(repo_root)))


def install_pre_push_hook(
    repo_root: Path,
    *,
    dry_run: bool = False,
    written: list[str] | None = None,
) -> None:
    script = _hooks_template_dir() / PRE_PUSH_NAME
    dest = repo_root / ".git" / "hooks" / PRE_PUSH_NAME
    written = written if written is not None else []
    rel = f".git/hooks/{PRE_PUSH_NAME}"
    if dry_run:
        written.append(rel)
        return
    if not script.is_file():
        raise FileNotFoundError(f"missing hook template {script}")
    dest = safe_write.check(repo_root, dest)
    if dest.is_file():   # no link (checked): keep the file's own mode, as write_text did
        mode = stat.S_IMODE(os.lstat(dest).st_mode)
    else:
        umask = os.umask(0o022)
        os.umask(umask)
        mode = 0o666 & ~umask
    text = script.read_text(encoding="utf-8")
    safe_write.write(repo_root, dest, text, mode=mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    written.append(rel)
