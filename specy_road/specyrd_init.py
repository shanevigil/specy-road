"""Install IDE command stubs that delegate to specy-road CLI or scripts."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from specy_road import __version__

AGENT_CHOICES = frozenset({"cursor", "claude-code", "generic"})
ROLE_CHOICES = frozenset({"pm", "dev", "both"})

DEFAULT_GUI_SETTINGS_JSON = (
    '{\n  "llm": {\n    "backend": "openai",\n    "openai_api_key": "",\n'
    '    "openai_model": "gpt-4o-mini",\n    "openai_base_url": "",\n'
    '    "azure_endpoint": "",\n    "azure_api_key": "",\n'
    '    "azure_deployment": "",\n    "azure_api_version": "2024-02-15-preview"\n'
    "  },\n"
    '  "git_remote": {\n    "provider": "github",\n    "repo": "",\n'
    '    "token": "",\n    "base_url": ""\n  }\n}\n'
)

# Relative to repo root per agent (generic uses --ai-commands-dir).
AGENT_REL_DEST: dict[str, Path | None] = {
    "cursor": Path(".cursor/commands"),
    "claude-code": Path(".claude/commands"),
    "generic": None,
}

# All available command stubs.
COMMAND_FILES = (
    "specyrd-validate.md",
    "specyrd-brief.md",
    "specyrd-export.md",
    "specyrd-file-limits.md",
    "specyrd-author.md",
    "specyrd-claim.md",
    "specyrd-finish.md",
    "specyrd-do-next-task.md",
    "specyrd-sync.md",
    "specyrd-list-nodes.md",
    "specyrd-show-node.md",
    "specyrd-add-node.md",
    "specyrd-review-node.md",
)

# Stubs installed per role; omit to install all.
ROLE_COMMAND_FILES: dict[str, tuple[str, ...]] = {
    "pm": (
        "specyrd-validate.md",
        "specyrd-export.md",
        "specyrd-author.md",
        "specyrd-sync.md",
        "specyrd-list-nodes.md",
        "specyrd-show-node.md",
        "specyrd-add-node.md",
        "specyrd-review-node.md",
    ),
    "dev": (
        "specyrd-validate.md",
        "specyrd-brief.md",
        "specyrd-claim.md",
        "specyrd-finish.md",
        "specyrd-do-next-task.md",
    ),
}


def _package_templates_dir() -> Path:
    """Package directory for templates/specyrd/..."""
    return Path(__file__).resolve().parent / "templates" / "specyrd"


def _commands_traversable():
    """Traversable for packaged command templates (filesystem fallback)."""
    return resources.files("specy_road").joinpath(
        "templates", "specyrd", "commands"
    )


def resolve_repo_root(start: Path) -> Path:
    """Prefer git worktree root; else the resolved start path."""
    start = start.resolve()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(r.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return start


def _read_template(name: str) -> str:
    """Load a command template; substitute version placeholder."""
    pkg_dir = _package_templates_dir()
    path = pkg_dir / "commands" / name
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        t = _commands_traversable() / name
        text = t.read_text(encoding="utf-8")
    return text.replace("{{SPECYRD_VERSION}}", __version__)


def _read_claude_template() -> str:
    pkg_dir = _package_templates_dir()
    path = pkg_dir / "CLAUDE.md.template"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        resources.files("specy_road")
        .joinpath("templates", "specyrd", "CLAUDE.md.template")
        .read_text(encoding="utf-8")
    )


def _read_dot_specyrd_readme() -> str:
    pkg_dir = _package_templates_dir()
    path = pkg_dir / "dot-specyrd" / "README.md"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        text = (
            resources.files("specy_road")
            .joinpath("templates", "specyrd", "dot-specyrd", "README.md")
            .read_text(encoding="utf-8")
        )
    return text.replace("{{SPECYRD_VERSION}}", __version__)


@dataclass
class InitResult:
    written: list[str]
    skipped: list[str]
    dry_run: bool


def _normalize_manifest_dict(data: dict[str, Any]) -> dict[str, Any]:
    if "specyr_version" in data and "specyrd_version" not in data:
        data["specyrd_version"] = data.pop("specyr_version")
    if "specyrd_version" not in data:
        data["specyrd_version"] = __version__
    return data


def _load_manifest(repo_root: Path) -> dict[str, Any]:
    primary = repo_root / ".specyrd" / "manifest.json"
    legacy = repo_root / ".specyr" / "manifest.json"
    path = primary if primary.is_file() else legacy
    if not path.is_file():
        return {"specyrd_version": __version__, "agents": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"specyrd_version": __version__, "agents": {}}
    data = _normalize_manifest_dict(data)
    if "agents" not in data or not isinstance(data["agents"], dict):
        data["agents"] = {}
    return data


def _save_manifest(repo_root: Path, data: dict[str, Any]) -> None:
    path = repo_root / ".specyrd" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data["specyrd_version"] = __version__
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _validate_generic_commands_dir(repo_root: Path, rel: Path) -> Path:
    if rel.is_absolute():
        raise ValueError(
            "--ai-commands-dir must be relative to the repository root"
        )
    if ".." in rel.parts:
        raise ValueError("--ai-commands-dir must not contain '..'")
    resolved = (repo_root / rel).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as e:
        raise ValueError(
            "--ai-commands-dir must resolve inside the repository root"
        ) from e
    return rel


def run_init(
    *,
    target: Path,
    agent: str,
    dry_run: bool,
    force: bool,
    ai_commands_dir: Path | None,
    role: str | None = None,
    write_claude_md: bool = False,
    gui_settings_stub: bool = False,
) -> InitResult:
    if agent not in AGENT_CHOICES:
        raise ValueError(f"unknown agent: {agent}")
    if role is not None and role not in ROLE_CHOICES:
        raise ValueError(
            f"unknown role: {role!r}; choose pm, dev, or both",
        )
    if agent == "generic":
        if ai_commands_dir is None:
            raise ValueError("--ai-commands-dir is required when --ai generic")
        rel_dest = ai_commands_dir
    else:
        rel_dest = AGENT_REL_DEST[agent]
        assert rel_dest is not None

    repo_root = resolve_repo_root(target)
    if agent == "generic":
        rel_dest = _validate_generic_commands_dir(repo_root, rel_dest)

    written: list[str] = []
    skipped: list[str] = []

    manifest = _load_manifest(repo_root)

    if role in ("pm", "dev"):
        files_to_install = ROLE_COMMAND_FILES[role]
    else:
        files_to_install = COMMAND_FILES
    for name in files_to_install:
        rel_file = rel_dest / name
        dest_file = repo_root / rel_file
        if dest_file.is_file() and not force:
            skipped.append(str(rel_file))
            continue
        content = _read_template(name)
        if dry_run:
            written.append(str(rel_file))
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(content, encoding="utf-8")
        written.append(str(rel_file))

    readme_rel = Path(".specyrd/README.md")
    readme_path = repo_root / readme_rel
    if readme_path.is_file() and not force:
        skipped.append(str(readme_rel))
    else:
        readme_content = _read_dot_specyrd_readme()
        if dry_run:
            written.append(str(readme_rel))
        else:
            readme_path.parent.mkdir(parents=True, exist_ok=True)
            readme_path.write_text(readme_content, encoding="utf-8")
            written.append(str(readme_rel))

    claude_rel = Path("CLAUDE.md")
    claude_path = repo_root / claude_rel
    if write_claude_md and agent == "claude-code":
        if claude_path.is_file() and not force:
            skipped.append(str(claude_rel))
        else:
            body = _read_claude_template()
            if dry_run:
                written.append(str(claude_rel))
            else:
                claude_path.write_text(body, encoding="utf-8")
                written.append(str(claude_rel))

    gui_home = Path.home() / ".specy-road" / "gui-settings.json"
    if gui_settings_stub:
        gui_display = "~/.specy-road/gui-settings.json"
        if dry_run:
            written.append(gui_display)
        elif not gui_home.is_file() or force:
            gui_home.parent.mkdir(parents=True, exist_ok=True)
            gui_home.write_text(DEFAULT_GUI_SETTINGS_JSON, encoding="utf-8")
            written.append(gui_display)

    if not dry_run:
        agents: dict[str, list[str]] = manifest.setdefault("agents", {})
        cmd_paths = [str(rel_dest / n) for n in files_to_install]
        canonical = cmd_paths + [str(readme_rel)]
        agents[agent] = canonical
        if role is not None:
            manifest["role"] = role
        _save_manifest(repo_root, manifest)

    return InitResult(written=written, skipped=skipped, dry_run=dry_run)
