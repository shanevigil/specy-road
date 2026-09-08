"""Console entrypoint: thin wrappers around bundled_scripts/."""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from specy_road.cli_init_argparse import build_specy_road_init_parser
from specy_road.cli_usage import USAGE_TEXT
from specy_road.runtime_paths import add_repo_root_arg, bundled_scripts_dir, resolve_repo_root

_PKG_DIR = Path(__file__).resolve().parent
_PM_GANTT_INDEX = _PKG_DIR / "pm_gantt_static" / "index.html"


# Commands that are exactly "run this script with these args". A table rather
# than a chain of elifs: the chain was one branch from the per-function line cap
# and every new command pushed it over.
_SCRIPTS = {
    "validate": "validate_roadmap.py",
    "brief": "generate_brief.py",
    "export": "export_roadmap_md.py",
    "update": "update_specy_road.py",
    "file-limits": "validate_file_limits.py",
    "do-next-available-task": "do_next_task.py",
    "abort-task-pickup": "abort_task_pickup.py",
    "registry-prune": "registry_prune.py",
    "mark-implementation-reviewed": "mark_implementation_reviewed.py",
    "finish-this-task": "finish_task.py",
    "grind-session": "grind_session.py",
    "start-milestone-session": "start_milestone_session.py",
    "open-milestone-pr": "open_milestone_pr.py",
    "reconcile-milestone-status": "reconcile_milestone_status.py",
    "sync": "pm_sync.py",
    "rebalance-chunks": "roadmap_rebalance.py",
    "refresh-schemas": "refresh_schemas.py",
    "refresh-stubs": "refresh_stubs.py",
    "review-node": "review_node.py",
    "scaffold-planning": "scaffold_planning.py",
    "move-node": "roadmap_move_node.py",
}

# Commands whose bundled script owns its own argparse. The command name is
# forwarded so `specy-road <cmd> -h` prints that subcommand's help.
_FORWARDED = {
    "history": "history_cli.py",
    "digest": "digest_cli.py",
    "search": "search_cli.py",
    "brainstorm": "brainstorm_cli.py",
    "why-blocked": "roadmap_query_cli.py",
    "list-gates": "roadmap_query_cli.py",
}

_CRUD_COMMANDS = (
    "list-nodes",
    "show-node",
    "add-node",
    "edit-node",
    "set-gate-status",
    "archive-node",
    "list-dependencies",
    "set-dependencies",
    "add-dependency",
    "remove-dependency",
)

_ARCHIVE_COMMANDS = (
    "archive",
    "deepen-archive",
    "list-archives",
    "show-archive",
    "restore-archive",
)


def _known_commands() -> list[str]:
    return sorted(
        {*_SCRIPTS, *_FORWARDED, *_CRUD_COMMANDS, *_ARCHIVE_COMMANDS,
         "scaffold-constitution", "init", "gui"}
    )


def _did_you_mean(cmd: str) -> list[str]:
    """Closest known commands for an unrecognised one.

    Prefixes are offered ahead of what ``difflib`` scores as similar, and that
    ordering is what makes the motivating case work: everyone types ``grind``
    first, but against ``grind-session`` the similarity ratio is 0.55 — under
    ``get_close_matches``'s default cutoff, so it would suggest nothing at all.
    A guess that is the first word of a real command is not a misspelling.
    """
    known = _known_commands()
    prefixed = [c for c in known if c.startswith(cmd)]
    if prefixed:
        return prefixed[:3]
    return difflib.get_close_matches(cmd, known, n=3, cutoff=0.6)


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
    """Run a bundled entrypoint in its own process.

    ``-m`` on the installed package, so the child resolves imports the same way
    the parent did. This used to exec the file by path with a hand-built
    PYTHONPATH prefix, which was the only thing making the scripts'
    bare-module-name imports resolve.
    """
    module = f"specy_road.bundled_scripts.{script.removesuffix('.py')}"
    if not (bundled_scripts_dir() / script).is_file():
        print(
            f"error: missing bundled script {script} (broken install).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    proc = subprocess.run([sys.executable, "-m", module, *args])
    if proc.returncode != 0:
        # Avoid chaining from CalledProcessError: bundled scripts already print
        # stderr messages; surfacing subprocess.check_call adds a noisy traceback.
        raise SystemExit(proc.returncode) from None


def _cmd_scaffold_constitution(rest: list[str]) -> None:
    from specy_road.constitution_scaffold import ConstitutionExistsError, write_constitution

    p = argparse.ArgumentParser(
        prog="specy-road scaffold-constitution",
        description=(
            "Create starter constitution/purpose.md and constitution/principles.md "
            "(human judgment; not validated by specy-road). Skips files that already exist unless --force."
        ),
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing purpose.md and/or principles.md.",
    )
    ns = p.parse_args(rest)
    root = resolve_repo_root(ns)
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
    add_repo_root_arg(p)
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


def _unknown_command(cmd: str) -> None:
    print(f"unknown command: {cmd}", file=sys.stderr)
    for suggestion in _did_you_mean(cmd):
        print(
            f"did you mean '{suggestion}'? Try: specy-road {suggestion} --help",
            file=sys.stderr,
        )
    print("Run 'specy-road --help' for the full list.", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE_TEXT)
        raise SystemExit(0)
    if argv[0] in ("--version", "-V"):
        from specy_road import __version__

        print(f"specy-road {__version__}")
        raise SystemExit(0)
    cmd, *rest = argv
    if cmd in _SCRIPTS:
        _run(_SCRIPTS[cmd], rest)
    elif cmd in _CRUD_COMMANDS:
        _run("roadmap_crud.py", _args_repo_root_first([cmd, *rest]))
    elif cmd in _ARCHIVE_COMMANDS:
        _run("archive_cli.py", [cmd, *rest])
    elif cmd in _FORWARDED:
        _run(_FORWARDED[cmd], [cmd, *rest])
    elif cmd == "scaffold-constitution":
        _cmd_scaffold_constitution(rest)
    elif cmd == "init":
        _run_init_cli(rest)
    elif cmd == "gui":
        _cmd_gui(rest)
    else:
        _unknown_command(cmd)


if __name__ == "__main__":
    main()
