"""Console entrypoint: thin wrappers around scripts/."""

from __future__ import annotations

import os
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
            "  validate             — validate merged roadmap graph and registry\n"
            "  brief <NODE_ID>      — generate focused brief for a node\n"
            "  export               — regenerate roadmap.md index from merged graph\n"
            "  file-limits          — check line-count constraints\n"
            "\n"
            "PM workflow:\n"
            "  sync                 — fetch/merge integration branch, validate, export\n"
            "    (optional: --base BRANCH --remote NAME | --no-git)\n"
            "  list-nodes           — list nodes and chunk paths (pass-through to roadmap CRUD)\n"
            "  show-node <NODE_ID>\n"
            "  add-node ...         — see: python scripts/roadmap_crud.py add-node -h\n"
            "  edit-node ...\n"
            "  archive-node ...\n"
            "  review-node <NODE_ID> — advisory LLM review (requires pip install specy-road[review])\n"
            "  scaffold-planning <NODE_ID> — create planning/<id>/ overview.md, plan.md, tasks.md; set planning_dir\n"
            "    (optional: --planning-dir PATH --task-id SUB_ID --force; see scripts/scaffold_planning.py -h)\n"
            "  gui — FastAPI + Gantt PM UI (requires pip install 'specy-road[gui-next]'; run npm build in gui/pm-gantt first)\n"
            "\n"
            "Dev task loop:\n"
            "  do-next-available-task  — pick a task, sync base, branch, register\n"
            "    (optional: --base BRANCH --remote NAME | --no-sync)\n"
            "  finish-this-task        — complete task, validate, commit\n"
            "    (optional: --push [--remote NAME])\n",
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
    elif cmd == "sync":
        _run("pm_sync.py", rest)
    elif cmd in (
        "list-nodes",
        "show-node",
        "add-node",
        "edit-node",
        "archive-node",
    ):
        _run("roadmap_crud.py", [cmd, *rest])
    elif cmd == "review-node":
        _run("review_node.py", rest)
    elif cmd == "scaffold-planning":
        _run("scaffold_planning.py", rest)
    elif cmd == "gui":
        import argparse
        import importlib.util

        p = argparse.ArgumentParser(prog="specy-road gui")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument(
            "--repo-root",
            type=Path,
            default=None,
            help="Repository root (default: git discovery / cwd)",
        )
        ns = p.parse_args(rest)
        uvicorn_spec = importlib.util.find_spec("uvicorn")
        if uvicorn_spec is None:
            print(
                "error: FastAPI GUI needs uvicorn. From the **specy-road repository root**, run:\n"
                '  pip install -e ".[gui-next]"\n'
                "Then build the SPA once:\n"
                "  cd gui/pm-gantt && npm install && npm run build && cd ../..\n"
                "If `pip` still says the extra `gui-next` is missing, your install is stale — "
                "use editable install from the clone that contains `pyproject.toml`, not only `pip install specy-road`.\n"
                "Use `cd` to the repo root before `cd gui/pm-gantt` (not from gui-spike/react-flow-spike).",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        env = os.environ.copy()
        if ns.repo_root is not None:
            env["SPECY_ROAD_REPO_ROOT"] = str(ns.repo_root.resolve())
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "specy_road.gui_app:app",
                "--host",
                ns.host,
                "--port",
                str(ns.port),
            ],
            cwd=Path.cwd(),
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "") + (proc.stdout or "")
            if "address already in use" in err or "Errno 48" in err:
                alt = ns.port + 1
                print(
                    f"error: port {ns.port} is already in use (another `specy-road gui` or app?).\n"
                    f"Try: specy-road gui --port {alt}\n"
                    "Or stop the process using that port, then run again.",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
            print(proc.stderr or proc.stdout or "uvicorn failed", file=sys.stderr)
            raise SystemExit(proc.returncode) from None
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
