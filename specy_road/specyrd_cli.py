"""specyrd: optional IDE glue (delegates to specy-road / scripts)."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

from specy_road.specyrd_init import run_init


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
        choices=["cursor", "claude-code", "generic"],
        metavar="ID",
        help="Agent pack: cursor | claude-code | generic",
    )
    init.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths that would be written; do not modify files.",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing specyrd-managed command files and README.",
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
            "pm (validate, export, author, sync, list-nodes, show-node, "
            "add-node, review-node), dev (validate, brief, claim, finish, "
            "do-next-task), or both (same as omitting --role: all 14 stubs). "
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
    p = argparse.ArgumentParser(
        prog="specyrd",
        description=(
            "Optional installer for IDE slash-command stubs that delegate to "
            "specy-road (and bundled roadmap scripts under "
            "specy_road/bundled_scripts/). "
            "Does not replace core validation or briefs."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    _add_specyrd_init_subparser(sub)
    return p


def main(argv: list[str] | None = None) -> None:
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
        print(f"Skipped (exists, use --force to overwrite): {s}")


if __name__ == "__main__":
    main()
