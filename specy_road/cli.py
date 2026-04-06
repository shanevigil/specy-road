"""Console entrypoint: thin wrappers around scripts/."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(script: str, args: list[str]) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *args]
    subprocess.check_call(cmd)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "Usage: specy-road <command> [args...]\n"
            "\n"
            "Authoring / validation:\n"
            "  validate             — validate roadmap YAML and registry\n"
            "  brief <NODE_ID>      — generate focused brief for a node\n"
            "  export               — regenerate roadmap.md and phase files\n"
            "  file-limits          — check line-count constraints\n"
            "\n"
            "Dev task loop:\n"
            "  do-next-available-task  — pick a task, branch, register\n"
            "  finish-this-task        — complete task, validate, commit\n",
        )
        raise SystemExit(0 if not argv else 2)
    cmd, *rest = argv
    if cmd == "validate":
        _run("validate_roadmap.py", rest)
    elif cmd == "brief":
        _run("generate_brief.py", rest)
    elif cmd == "export":
        _run("export_roadmap_md.py", rest)
    elif cmd == "file-limits":
        _run("validate_file_limits.py", rest)
    elif cmd == "do-next-available-task":
        _run("do_next_task.py", rest)
    elif cmd == "finish-this-task":
        _run("finish_task.py", rest)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
