"""specyrd: optional IDE glue (delegates to specy-road / scripts)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from specy_road.specyrd_init import ROLE_COMMAND_FILES, resolve_repo_root, run_init


def _note_if_already_initialized(target: Path) -> None:
    """Point an existing repo at ``refresh-stubs`` before ``init`` rewrites it.

    Re-running ``init`` on an initialized repo is a supported flow (adding a
    second ``--ai`` pack), so this is a note, not a refusal — but reaching for
    ``--force`` to pick up newly shipped stubs is what a refresh command is for.

    ``init project`` writes the manifest too, to record ``project_root``, but
    with no ``agents``; only a recorded IDE pack means stubs are installed.
    """
    manifest = resolve_repo_root(target) / ".specyrd" / "manifest.json"
    if not manifest.is_file():
        return
    try:
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        if not recorded.get("agents"):
            return
        version = str(recorded.get("specyrd_version") or "unknown")
    except (OSError, json.JSONDecodeError, AttributeError):
        version = "unknown"
    print(
        f"note: this repo is already initialized (specyrd {version}).\n"
        "  To pick up stubs from this version, run: specy-road refresh-stubs\n"
        "  To add another IDE pack, keep going with --ai <other>.",
        file=sys.stderr,
    )


def _role_stub_names(role: str) -> str:
    """The role's stubs for ``--help``, read from the install table so it cannot drift."""
    return ", ".join(f.removeprefix("specyrd-").removesuffix(".md") for f in ROLE_COMMAND_FILES[role])


def _parse_extras(s: str) -> list[str]:
    return [x.strip().lower() for x in s.split(",") if x.strip()]


def _install_extras(names: list[str], *, dry_run: bool) -> None:
    want: list[str] = []
    for n in names:
        if n == "review":
            if importlib.util.find_spec("openai") is None:
                want.append("review")
        elif n == "gui":
            if importlib.util.find_spec("fastapi") is None:
                want.append("gui")
        else:
            print(f"warning: unknown extra {n!r} (use review, gui)", file=sys.stderr)
    if not want:
        return
    spec = ",".join(sorted(set(want)))
    cmd = [sys.executable, "-m", "pip", "install", f"specy-road[{spec}]"]
    if dry_run:
        print(f"Would run: {' '.join(cmd)}")
        return
    subprocess.check_call(cmd)


def _prompt_extras() -> list[str]:
    out: list[str] = []
    if input("Install [review] extra (LLM node review)? [y/N]: ").strip().lower() == "y":
        out.append("review")
    if input("Install [gui] extra (PM Gantt: FastAPI + React)? [y/N]: ").strip().lower() == "y":
        out.append("gui")
    return out


def _prompt_role() -> str | None:
    print("Stub set: [1] all  [2] pm  [3] dev  (default: 1)")
    ch = input("> ").strip() or "1"
    if ch == "2":
        return "pm"
    if ch == "3":
        return "dev"
    return "both"


def _add_specyrd_init_subparser(sub: argparse.Action) -> None:
    init = sub.add_parser(
        "init",
        help=(
            "Bootstrap or augment a repo with thin command markdown "
            "(not the Spec Kit 'specify' CLI)."
        ),
    )
    init.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target directory to resolve as the repo (default: .).",
    )
    init.add_argument(
        "--here",
        action="store_true",
        help="Use the current working directory (same as path .).",
    )
    init.add_argument(
        "--ai",
        "--ide",
        dest="agent",
        required=True,
        choices=["cursor", "claude-code", "codex", "generic"],
        metavar="ID",
        help="Agent pack: cursor | claude-code | codex (skills under .agents/skills/) | generic",
    )
    init.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths that would be written; do not modify files.",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite the command stubs and .specyrd/README.md that this tool "
            "installed — exactly the paths .specyrd/manifest.json records, and "
            "nothing else. Consumer-owned files (CLAUDE.md, .gitignore, "
            ".cursorindexingignore) are always merged inside their managed "
            "block, never replaced, with or without this flag. To refresh an "
            "already-initialized repo, prefer specy-road refresh-stubs."
        ),
    )
    init.add_argument(
        "--ai-commands-dir",
        type=Path,
        metavar="REL_PATH",
        help=(
            "Required for --ai generic: relative path under repo root "
            "for command .md files."
        ),
    )
    init.add_argument(
        "--role",
        choices=["pm", "dev", "both"],
        metavar="ROLE",
        default=None,
        help=(
            "Install only the stubs relevant to a role: "
            f"pm ({_role_stub_names('pm')}), dev ({_role_stub_names('dev')}), "
            "or both (same as omitting --role: every stub). "
            "With --no-prompt this flag is required."
        ),
    )
    init.add_argument(
        "--extras",
        default="",
        metavar="LIST",
        help="Comma-separated optional installs: review, gui (pip install specy-road[...]).",
    )
    init.add_argument(
        "--no-prompt",
        action="store_true",
        help="Non-interactive: do not prompt; requires --role; use --extras as given.",
    )


def _build_parser() -> argparse.ArgumentParser:
    from specy_road import __version__

    p = argparse.ArgumentParser(
        prog="specyrd",
        description=(
            "Optional installer for IDE slash-command stubs that delegate to "
            "specy-road (and bundled roadmap scripts under "
            "specy_road/bundled_scripts/). "
            "Does not replace core validation or briefs."
        ),
    )
    p.add_argument("--version", "-V", action="version", version=f"specyrd {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    _add_specyrd_init_subparser(sub)
    return p


def main(argv: list[str] | None = None) -> None:  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "init":
        parser.print_help()
        raise SystemExit(2)

    target = Path.cwd() if args.here else Path(args.path)

    if args.agent == "generic" and args.ai_commands_dir is None:
        print(
            "error: --ai-commands-dir is required when --ai generic",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if args.no_prompt and args.role is None:
        print(
            "error: --no-prompt requires --role (pm, dev, or both)",
            file=sys.stderr,
        )
        raise SystemExit(2)

    _note_if_already_initialized(target)

    extras = _parse_extras(args.extras or "")
    role = args.role
    if not args.no_prompt and sys.stdin.isatty():
        if not extras:
            extras = _prompt_extras()
        if role is None:
            role = _prompt_role()

    try:
        result = run_init(
            target=target,
            agent=args.agent,
            dry_run=args.dry_run,
            force=args.force,
            ai_commands_dir=args.ai_commands_dir,
            role=role,
            write_claude_md=(args.agent == "claude-code"),
            gui_settings_stub=("gui" in extras),
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    try:
        _install_extras(extras, dry_run=args.dry_run)
    except subprocess.CalledProcessError as e:
        print(f"error: pip install failed with exit code {e.returncode}", file=sys.stderr)
        raise SystemExit(1) from e

    if result.dry_run:
        print("Dry run — would write:")
        for w in result.written:
            print(f"  {w}")
    else:
        for w in result.written:
            print(f"Wrote {w}")
    for s in result.skipped:
        print(f"Skipped: {s}" if "(" in s else f"Skipped (exists, use --force to overwrite): {s}")


if __name__ == "__main__":
    main()
