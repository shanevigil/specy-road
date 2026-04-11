"""PM GUI helpers: settings paths, registry resolution, LLM env (FastAPI + scripts)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Ensure sibling script imports work when this module is loaded first
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import yaml
from roadmap_chunk_utils import iter_roadmap_fingerprint_files
from roadmap_gui_settings import (
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

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[misc, assignment]
    FileSystemEventHandler = None  # type: ignore[misc, assignment]

_WATCHDOG_LOCK = threading.Lock()
_WATCHDOG_STARTED = False
_WATCH_OBS_HOLD: list[Any] = []

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
    if not os.environ.get("SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT"):
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
    if not os.environ.get("SPECY_ROAD_OPENAI_MODEL"):
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
    if not os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL"):
        m = (llm.get("anthropic_model") or "").strip()
        if m:
            os.environ["SPECY_ROAD_ANTHROPIC_MODEL"] = m


def apply_llm_env_from_settings(llm: dict[str, Any]) -> None:
    """Inject saved LLM config into env for review_node (env vars still win if pre-set)."""
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
    return h


def _run_watchdog_observer(root: Path, bump: list[float]) -> None:
    if Observer is None or FileSystemEventHandler is None:
        return
    roadmap_dir = root / "roadmap"
    if not roadmap_dir.is_dir():
        return

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):  # type: ignore[override]
            if event.is_directory:
                return
            p = getattr(event, "src_path", "")
            if p.endswith((".yaml", ".yml", ".json", ".md")):
                bump[0] = time.time()

    try:
        obs = Observer()
        obs.schedule(Handler(), str(roadmap_dir), recursive=True)
        obs.start()
        _WATCH_OBS_HOLD.append(obs)
    except Exception:
        pass


def ensure_watchdog_thread(root: Path, bump: list[float]) -> None:
    global _WATCHDOG_STARTED
    with _WATCHDOG_LOCK:
        if _WATCHDOG_STARTED:
            return
        _WATCHDOG_STARTED = True
    threading.Thread(
        target=_run_watchdog_observer,
        args=(root, bump),
        daemon=True,
    ).start()
