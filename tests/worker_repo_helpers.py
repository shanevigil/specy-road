"""A review repo whose roster runs a fake harness, for ``specy-road worker`` tests.

Promoted from ``tests/test_worker_cli.py`` so worker tests in other modules
share one setup through public names.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.review_repo_helpers import git, make_review_repo

FAKE = '''
import json, sys, time
spec = json.loads(open(sys.argv[1]).read()) if sys.argv[1].endswith(".json") else {"lines": [
    {"type": "system", "subtype": "init", "session_id": "s-" + str(len(sys.argv)), "model": "fake"},
    {"type": "result", "subtype": "success", "result": "done", "session_id": "s-" + str(len(sys.argv))}]}
if spec.get("write"):                       # a READY written during the turn, as a real harness would
    open(spec["write"]["path"], "w").write(spec["write"]["text"])
for d in spec["lines"]:
    print(json.dumps(d), flush=True)
time.sleep(spec.get("sleep", 0))
sys.exit(spec.get("exit", 0))
'''


def worker_roster(cli: str, *, max_workers: int = 2) -> str:
    return (f"version: 1\nroster:\n  - {{id: human, family: human, roles: [coordinator, reviewer]}}\n"
            f"  - {{id: opus, family: anthropic, roles: [executor, reviewer], harness: claude-code,\n"
            f"     billing_route: claude_subscription, channels: {{cli: '{cli}'}}}}\n"
            f"  - {{id: sol, family: openai, roles: [reviewer]}}\n"
            f"policy: {{max_workers: {max_workers}}}\n")


def make_worker_repo(tmp_path: Path, *, max_workers: int = 2) -> tuple[Path, Path]:
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}", max_workers=max_workers))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    return repo, script
