"""Console entrypoint: thin wrappers around bundled_scripts/."""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.agents_md_block import AGENTS_MD
from specy_road.cli_init_argparse import build_specy_road_init_parser
from specy_road.cli_usage import USAGE_TEXT
from specy_road.managed_block import HTML_COMMENT, _split
from specy_road.runtime_paths import add_repo_root_arg, bundled_scripts_dir, git_root, project_root, resolve_repo_root
from specy_road.specyrd_init import _load_manifest

_PKG_DIR = Path(__file__).resolve().parent
_PM_GANTT_INDEX = _PKG_DIR / "pm_gantt_static" / "index.html"
_VERSION = re.compile(r"^(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?$", re.IGNORECASE)
_AGENTS_WRITTEN = re.compile(r"Written by specy-road (\S+);")
_MINIMUM_LINE = re.compile(r"\*\*Minimum specy-road version:\*\* (\S+)\.")
_PRE = {"a": 0, "b": 1, "rc": 2}


def _version_sort_key(version: str) -> tuple[int, ...]:
    stem = version.strip().split("+", 1)[0]
    m = _VERSION.match(stem)
    if not m:
        return (0,)
    release = tuple(int(p) for p in m.group(1).split("."))
    pre = m.group(2)
    return (*release, 3, 0) if pre is None else (*release, _PRE[pre.lower()], int(m.group(3)))


def recorded_toolkit_version(project: Path) -> tuple[str, str] | None:
    checkout = git_root(project) or project.resolve()
    candidates: list[tuple[str, str]] = []
    recorded = str(_load_manifest(checkout).get("specyrd_version") or "").strip()
    if recorded:
        candidates.append((recorded, ".specyrd/manifest.json"))
    path = project / AGENTS_MD
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        text = ""
    _before, block, _after = _split(text, HTML_COMMENT)
    if block:
        for pattern in (_AGENTS_WRITTEN, _MINIMUM_LINE):
            m = pattern.search(block)
            if m:
                candidates.append((m.group(1), AGENTS_MD))
    if not candidates:
        return None
    best = max(candidates, key=lambda item: _version_sort_key(item[0]))
    sources = sorted({where for ver, where in candidates if ver == best[0]})
    where = sources[0] if len(sources) == 1 else " and ".join(sources)
    return best[0], where


def warn_if_running_version_older(project: Path) -> None:
    found = recorded_toolkit_version(project)
    if found is None:
        return
    recorded, where = found
    if _version_sort_key(__version__) >= _version_sort_key(recorded):
        return
    print(
        f"specy-road: warning — specy-road {__version__} is running but this project records "
        f"{recorded} ({where}); an older install earlier on PATH is the usual cause. "
        "Check `which specy-road` and `specy-road --version`, then reinstall with "
        "`pipx install specy-road` or `uv tool install specy-road`.",
        file=sys.stderr,
    )


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
    "review-packet": "review_packet.py",
    "integrity": "integrity_cli.py",
    "impact": "impact_cli.py",
    "prompt": "role_prompt.py",
    "finish-this-task": "finish_task.py",
    "grind-session": "grind_session.py",
    "start-milestone-session": "start_milestone_session.py",
    "open-milestone-pr": "open_milestone_pr.py",
    "reconcile-milestone-status": "reconcile_milestone_status.py",
    "sync": "pm_sync.py",
    "rebalance-chunks": "roadmap_rebalance.py",
    "refresh-schemas": "refresh_schemas.py",
    "refresh-profiles": "refresh_profiles.py",
    "refresh-stubs": "refresh_stubs.py",
    "upgrade": "upgrade.py",
    "review-node": "review_node.py",
    "scaffold-planning": "scaffold_planning.py",
    "move-node": "roadmap_move_node.py",
    "doctor": "doctor.py",
}

_FORWARDED = {
    "history": "history_cli.py",
    "digest": "digest_cli.py",
    "search": "search_cli.py",
    "brainstorm": "brainstorm_cli.py",
    "why-blocked": "roadmap_query_cli.py",
    "list-gates": "roadmap_query_cli.py",
    "handoff": "review_cli.py",
    "models": "models_cli.py",
    "orchestrate": "orchestrate_cli.py",
    "session": "session_cli.py",
    "review": "review_cli.py",
    "ready": "review_cli.py",
    "worker": "worker_cli.py",
    "branches": "branches_cli.py",
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
    "apply",
)

_ARCHIVE_COMMANDS = (
    "archive",
    "deepen-archive",
    "list-archives",
    "show-archive",
    "restore-archive",
)


REPLACED_COMMANDS = {
    "specy-road grind": "specy-road grind-session",
    "specy-road pm-sync": "specy-road sync",
    "specy-road backfill-activity": "",   # last-worked dates are derived from git
}


def _known_commands() -> list[str]:
    return sorted(
        {*_SCRIPTS, *_FORWARDED, *_CRUD_COMMANDS, *_ARCHIVE_COMMANDS,
         "scaffold-constitution", "init", "gui"}
    )


def registered_agent_command_names() -> dict[str, set[str]]:
    from specy_road.specyrd_cli import _build_parser as _specyrd_parser

    specyrd = next(
        a
        for a in _specyrd_parser()._actions
        if isinstance(a, argparse._SubParsersAction)
    )
    return {
        "specy-road": {*_known_commands(), "version"},
        "specyrd": set(specyrd.choices),
    }


def _did_you_mean(cmd: str) -> list[str]:
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
    module = f"specy_road.bundled_scripts.{script.removesuffix('.py')}"
    if not (bundled_scripts_dir() / script).is_file():
        print(
            f"error: missing bundled script {script} (broken install).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    proc = subprocess.run([sys.executable, "-m", module, *args])
    if proc.returncode != 0:
        raise SystemExit(proc.returncode) from None


def _cmd_scaffold_constitution(rest: list[str]) -> None:
    from specy_road.constitution_scaffold import ConstitutionExistsError, write_constitution

    p = argparse.ArgumentParser(
        prog="specy-road scaffold-constitution",
        description="Create starter constitution/purpose.md and constitution/principles.md.",
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
            "error: FastAPI Gantt UI needs uvicorn (specy-road[gui-next]). "
            "Run: specy-road init gui --install-gui",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    if not _gui_static_ok():
        print(
            "error: packaged Gantt UI assets are missing. Reinstall specy-road[gui-next] "
            "or rebuild gui/pm-gantt (see contributor-guide).",
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
    if cmd == "doctor" or cmd not in _known_commands():
        return
    warn_if_running_version_older(project_root(_repo_root_from_argv(rest)))


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE_TEXT)
        raise SystemExit(0)
    if argv[0] in ("--version", "-V", "version"):
        from specy_road import __version__

        print(f"specy-road {__version__}")
        raise SystemExit(0)
    cmd, *rest = argv
    _maybe_warn_running_version_older(cmd, rest)
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
