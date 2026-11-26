"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import json

RECORDED = json.loads((Path(__file__).resolve().parents[2] / "fixtures/worker_usage/turn_end_lines.json").read_text())

CLAUDE_RESULT, CODEX_TURN, CURSOR_RESULT = (RECORDED[h]["lines"][i] for h, i in (("claude-code", 1), ("codex", -1), ("cursor", -1)))

FULL_INIT = {"type": "system", "subtype": "init", "session_id": "s1", "model": "opus", "claude_code_version": "2.1.300",
             "tools": ["Bash", "Read", "Edit", "Write", "Skill"], "mcp_servers": [{"name": "docs", "status": "connected"}],
             "plugins": [{"name": "lint", "path": "/p"}]}

import sys
from specy_road.orchestration.workers import worker_adapters as wa

OK = [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]

def launch(tmp_path: Path, script: Path, repo: Path, name: str, **spec):
    """Shared test helper."""
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"lines": OK, **spec}))
    return wa.adapter_for("claude-code").launch(p, repo, "opus", f"{sys.executable} {script} {{prompt}}")
