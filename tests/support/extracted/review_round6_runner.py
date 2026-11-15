"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import json
import sys
from specy_road.orchestration.workers import worker_adapters as wa

OK = [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]

def _launch(tmp_path: Path, script: Path, repo: Path, name: str, **spec):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"lines": OK, **spec}))
    return wa.adapter_for("claude-code").launch(p, repo, "opus", f"{sys.executable} {script} {{prompt}}")
