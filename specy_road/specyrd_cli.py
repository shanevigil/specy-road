"""specyrd: optional IDE glue (delegates to specy-road / scripts)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.specyrd_init import run_init


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specyrd",
        description=(
            "Optional installer for IDE slash-command stubs that delegate to "
            "specy-road or python scripts/. "
            "Does not replace core validation or briefs."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
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
        choices=["pm", "dev"],
        metavar="ROLE",
        help=(
            "Install only the stubs relevant to a role: "
            "pm (validate, export, author, sync, list-nodes, show-node, "
            "add-node, review-node) or dev (validate, brief, claim, finish, "
            "do-next-task). Omit to install all command stubs."
        ),
    )
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

    try:
        result = run_init(
            target=target,
            agent=args.agent,
            dry_run=args.dry_run,
            force=args.force,
            ai_commands_dir=args.ai_commands_dir,
            role=args.role,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2) from e

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
