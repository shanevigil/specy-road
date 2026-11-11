"""Console entrypoint: each command's bundled_scripts module, run in this process."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import importlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from types import ModuleType
from typing import IO

from specy_road.cli_args import subcommand_parsers
from specy_road.errors import SpecyError, exit_for
from specy_road.runtime_paths import add_repo_root_arg, bundled_scripts_dir, project_root, resolve_repo_root
from specy_road.version_skew import warn_if_running_version_older

_PKG_DIR = Path(__file__).resolve().parent
_PM_GANTT_INDEX = _PKG_DIR / "pm_gantt_static" / "index.html"


# The dispatcher tables. Each command imports ``specy_road.bundled_scripts.<module>`` and calls
# its ``main(argv)`` in this process. A table rather than a chain of elifs: the chain was one
# branch from the per-function line cap and every new command pushed it over.
#
# Commands whose module parses the words after the command name; argparse names the program
# ``specy-road <command>``.
_SCRIPTS = {
    "validate": "validate_roadmap",
    "brief": "generate_brief",
    "export": "export_roadmap_md",
    "update": "update_specy_road",
    "file-limits": "validate_file_limits",
    "do-next-available-task": "do_next_task",
    "abort-task-pickup": "abort_task_pickup",
    "reconcile-branch": "reconcile_branch_cli",
    "registry-prune": "registry_prune",
    "mark-implementation-reviewed": "mark_implementation_reviewed",
    "review-packet": "review_packet",
    "integrity": "integrity_cli",
    "impact": "impact_cli",
    "prompt": "role_prompt",
    "finish-this-task": "finish_task",
    "grind-session": "grind_session",
    "start-milestone-session": "start_milestone_session",
    "open-milestone-pr": "open_milestone_pr",
    "reconcile-milestone-status": "reconcile_milestone_status",
    "sync": "pm_sync",
    "rebalance-chunks": "roadmap_rebalance",
    "refresh-schemas": "refresh_schemas",
    "refresh-profiles": "refresh_profiles",
    "refresh-stubs": "refresh_stubs",
    "upgrade": "upgrade",
    "review-node": "review_node",
    "scaffold-planning": "scaffold_planning",
    "author-approach": "author_approach",
    "move-node": "roadmap_move_node", "rename-refs": "planning_rename",
    "doctor": "doctor",
    "history": "history_cli",
    "digest": "digest_cli",
    "search": "search_cli",
    "brainstorm": "brainstorm_cli",
}

# Commands whose module's parser has one subcommand per command it serves, so the command
# name goes first in its argv and argparse names the program ``specy-road``.
_FORWARDED = {
    "why-blocked": "roadmap_query_cli",
    "list-gates": "roadmap_query_cli",
    "handoff": "review_cli",
    "models": "models_cli",
    "orchestrate": "orchestrate_cli",
    "session": "session_cli",
    "review": "review_cli",
    "ready": "review_cli",
    "worker": "worker_cli",
    "chore": "chore_cli",
    "decisions": "decisions_cli",
    "lessons": "lessons_cli",
    "branches": "branches_cli",
    "worktree": "worktree_cli",
    **dict.fromkeys(("indent", "outdent", "group-nodes"), "roadmap_outline_group"),
}

_CRUD_COMMANDS = (
    "list-nodes",
    "show-node",
    "add-node",
    "edit-node",
    "set-gate-status",
    "archive-node", "remove-node",
    "list-dependencies",
    "set-dependencies",
    "add-dependency",
    "remove-dependency",
    "apply",
)

_ARCHIVE_COMMANDS = (
    "archive",
    "deepen-archive",
    "list-archives",
    "show-archive",
    "restore-archive",
)


# Commands an agent file may still name that are not registered, each with what
# to run instead ("" when nothing replaces it). `validate` names the replacement
# when AGENTS.md or CLAUDE.md mentions one.
REPLACED_COMMANDS = {
    "specy-road grind": "specy-road grind-session",
    "specy-road pm-sync": "specy-road sync",
    "specy-road backfill-activity": "",   # last-worked dates are derived from git
}


def _known_commands() -> list[str]:
    return sorted(
        {*_SCRIPTS, *_FORWARDED, *_CRUD_COMMANDS, *_ARCHIVE_COMMANDS, *_FUNCTIONS}
    )


def registered_agent_command_names() -> dict[str, set[str]]:
    """Registered ``specy-road`` / ``specyrd`` subcommand names for agent-file checks."""
    from specy_road.specyrd_cli import build_parser as specyrd_parser

    return {
        "specy-road": {*_known_commands(), "version"},
        "specyrd": set(subcommand_parsers(specyrd_parser())),
    }


def command_parsers(name: str) -> list[argparse.ArgumentParser]:
    """The parsers ``specy-road <name>`` reads its arguments with, outermost first.

    One, its module's ``build_parser()``, for a command whose module parses the words after the
    command name. Two for a command whose module serves several: that module's parser, whose own
    options (``--repo-root`` on the roadmap CRUD parser, say) apply too, then the command's
    subparser. Only ``name``'s module is imported. ``KeyError`` for a name that is not a command.
    """
    if name in _PARSERS:
        return [_PARSERS[name]()]
    if name in _SCRIPTS:
        return [_module(_SCRIPTS[name]).build_parser()]
    if name in _CRUD_COMMANDS:
        module = "roadmap_crud"
    elif name in _ARCHIVE_COMMANDS:
        module = "archive_cli"
    else:
        module = _FORWARDED[name]
    outer = _module(module).build_parser()
    return [outer, subcommand_parsers(outer)[name]]


def _module(name: str) -> ModuleType:
    return importlib.import_module(f"specy_road.bundled_scripts.{name}")


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
    from specy_road.cli_init_argparse import build_parser
    from specy_road.init_project import run_init_project

    p = build_parser()
    ns = p.parse_args(rest)
    if ns.init_cmd == "project":
        raise SystemExit(
            run_init_project(
                ns.path, dry_run=ns.dry_run, force=ns.force, profiles=ns.profiles
            )
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


def _run(module: str, argv: list[str], prog: str = "specy-road") -> None:
    """Call ``bundled_scripts.<module>``'s ``main(argv)`` in this process (:func:`_call_main`)."""
    if not (bundled_scripts_dir() / f"{module}.py").is_file():
        print(
            f"error: missing bundled script {module}.py (broken install).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    _call_main(_module(module), argv, prog)


def _invoke_main(entry: ModuleType, argv: list[str]) -> None:
    """Run ``entry.main``; a command error is printed once and becomes its exit code."""
    try:
        entry.main(argv)
    except SpecyError as error:
        exit_for(error)


def _call_main(entry: ModuleType, argv: list[str], prog: str) -> None:
    """``entry.main(argv)``, with ``sys.argv`` ``[prog, *argv]`` while it runs.

    That is what it was when each command ran in a child interpreter, so argparse help reads
    ``usage: specy-road <cmd>`` rather than this module's file name. It returns when the command
    exits 0, as it did when the child did; any other exit is the ``SystemExit`` the command raised.
    """
    saved = sys.argv
    sys.argv = [prog, *argv]
    try:
        _invoke_main(entry, argv)
    except SystemExit as e:
        if e.code not in (None, 0):
            raise
    finally:
        sys.argv = saved


def run(argv: list[str]) -> int:
    """Run ``specy-road <argv>`` in this process; return the exit status a child would have had.

    For a command that runs another, as a step it must see succeed. The output is flushed
    before this returns, so it lands ahead of anything a later git command prints.
    """
    try:
        main(argv)
        status = 0
    except SystemExit as e:
        status = exit_status(e)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
    return status


def run_captured(module: str, argv: list[str]) -> tuple[int, str, str]:
    """Run ``bundled_scripts.<module>``'s ``main(argv)`` here; return ``(status, stdout, stderr)``.

    The output is captured as a child's pipes captured it: at the file descriptors too, because
    the git commands a module runs write there directly. An exception the module does not handle is
    reported as a child's would be: its traceback on stderr and status 1.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        saved = os.dup(1), os.dup(2)
        os.dup2(out.fileno(), 1)
        os.dup2(err.fileno(), 2)
        py_out, py_err = (_line_writer(f) for f in (out, err))
        try:
            with contextlib.redirect_stdout(py_out), contextlib.redirect_stderr(py_err):
                try:
                    _run(module, argv)
                    status = 0
                except SystemExit as e:
                    status = exit_status(e)
                except Exception:  # noqa: BLE001 — a child's traceback, as its pipe captured it
                    traceback.print_exc()
                    status = 1
        finally:
            py_out.close()
            py_err.close()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
        return status, _read(out), _read(err)


def _line_writer(f: IO[bytes]) -> IO[str]:
    """A line-buffered text stream on ``f``'s descriptor, which the caller closes."""
    return open(f.fileno(), "w", buffering=1, encoding="utf-8", closefd=False)  # noqa: SIM115


def _read(f: IO[bytes]) -> str:
    f.seek(0)
    return f.read().decode("utf-8", errors="replace")


def exit_status(e: SystemExit) -> int:
    """The status an interpreter exits with on ``e``, printing a message code as it would."""
    if e.code is None or isinstance(e.code, int):
        return e.code or 0
    print(e.code, file=sys.stderr)
    return 1


def _scaffold_constitution_parser() -> argparse.ArgumentParser:
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
    return p


def _cmd_scaffold_constitution(rest: list[str]) -> None:
    from specy_road.constitution_scaffold import write_constitution

    ns = _scaffold_constitution_parser().parse_args(rest)
    root = resolve_repo_root(ns)
    result = write_constitution(root, force=ns.force)
    for rel in result.written:
        print(f"wrote {rel}")
    for rel in result.skipped_existing:
        print(f"skipped (exists, use --force to overwrite): {rel}")


def _gui_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road gui")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--read-only",
        action="store_true",
        help="Serve every GET route and refuse every write route with 403.",
    )
    add_repo_root_arg(p)
    return p


