"""TTY prompt and footer lines for do-next-available-task ``on_complete``."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from specy_road.git_workflow_config import ON_COMPLETE_MODES, resolve_on_complete
from specy_road.on_complete_session import on_complete_session_path


def prompt_on_complete(repo_root: Path, cli_on_complete: str | None) -> str:
    """TTY prompt for this task's completion workflow; non-TTY uses config/env only."""
    if cli_on_complete is not None:
        return cli_on_complete
    default = resolve_on_complete(repo_root, cli=None, session=None)
    if not sys.stdin.isatty():
        return default
    print()
    print(
        "Completion workflow for this task (how to land work when you run "
        "finish-this-task):",
    )
    print(
        "  pr    — open a PR/MR to the integration branch "
        "(GitHub: PR, GitLab: MR; same idea)",
    )
    print("  merge — merge the feature branch into integration locally, then push")
    print(
        "  auto  — try merge+push first; if that fails, print PR/MR steps (merge pending)",
    )
    print(f"Default from roadmap/git-workflow.yaml / env: {default}")
    try:
        raw = input(f"Choice [{default}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    if not raw:
        return default
    if raw in ON_COMPLETE_MODES:
        return raw
    print(f"Invalid choice {raw!r}; using {default!r}.", file=sys.stderr)
    return default


def print_pickup_footer(
    *,
    root: Path,
    work_dir: Path,
    brief_path: Path,
    prompt_path: Path,
    push_registry: bool,
    remote: str,
    base: str,
    mr_manual: bool,
    impl_review_gate: bool,
    on_complete: str,
    node_id: str,
) -> None:
    """Console lines after task pickup (mirrors do-next-available-task)."""
    print(f"brief:  {brief_path.relative_to(root)}")
    print(f"prompt: {prompt_path.relative_to(root)}")
    print(f"on_complete (this task): {on_complete}")
    sess = on_complete_session_path(work_dir, node_id).relative_to(root)
    print(f"session: {sess} (read by finish-this-task)")
    print()
    if not push_registry:
        print("Push the integration branch so PMs see the registry update:")
        print(f"  git push {remote} {base}")
        print()
    if mr_manual:
        print(
            "Merge requests require manual approval in this repo "
            "(roadmap/git-workflow.yaml). Open the MR after push and wait for review.",
        )
        print()
    print("-" * 60)
    print(f"Open {prompt_path.relative_to(root)} in your agent to begin.")
    if impl_review_gate:
        print(
            "When done: write work/implementation-summary-<NODE_ID>.md, then human runs "
            "specy-road mark-implementation-reviewed, then specy-road finish-this-task",
        )
    else:
        print("When done: specy-road finish-this-task")
    print("-" * 60)
    print_orchestration_hint()


def print_orchestration_hint() -> None:
    """Point at ``grind-session`` from the one place everyone already looks.

    The loop and its hook mode were documented only in ``docs/grind-session.md``,
    which nothing on this path linked to, so operators reached for hand-rolled
    sub-agents instead and never adopted the hook contract. Pickup is where they
    are standing when the question comes up.

    Suppressed inside a running loop, which exports ``SPECY_ROAD_GRIND_SESSION``:
    advertising the loop to itself once per cycle is the flood this is trying not
    to become.
    """
    if os.environ.get("SPECY_ROAD_GRIND_SESSION"):
        return
    print()
    print("Running more than one leaf? specy-road grind-session drives this loop:")
    print("  specy-road grind-session --plan            # ready/blocked leaves + waves")
    print("  specy-road grind-session --on-complete merge \\")
    print("      --implement-mode hook --implement-cmd '<your agent command>'")
    print(
        "  Hook mode hands each leaf's node id, branch, brief and prompt to that "
        "command via SPECY_ROAD_* env vars. See docs/grind-session.md."
    )
