"""Install the specyrd command skills (or stubs) that delegate to the specy-road CLI."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from specy_road import __version__
from specy_road.agent_guide_block import AGENT_GUIDE, GUIDE_AGENTS, apply_guide_and_report  # noqa: F401 — re-exported
from specy_road.agent_ignores import apply_and_report
from specy_road.specyrd_skills import (  # noqa: F401 — re-exported for refresh_stubs
    SKILLS_REL,
    _package_templates_dir,
    _read_template,
    install_stubs as _append_command_stub_installs,
    managed_paths,
    owned_paths,
)
from specy_road.runtime_paths import (
    discover_project_root,
    prefix_within,
    recorded_project_root,
)

AGENT_CHOICES = frozenset({"cursor", "claude-code", "codex", "generic"})
ROLE_CHOICES = frozenset({"pm", "dev", "both"})

DEFAULT_GUI_SETTINGS_JSON = (
    '{\n  "llm": {\n    "backend": "openai",\n    "openai_api_key": "",\n'
    '    "openai_model": "gpt-4o-mini",\n    "openai_base_url": "",\n'
    '    "azure_endpoint": "",\n    "azure_api_key": "",\n'
    '    "azure_deployment": "",\n    "azure_api_version": "2024-02-15-preview",\n'
    '    "anthropic_api_key": "",\n    "anthropic_model": "",\n'
    '    "anthropic_max_output_tokens": ""\n'
    "  },\n"
    '  "git_remote": {\n    "provider": "github",\n    "repo": "",\n'
    '    "token": "",\n    "base_url": ""\n  }\n}\n'
)

# Where a pack's command files live, relative to the repo root. The skill packs
# share one directory (see specyrd_skills); generic uses --ai-commands-dir.
AGENT_REL_DEST: dict[str, Path | None] = {
    "cursor": SKILLS_REL,
    "claude-code": SKILLS_REL,
    "codex": SKILLS_REL,
    "generic": None,
}

# All available command stubs.
COMMAND_FILES = (
    "specyrd-validate.md",
    "specyrd-brief.md",
    "specyrd-export.md",
    "specyrd-file-limits.md",
    "specyrd-author.md",
    "specyrd-constitution.md",
    "specyrd-claim.md",
    "specyrd-mark-reviewed.md",
    "specyrd-review-packet.md",
    "specyrd-review-record.md",
    "specyrd-handoff-status.md",
    "specyrd-prompt.md",
    "specyrd-orchestrate.md",
    "specyrd-finish.md",
    "specyrd-do-next-task.md",
    "specyrd-grind-session.md",
    "specyrd-abort-task-pickup.md",
    "specyrd-sync.md",
    "specyrd-list-nodes.md",
    "specyrd-show-node.md",
    "specyrd-add-node.md",
    "specyrd-review-node.md",
    "specyrd-brainstorm.md",
    "specyrd-search.md",
    "specyrd-digest.md",
    "specyrd-history.md",
)

# Stubs installed per role; omit to install all.
ROLE_COMMAND_FILES: dict[str, tuple[str, ...]] = {
    "pm": (
        "specyrd-validate.md",
        "specyrd-export.md",
        "specyrd-author.md",
        "specyrd-constitution.md",
        "specyrd-sync.md",
        "specyrd-list-nodes.md",
        "specyrd-show-node.md",
        "specyrd-add-node.md",
        "specyrd-review-node.md",
        "specyrd-orchestrate.md",
        "specyrd-brainstorm.md",
        "specyrd-search.md",
        "specyrd-digest.md",
        "specyrd-history.md",
    ),
    "dev": (
        "specyrd-validate.md",
        "specyrd-brief.md",
        "specyrd-claim.md",
        "specyrd-mark-reviewed.md",
        "specyrd-review-packet.md",
        "specyrd-review-record.md",
        "specyrd-handoff-status.md",
        "specyrd-prompt.md",
        "specyrd-orchestrate.md",
        "specyrd-finish.md",
        "specyrd-do-next-task.md",
        "specyrd-grind-session.md",
        "specyrd-abort-task-pickup.md",
        "specyrd-search.md",
        "specyrd-digest.md",
        "specyrd-history.md",
    ),
}


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
    if "specyrd_version" not in data:
        data["specyrd_version"] = __version__
    return data


def _load_manifest(repo_root: Path) -> dict[str, Any]:
    """Load ``.specyrd/manifest.json``."""
    primary = repo_root / ".specyrd" / "manifest.json"
    empty: dict[str, Any] = {"specyrd_version": __version__, "agents": {}}

    def _parse(path: Path) -> dict[str, Any] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        data = _normalize_manifest_dict(raw)
        if "agents" not in data or not isinstance(data["agents"], dict):
            data["agents"] = {}
        return data

    if primary.is_file():
        return _parse(primary) or empty
    return empty


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


def _write_readme_and_gui_stub(
    repo_root: Path,
    *,
    force: bool,
    dry_run: bool,
    gui_settings_stub: bool,
    written: list[str],
    skipped: list[str],
) -> None:
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

    # Never overwritten, not even with --force: this file lives in $HOME rather
    # than the repo, holds the user's API keys, is absent from the manifest, and
    # `git checkout --` cannot bring it back.
    if not gui_settings_stub:
        return
    gui_home = Path.home() / ".specy-road" / "gui-settings.json"
    gui_display = "~/.specy-road/gui-settings.json"
    if gui_home.is_file():
        skipped.append(gui_display)
        return
    if dry_run:
        written.append(gui_display)
        return
    gui_home.parent.mkdir(parents=True, exist_ok=True)
    gui_home.write_text(DEFAULT_GUI_SETTINGS_JSON, encoding="utf-8")
    written.append(gui_display)


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
    _append_command_stub_installs(
        repo_root, rel_dest, files_to_install, force, dry_run, written, skipped, agent=agent
    )
    _write_readme_and_gui_stub(
        repo_root,
        force=force,
        dry_run=dry_run,
        gui_settings_stub=gui_settings_stub,
        written=written,
        skipped=skipped,
    )

    # The project tree may sit below the checkout (the nested layout). Prefer
    # the root `init project` recorded: discovery only walks *upward*, so run
    # from the git root of a nested repo it cannot see `sr/` at all — which is
    # how the ignore blocks came out unprefixed.
    project = recorded_project_root(repo_root) or discover_project_root(target)
    prefix = prefix_within(repo_root, project or repo_root)

    # Both managed blocks report under --dry-run too: a dry run that silently
    # omitted them is what let the CLAUDE.md overwrite go unnoticed.
    if write_claude_md:
        apply_guide_and_report(
            repo_root, prefix, written, agent=agent, dry_run=dry_run
        )
    apply_and_report(repo_root, prefix, written, dry_run=dry_run)

    if not dry_run:
        _record_manifest(
            repo_root,
            manifest,
            agent=agent,
            managed=owned_paths(managed_paths(rel_dest, files_to_install, agent=agent), skipped,
                                {p for paths in (manifest.get("agents") or {}).values() for p in paths}),
            role=role,
            prefix=prefix,
        )

    return InitResult(written=written, skipped=skipped, dry_run=dry_run)


def _record_manifest(
    repo_root: Path,
    manifest: dict[str, Any],
    *,
    agent: str,
    managed: list[str],
    role: str | None,
    prefix: str,
) -> None:
    agents: dict[str, list[str]] = manifest.setdefault("agents", {})
    agents[agent] = managed
    if role is not None:
        manifest["role"] = role
    manifest["project_root"] = prefix.rstrip("/") or "."
    _save_manifest(repo_root, manifest)
