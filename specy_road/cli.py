"""Console entrypoint: thin wrappers around scripts/."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_PKG_DIR = Path(__file__).resolve().parent
_PM_GANTT_INDEX = _PKG_DIR / "pm_gantt_static" / "index.html"


def _gui_static_ok() -> bool:
    return _PM_GANTT_INDEX.is_file()


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
            "  init --install-gui — pip gui-next + local npm build when gui/pm-gantt exists (one-time setup for specy-road gui)\n"
            "  init --reinstall-gui — same as install-gui but pip --force-reinstall\n"
            "  init --build-gui — npm only (rebuild SPA without touching pip)\n"
            "  update — fast-forward a git clone of specy-road from github.com/shanevigil/specy-road "
            "(optional: --path DIR --remote NAME --branch BRANCH --dry-run)\n"
            "  gui — FastAPI + Gantt PM UI (after: init --install-gui or pip install 'specy-road[gui-next]')\n"
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
    elif cmd == "update":
        _run("update_specy_road.py", rest)
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
    elif cmd == "init":
        from specy_road.cli_init import run_install_gui

        p = argparse.ArgumentParser(
            prog="specy-road init",
            description="Set up the Gantt PM UI: Python deps (FastAPI/uvicorn) and, in a source tree, the bundled SPA build.",
        )
        mode = p.add_mutually_exclusive_group(required=False)
        mode.add_argument(
            "--install-gui",
            action="store_true",
            help="pip install --upgrade …[gui-next], then npm build in gui/pm-gantt when that folder exists (so specy-road gui works).",
        )
        mode.add_argument(
            "--reinstall-gui",
            action="store_true",
            help="Like --install-gui but pip uses --force-reinstall (repair a broken Python env).",
        )
        p.add_argument(
            "--build-gui",
            action="store_true",
            help="Only rebuild the SPA (npm ci/install + npm run build). Use without --install-gui to skip pip.",
        )
        p.add_argument(
            "--skip-npm-build",
            action="store_true",
            help="With --install-gui or --reinstall-gui only: install Python deps but do not run npm (faster repeat upgrades).",
        )
        p.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the commands that would be run; do not install or build.",
        )
        ns = p.parse_args(rest)
        if not ns.install_gui and not ns.reinstall_gui and not ns.build_gui:
            p.print_help()
            print(
                "\nerror: specify at least one of --install-gui, --reinstall-gui, or --build-gui.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        do_pip = ns.install_gui or ns.reinstall_gui
        npm_only = ns.build_gui and not do_pip
        try:
            run_install_gui(
                dry_run=ns.dry_run,
                reinstall=ns.reinstall_gui,
                do_pip=do_pip,
                npm_only=npm_only,
                skip_npm_after_pip=do_pip and ns.skip_npm_build,
            )
        except subprocess.CalledProcessError as e:
            print(
                f"error: command failed with exit code {e.returncode}",
                file=sys.stderr,
            )
            raise SystemExit(1) from e
    elif cmd == "gui":
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
                "error: FastAPI Gantt UI needs uvicorn (included in specy-road[gui-next]). Run:\n"
                "  specy-road init --install-gui\n"
                "  specy-road init --reinstall-gui   # if deps are corrupted or stuck\n"
                "or:\n"
                "  pip install 'specy-road[gui-next]'\n"
                "Use the same Python environment as this `specy-road` command.",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        if not _gui_static_ok():
            print(
                "error: packaged Gantt UI assets are missing "
                f"({_PM_GANTT_INDEX}).\n"
                "Reinstall or upgrade: pip install --upgrade 'specy-road[gui-next]'\n"
                "If you develop the UI from git, rebuild once from the repo root:\n"
                "  cd gui/pm-gantt && npm install && npm run build",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        env = os.environ.copy()
        if ns.repo_root is not None:
            env["SPECY_ROAD_REPO_ROOT"] = str(ns.repo_root.resolve())
        host, port_s = ns.host, str(ns.port)
        if ns.host == "0.0.0.0":
            display_host = "127.0.0.1"
        else:
            display_host = ns.host
        print(
            f"Gantt PM UI — open http://{display_host}:{ns.port}/ "
            f"(listening on {host}:{port_s}; Ctrl+C to stop)\n",
            flush=True,
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "specy_road.gui_app:app",
                "--host",
                host,
                "--port",
                port_s,
            ],
            cwd=Path.cwd(),
            env=env,
        )
        if proc.returncode != 0:
            raise SystemExit(proc.returncode) from None
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
