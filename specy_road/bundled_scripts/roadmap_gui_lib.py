"""PM GUI helpers: settings paths, registry resolution, LLM env (FastAPI + scripts)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure sibling script imports work when this module is loaded first
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import yaml
from roadmap_chunk_utils import iter_roadmap_fingerprint_files
from roadmap_gui_settings import (  # noqa: F401 (re-exported for tests and gui routes)
    SETTINGS_DIR,
    SETTINGS_FILE_VERSION,
    SETTINGS_PATH,
    default_settings,
    effective_settings_for_repo,
    load_settings,
    repo_settings_id,
    save_settings,
    save_settings_for_repo,
    settings_api_payload,
)


def resolve_repo_root(fallback: Path) -> Path:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=fallback,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(r.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return fallback


def _apply_azure_llm_env(llm: dict[str, Any]) -> None:
    if not os.environ.get("SPECY_ROAD_AZURE_OPENAI_ENDPOINT"):
        ep = (llm.get("azure_endpoint") or "").strip()
        if ep:
            os.environ["SPECY_ROAD_AZURE_OPENAI_ENDPOINT"] = ep
    if not os.environ.get("SPECY_ROAD_AZURE_OPENAI_API_KEY"):
        k = (llm.get("azure_api_key") or "").strip()
        if k:
            os.environ["SPECY_ROAD_AZURE_OPENAI_API_KEY"] = k
    # Deployment name must refresh on every apply: the GUI sends the current value
    # and the FastAPI process reuses os.environ, so "only if unset" would stick forever.
    d = (llm.get("azure_deployment") or "").strip()
    if d:
        os.environ["SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT"] = d
    ver = (llm.get("azure_api_version") or "").strip()
    if ver and not os.environ.get("SPECY_ROAD_OPENAI_API_VERSION"):
        os.environ["SPECY_ROAD_OPENAI_API_VERSION"] = ver


def _apply_openai_llm_env(llm: dict[str, Any], backend: str) -> None:
    if not os.environ.get("SPECY_ROAD_OPENAI_API_KEY"):
        k = (llm.get("openai_api_key") or "").strip()
        if k:
            os.environ["SPECY_ROAD_OPENAI_API_KEY"] = k
    m = (llm.get("openai_model") or "").strip()
    if m:
        os.environ["SPECY_ROAD_OPENAI_MODEL"] = m
    base = (llm.get("openai_base_url") or "").strip()
    if base and backend == "compatible" and not os.environ.get("SPECY_ROAD_OPENAI_BASE_URL"):
        os.environ["SPECY_ROAD_OPENAI_BASE_URL"] = base


def _apply_anthropic_llm_env(llm: dict[str, Any]) -> None:
    if not os.environ.get("SPECY_ROAD_ANTHROPIC_API_KEY"):
        k = (llm.get("anthropic_api_key") or "").strip()
        if k:
            os.environ["SPECY_ROAD_ANTHROPIC_API_KEY"] = k
    # Model must refresh on every apply; see _apply_azure_llm_env deployment note.
    m = (llm.get("anthropic_model") or "").strip()
    if m:
        os.environ["SPECY_ROAD_ANTHROPIC_MODEL"] = m
    # Anthropic Messages API requires max_tokens; map saved GUI value to env.
    mt = str(llm.get("anthropic_max_output_tokens") or "").strip()
    if mt:
        os.environ["SPECY_ROAD_ANTHROPIC_MAX_TOKENS"] = mt


def apply_llm_env_from_settings(llm: dict[str, Any]) -> None:
    """Inject saved LLM config into env for review_node.

    API keys and endpoints follow "existing env wins if already set" so a shell
    export before starting the GUI still overrides file-backed defaults. Model
    name (and Azure deployment) always update from ``llm`` when non-empty so
    switching models in Settings works without restarting the server.
    """
    backend = (llm.get("backend") or "openai").strip().lower()
    if backend == "azure":
        _apply_azure_llm_env(llm)
    elif backend == "anthropic":
        _apply_anthropic_llm_env(llm)
    else:
        _apply_openai_llm_env(llm, backend)


def load_registry(root: Path) -> dict[str, Any]:
    p = root / "roadmap" / "registry.yaml"
    if not p.is_file():
        return {"version": 1, "entries": []}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def registry_by_node_id(reg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in reg.get("entries") or []:
        if isinstance(e, dict) and e.get("node_id"):
            out[str(e["node_id"])] = e
    return out


def roadmap_fingerprint(root: Path) -> int:
    h = 0
    for p in iter_roadmap_fingerprint_files(root):
        try:
            h += p.stat().st_mtime_ns
        except OSError:
            continue
    reg = root / "roadmap" / "registry.yaml"
    if reg.is_file():
        try:
            h += reg.stat().st_mtime_ns
        except OSError:
            pass
    try:
        gr = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if gr.returncode == 0 and (sha := gr.stdout.strip()):
            h += int.from_bytes(
                hashlib.sha256(sha.encode("utf-8")).digest()[:8],
                "little",
            )
    except OSError:
        pass
    return h


def iter_pm_gui_extra_fingerprint_files(root: Path) -> list[Path]:
    """Paths whose edits should invalidate the PM GUI mutation token (planning, vision, constitution, shared)."""
    root = root.resolve()
    out: list[Path] = []
    planning = root / "planning"
    if planning.is_dir():
        for p in sorted(planning.rglob("*.md")):
            if p.is_file():
                out.append(p)
    constitution = root / "constitution"
    if constitution.is_dir():
        for p in sorted(constitution.rglob("*.md")):
            if p.is_file():
                out.append(p)
    vision = root / "vision.md"
    if vision.is_file():
        out.append(vision)
    shared = root / "shared"
    if shared.is_dir():
        for p in sorted(shared.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            out.append(p)
    return sorted(set(out), key=lambda x: str(x))


def pm_gui_mutation_fingerprint_base(root: Path) -> int:
    """Roadmap fingerprint plus PM-edited paths outside ``roadmap/`` (for optimistic concurrency)."""
    h = roadmap_fingerprint(root)
    for p in iter_pm_gui_extra_fingerprint_files(root):
        try:
            h += p.stat().st_mtime_ns
        except OSError:
            continue
    return h
