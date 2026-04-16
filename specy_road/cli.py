"""Console entrypoint: thin wrappers around bundled_scripts/."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from specy_road.cli_init_argparse import build_specy_road_init_parser
from specy_road.runtime_paths import bundled_scripts_dir

_PKG_DIR = Path(__file__).resolve().parent
_PM_GANTT_INDEX = _PKG_DIR / "pm_gantt_static" / "index.html"

_USAGE_TEXT = (
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
    "  scaffold-planning <NODE_ID> — create planning/<id>_<slug>_<node_key>.md; set planning_dir\n"
    "    (optional: --planning-dir PATH --force; see scripts/scaffold_planning.py -h)\n"
    "  scaffold-constitution — create constitution/purpose.md and constitution/principles.md from templates\n"
    "    (optional: --repo-root DIR --force)\n"
    "  init project [PATH] — scaffold roadmap/constitution/shared/… into the repo root\n"
    "    (optional: --dry-run --force)\n"
    "  init gui — optional PM UI: --install-gui | --reinstall-gui | --build-gui [--skip-npm-build]\n"
    "  update — fast-forward a git clone of specy-road from github.com/shanevigil/specy-road "
    "(optional: --path DIR --remote NAME --branch BRANCH --dry-run --install-gui-stack)\n"
    "  gui — FastAPI + Gantt PM UI (after: init --install-gui or pip install 'specy-road[gui-next]')\n"
    "\n"
    "Dev task loop:\n"
    "  do-next-available-task  — sync base, brief, register on base, push base, branch, prompt\n"
    "    (optional: --base BRANCH --remote NAME | --interactive | "
    "--no-ci-skip-in-message)\n"
    "  mark-implementation-reviewed — human gate: record review after implementation-summary\n"
    "    (optional: --yes | --allow-missing-summary)\n"
    "  finish-this-task        — complete task, validate, commit\n"
    "    (optional: --push [--remote NAME] | --no-cleanup-work)\n"
)


def _run_init_cli(rest: list[str]) -> None:
    from specy_road.cli_init import run_install_gui
    from specy_road.init_project import run_init_project

    p = build_specy_road_init_parser()
    ns = p.parse_args(rest)
    if ns.init_cmd == "project":
        raise SystemExit(
            run_init_project(ns.path, dry_run=ns.dry_run, force=ns.force)
        )
    assert ns.init_cmd == "gui"
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


def _gui_static_ok() -> bool:
    return _PM_GANTT_INDEX.is_file()


def _args_repo_root_first(args: list[str]) -> list[str]:
    """``roadmap_crud`` expects ``--repo-root`` before the subcommand."""
    out: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--repo-root" and i + 1 < len(args):
            out.extend(["--repo-root", args[i + 1]])
            i += 2
        else:
            out.append(args[i])
            i += 1
    try:
        idx = out.index("--repo-root")
    except ValueError:
        return out
    pair = out[idx : idx + 2]
    rest_ = out[:idx] + out[idx + 2 :]
    return pair + rest_


def _run(script: str, args: list[str]) -> None:
    d = bundled_scripts_dir()
    script_path = d / script
    if not script_path.is_file():
        print(
            f"error: missing bundled script {script_path} (broken install).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    env = os.environ.copy()
    sep = os.pathsep
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(d) + (sep + prev if prev else "")
    cmd = [sys.executable, str(script_path), *args]
    subprocess.check_call(cmd, env=env)


def _cmd_scaffold_constitution(rest: list[str]) -> None:
    from specy_road.constitution_scaffold import ConstitutionExistsError, write_constitution

    p = argparse.ArgumentParser(
        prog="specy-road scaffold-constitution",
        description=(
            "Create starter constitution/purpose.md and constitution/principles.md "
            "(human judgment; not validated by specy-road). Skips files that already exist unless --force."
        ),
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: current working directory)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing purpose.md and/or principles.md.",
    )
    ns = p.parse_args(rest)
    root = (ns.repo_root or Path.cwd()).resolve()
    try:
        result = write_constitution(root, force=ns.force)
    except ConstitutionExistsError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    for rel in result.written:
        print(f"wrote {rel}")
    for rel in result.skipped_existing:
        print(f"skipped (exists, use --force to overwrite): {rel}")


def _cmd_gui(rest: list[str]) -> None:
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
            "  specy-road init gui --install-gui\n"
            "  specy-road init gui --reinstall-gui   # if deps are corrupted or stuck\n"
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


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE_TEXT)
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
    elif cmd == "mark-implementation-reviewed":
        _run("mark_implementation_reviewed.py", rest)
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
        _run("roadmap_crud.py", _args_repo_root_first([cmd, *rest]))
    elif cmd == "review-node":
        _run("review_node.py", rest)
    elif cmd == "scaffold-planning":
        _run("scaffold_planning.py", rest)
    elif cmd == "scaffold-constitution":
        _cmd_scaffold_constitution(rest)
    elif cmd == "init":
        _run_init_cli(rest)
    elif cmd == "gui":
        _cmd_gui(rest)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