def _cmd_gui(rest: list[str]) -> None:
    ns = _gui_parser().parse_args(rest)
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
    if ns.read_only:
        env["SPECY_ROAD_GUI_READ_ONLY"] = "1"
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


def _cmd_orchestration(rest: list[str]) -> None:
    """``orchestration guard …`` is the only form; the guard's ``main`` gets the words after it."""
    if rest[:1] != ["guard"]:
        print("usage: specy-road orchestration guard --format …", file=sys.stderr)
        raise SystemExit(2)
    _run("orchestration_guard_cli", rest[1:], prog="specy-road orchestration guard")


def _orchestration_parser() -> argparse.ArgumentParser:
    """``orchestration``'s surface: its one subcommand, ``guard``, with the guard's own options.

    :func:`_cmd_orchestration` dispatches on the first word itself (anything but ``guard`` gets a
    one-line usage); this parser is what the command accepts, for the inventory and the flag scan.
    """
    p = argparse.ArgumentParser(prog="specy-road orchestration", add_help=False)
    sub = p.add_subparsers(dest="orchestration_cmd")
    guard = _module("orchestration_guard_cli").build_parser()
    sub.add_parser("guard", parents=[guard], add_help=False, description=guard.description)
    return p


# Commands implemented here rather than by a bundled_scripts module.
_FUNCTIONS = {
    "scaffold-constitution": _cmd_scaffold_constitution,
    "init": _run_init_cli,
    "gui": _cmd_gui,
    "orchestration": _cmd_orchestration,
}

