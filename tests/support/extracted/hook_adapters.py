"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import json
from tests.helpers import script_subprocess_env
import subprocess
import sys
from tests.helpers import REPO

def _pre_tool_use(cmd: str) -> dict:
    return {
        "session_id": "abc", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp", "permission_mode": "default",
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "toolu_1",
        "tool_input": {"command": cmd, "description": "x", "timeout": 120000},
    }

PAYLOADS = {
    "generic": lambda cmd: {"command": cmd},
    "claude-code": _pre_tool_use,
    "codex": _pre_tool_use,
    "cursor": lambda cmd: {"conversation_id": "c", "generation_id": "g", "hook_event_name": "beforeShellExecution",
                           "workspace_roots": ["/tmp"], "command": cmd, "cwd": "/tmp", "sandbox": False},
}

DENY = {   # (exit code, where the reason appears)
    "generic": (2, "stderr"), "claude-code": (2, "stderr"), "codex": (2, "stderr"), "cursor": (0, "stdout"),
}

def _run(repo: Path, fmt: str, payload: dict, *extra: str) -> subprocess.CompletedProcess[str]:
    env = script_subprocess_env()
    env["SPECY_ROAD_AGENT_ID"] = "me"
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "session", "guard", "--format", fmt, *extra, "--repo-root", str(repo)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=REPO, check=False,
    )
