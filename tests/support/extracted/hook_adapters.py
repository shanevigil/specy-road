"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import json
from tests.helpers import script_subprocess_env
import subprocess
from tests.support.cli import run_cli
from tests.helpers import REPO

#: The stdin each harness sends for a shell command, as documented.
def pre_tool_use(cmd: str) -> dict:
    """Shared test helper."""
    return {
        "session_id": "abc", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp", "permission_mode": "default",
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "toolu_1",
        "tool_input": {"command": cmd, "description": "x", "timeout": 120000},
    }

PAYLOADS = {
    "generic": lambda cmd: {"command": cmd},
    "claude-code": pre_tool_use,
    "codex": pre_tool_use,
    "cursor": lambda cmd: {"conversation_id": "c", "generation_id": "g", "hook_event_name": "beforeShellExecution",
                           "workspace_roots": ["/tmp"], "command": cmd, "cwd": "/tmp", "sandbox": False},
}

#: How each harness reads a deny and an allow, per its docs.
DENY = {   # (exit code, where the reason appears)
    "generic": (2, "stderr"), "claude-code": (2, "stderr"), "codex": (2, "stderr"), "cursor": (0, "stdout"),
}

def run(repo: Path, fmt: str, payload: dict, *extra: str) -> subprocess.CompletedProcess[str]:
    """Shared test helper."""
    env = script_subprocess_env()
    env["SPECY_ROAD_AGENT_ID"] = "me"
    argv = ["session", "guard", "--format", fmt, *extra, "--repo-root", str(repo)]
    return run_cli(argv, input=json.dumps(payload), env=env, cwd=REPO)