# The parsers of the commands in _FUNCTIONS, for command_parsers().
_PARSERS = {
    "scaffold-constitution": _scaffold_constitution_parser,
    "init": lambda: importlib.import_module("specy_road.cli_init_argparse").build_parser(),
    "gui": _gui_parser,
    "orchestration": _orchestration_parser,
}


def _unknown_command(cmd: str) -> None:
    print(f"unknown command: {cmd}", file=sys.stderr)
    for suggestion in _did_you_mean(cmd):
        print(
            f"did you mean '{suggestion}'? Try: specy-road {suggestion} --help",
            file=sys.stderr,
        )
    print("Run 'specy-road --help' for the full list.", file=sys.stderr)
    raise SystemExit(2)


def _repo_root_from_argv(args: list[str]) -> Path | None:
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--repo-root="):
            return Path(arg.split("=", 1)[1])
        if arg == "--repo-root" and i + 1 < len(args):
            return Path(args[i + 1])
        i += 1
    return None


def _maybe_warn_running_version_older(cmd: str, rest: list[str]) -> None:
    if cmd in ("doctor", "upgrade") or cmd not in _known_commands():
        return
    warn_if_running_version_older(project_root(_repo_root_from_argv(rest)))


def main(argv: list[str] | None = None) -> None:
    """Dispatch ``argv``. A command error is printed once and becomes its exit code."""
    try:
        _dispatch(argv)
    except SpecyError as error:
        exit_for(error)


def _dispatch(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        from specy_road.cli_usage import USAGE_TEXT
        from specy_road.doc_links import link_toolkit_docs

        print(link_toolkit_docs(USAGE_TEXT))
        raise SystemExit(0)
    if argv[0] in ("--version", "-V", "version"):
        from specy_road.toolkit_version import running_toolkit_version

        print(f"specy-road {running_toolkit_version()}")
        raise SystemExit(0)
    cmd, *rest = argv
    _maybe_warn_running_version_older(cmd, rest)
    if cmd in _SCRIPTS:
        _run(_SCRIPTS[cmd], rest, prog=f"specy-road {cmd}")
    elif cmd in _CRUD_COMMANDS:
        _run("roadmap_crud", [cmd, *rest])
    elif cmd in _ARCHIVE_COMMANDS:
        _run("archive_cli", [cmd, *rest])
    elif cmd in _FORWARDED:
        _run(_FORWARDED[cmd], [cmd, *rest])
    elif cmd in _FUNCTIONS:
        _FUNCTIONS[cmd](rest)
    else:
        _unknown_command(cmd)


if __name__ == "__main__":
    main()
