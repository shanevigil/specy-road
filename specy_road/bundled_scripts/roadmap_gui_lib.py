"""PM GUI helpers: settings paths, registry resolution, LLM env (FastAPI + scripts)."""

from __future__ import annotations

import base64
import json
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

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[misc, assignment]
    FileSystemEventHandler = None  # type: ignore[misc, assignment]

_WATCHDOG_LOCK = threading.Lock()
_WATCHDOG_STARTED = False
_WATCH_OBS_HOLD: list[Any] = []

SETTINGS_DIR = Path.home() / ".specy-road"
SETTINGS_PATH = SETTINGS_DIR / "gui-settings.json"


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
        if isinstance(v, str) and v.startswith("__b64__:"):
            try:
                base["llm"][key] = _b64_decode(v[len("__b64__:") :])
            except (ValueError, UnicodeDecodeError):
                base["llm"][key] = ""
    tok = base["git_remote"].get("token") or ""
    if isinstance(tok, str) and tok.startswith("__b64__:"):
        try:
            base["git_remote"]["token"] = _b64_decode(tok[len("__b64__:") :])
        except (ValueError, UnicodeDecodeError):
            base["git_remote"]["token"] = ""


def load_settings() -> dict[str, Any]:
    base = default_settings()
    if not SETTINGS_PATH.is_file():
        return base
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(raw, dict):
        return base
    for section in ("llm", "git_remote"):
        if isinstance(raw.get(section), dict):
            base[section].update(raw[section])
    _merge_token_fields(base)
    return base


def save_settings(data: dict[str, Any]) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = json.loads(json.dumps(data))
    for key in ("openai_api_key", "azure_api_key", "anthropic_api_key"):
        v = out["llm"].get(key) or ""
        if v:
            out["llm"][key] = "__b64__:" + _b64_encode(str(v))
    tok = out["git_remote"].get("token") or ""
    if tok:
        out["git_remote"]["token"] = "__b64__:" + _b64_encode(str(tok))
    SETTINGS_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


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
