#!/usr/bin/env python3
"""``specy-road doctor``: list what the task loop left behind; remove it with ``--prune``.

The listing is the cleanup planner's (:mod:`specy_road.cleanup_plan`): ``feature/rm-*`` branches,
worktrees, registry rows and toolkit stashes, each kind its own section, each row saying why it is
listed and whether ``--prune`` leaves it. ``--kind`` (repeatable: branches, worktrees, registry,
stashes) narrows both the listing and the removal; without it every kind is planned. Nothing
changes without ``--prune``, and ``--prune`` asks once per kind (``--yes`` does not ask) and
removes exactly the rows it planned. ``--fix`` is the deprecated name of ``--prune``.

Before the listing doctor checks the checkout (:func:`report_checkout`):

- the review gate and the orchestration policy agree (:mod:`specy_road.review_gate_agreement`): an
  error.
- ``env_setup`` (:mod:`specy_road.worktree_env`), when configured: its copy and link sources exist
  in the main checkout and its command succeeds there; either failing is an error.
- each linked worktree's ``.venv`` runs the same Python (major.minor) as the main checkout's: a
  warning, since a pin file such as ``.python-version`` is usually ignored and so missing from a
  new worktree.

With no such git remote there is nothing to compare against, which is not a failure: doctor says
so in one line and lists only the stashes. A remote that is configured but cannot be fetched still
fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road import cleanup_plan
from specy_road.cli import DeprecatedFlag
from specy_road.cli_args import add_base_arg, add_remote_arg
# SAME_PATCH, TEMP_WORKTREES and merged_how re-exported for callers
from specy_road.doctor_worktrees import SAME_PATCH, TEMP_WORKTREES, merged_how  # noqa: F401
from specy_road.git_subprocess import git_text
from specy_road.nested_repos import report_unpushed
from specy_road.orchestrate_assign import guidance_bypass_lines
from specy_road.orchestration import read_state
from specy_road.orchestration_pinned import pinned_config
from specy_road.orphaned_claims import report_lines
from specy_road.review_gate_agreement import report_gate_mismatch
from specy_road.runtime_paths import add_repo_root_arg, project_prefix, resolve_repo_root
from specy_road.version_skew import print_install_report, warn_if_running_version_older
from specy_road.worker_adapter_cursor import force_warnings
from specy_road.worker_lock import workers_dir
from specy_road.worker_ops_slots import stall_lines, stalled_workers
from specy_road.worktree_env import (
    EnvSetupError, bounded_path, copy_pairs, copy_source, env_setup_config, git_top, link_paths,
    run_setup_cmd,
)

# --- Checkout checks, printed before the listing ----------------------------


def _worktree_tops(root: Path) -> list[Path]:
    """Every worktree's top directory, the main checkout's first (``git worktree list``)."""
    out = git_text(["worktree", "list", "--porcelain"], root) or ""
    return [Path(line.removeprefix("worktree ")) for line in out.splitlines()
            if line.startswith("worktree ")]


def env_python(project_root: Path, top: Path) -> str | None:
    """The Python version in ``.venv/pyvenv.cfg`` at ``project_root``, else at the git root
    ``top``."""
    for cfg in (project_root / ".venv" / "pyvenv.cfg", top / ".venv" / "pyvenv.cfg"):
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                key, _, value = line.partition("=")
                if key.strip() in ("version_info", "version"):   # uv and virtualenv; venv
                    return value.strip()
            return None
    return None


def _minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _missing_sources(main: Path, conf: dict) -> list[str]:
    """Each copy or link source that is missing from the main checkout or climbs past its git
    root."""
    missing = []
    for src, _dest in copy_pairs(conf):
        try:
            if not copy_source(main, src).is_file():
                missing.append(f"env_setup copies {src}, which is not a file in the main checkout "
                               f"({main / src})")
        except EnvSetupError as e:   # climbs past the git root: the pickup would refuse it
            missing.append(str(e))
    for rel in link_paths(conf):
        try:
            if not bounded_path(main, rel, git_top(main), f"from {rel!r}", "the main checkout",
                                "link").exists():
                missing.append(f"env_setup links {rel}, which does not exist in the main checkout "
                               f"({main / rel})")
        except EnvSetupError as e:
            missing.append(str(e))
    return missing


def report_env_setup(main: Path) -> bool:
    """Say what ``env_setup`` does and run it in the main checkout's project root ``main``;
    whether it failed."""
    conf = env_setup_config(main)
    if not conf:
        return False
    copies = ", ".join(src if src == dest else f"{src} -> {dest}" for src, dest in copy_pairs(conf))
    links = f"; link {', '.join(link_paths(conf))}" if link_paths(conf) else ""
    print(f"env_setup: copy {copies or 'nothing'}{links}; cmd {conf.get('cmd') or 'none'}")
    missing = _missing_sources(main, conf)
    for problem in missing:
        print(f"error: {problem}", file=sys.stderr)
    if not conf.get("cmd"):
        return bool(missing)
    code, out = run_setup_cmd(conf["cmd"], main)
    if code:
        print(f"error: env_setup fails in the main checkout {main} (exit {code}): "
              f"{conf['cmd']}\n{out.rstrip()}",
              file=sys.stderr)
        return True
    print(f"env_setup: succeeds in the main checkout {main}")
    return bool(missing)


def report_python_mismatch(tops: list[Path], prefix: str) -> None:
    """Warn for each linked worktree whose ``.venv`` Python differs from the main checkout's."""
    want = env_python(tops[0] / prefix, tops[0]) if tops else None
    if want is None:
        return
    for top in tops[1:]:
        have = env_python(top / prefix, top)
        if have and _minor(have) != _minor(want):
            print(f"warning: worktree {top} has a Python {have} environment; "
                  f"the main checkout's is {want}. "
                  "Pin the version for env_setup (for example copy .python-version), "
                  "then rebuild it there.",
                  file=sys.stderr)


def report_checkout(root: Path) -> bool:
    """The checkout checks; True when one is an error (doctor exits 1 after the listing)."""
    tops, prefix = _worktree_tops(root), project_prefix(root)
    bad = report_gate_mismatch(root)
    bad = report_env_setup(tops[0] / prefix if tops else root) or bad
    report_python_mismatch(tops, prefix)
    return bad


def _print_orphaned_claims(root: Path) -> None:
    """Report-only: ``--prune`` does not release these (they are not in
    :data:`specy_road.cleanup_plan.FIX_ORDER`).

    The claims are the state model's abandoned ones (:func:`specy_road.orchestration.read_state`).
    """
    lines = report_lines(read_state(root).abandoned)
    if not lines:
        return
    print("Claims with no live worker (report only; --prune does not release them):")
    for line in lines:
        print(f"  {line}")


def _print_stalled(root: Path) -> None:
    """Report-only: each stalled worker and how long it has been silent; ``worker recover`` acts
    on it."""
    # none launched: no sweep
    lines = stall_lines(stalled_workers(root)) if workers_dir(root).is_dir() else []
    if lines:
        print("Stalled workers (report only; --prune does not recover them):")
        print("\n".join(f"  {line}" for line in lines))


def _print_cursor_force(root: Path) -> None:
    """Advisory: one line per roster ``cursor`` entry that launches with ``--force`` (the roster
    launches read).
    An unreadable roster is left to ``validate`` and ``orchestrate plan``."""
    config, err = pinned_config(root)
    # then each excluded or opted-in guidance-bypass model
    for line in (([] if err else force_warnings(config.get("roster") or []))
                 + guidance_bypass_lines(root)):
        print(line, file=sys.stderr)


def _planned(root: Path, ns: argparse.Namespace) -> tuple[list[cleanup_plan.Section], str] | None:
    """The planner's sections for ``--kind`` and the line that says there is nothing to tidy;
    ``None`` when the planner cannot read what it judges against (printed)."""
    kinds = {cleanup_plan.KINDS[k] for k in ns.kind or cleanup_plan.KINDS}
    if cleanup_plan.no_remote(root, ns):
        return ([cleanup_plan.stash_section(root)] if "stash" in kinds else [],
                "Nothing to tidy: no toolkit stash.")
    ctx = cleanup_plan.context(root, ns)
    if ctx is None:
        return None
    return (cleanup_plan.plan(ctx, kinds),
            "Nothing to tidy: no stale branch, worktree, registry row or toolkit stash.")


def cmd_doctor(ns: argparse.Namespace) -> int:
    print_install_report()
    root = resolve_repo_root(ns)
    warn_if_running_version_older(root)
    # gate mismatch, env_setup failure: exit 1 after the listing
    bad_config = report_checkout(root)
    report_unpushed(root)   # advisory: nested-repo commits no remote has
    _print_cursor_force(root)   # advisory: cursor workers that run without the sandbox
    planned = _planned(root, ns)
    if planned is None:
        return 1
    sections, clean = planned
    if not any(found for _k, _h, found in sections):
        print(clean)
    else:
        for _kind, heading, found in sections:
            if found:
                print(heading)
                for f in found:
                    print(f"  {f.name}  — {f.reason}")
        if not ns.prune:
            print("Nothing removed. Re-run with --prune to remove them (it asks per kind).")
        else:
            bad_config = cleanup_plan.apply(sections, ns.yes) or bad_config
    # after the branch section, so it is not read as one of those rows
    _print_orphaned_claims(root)
    _print_stalled(root)
    return int(bad_config)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road doctor",
        description=(
            "After git fetch --prune, list feature/rm-* branches (local and remote) whose leaf is "
            "Complete or that nothing claims — merged by ancestry or patch content, leaf "
            "Complete, or claim gone — worktrees whose branch is gone or merged, other detached "
            "worktrees, registry rows with no branch (listed; --prune leaves a non-Complete one "
            "for registry-prune --remove) or a Complete leaf, and stashes specy-road pushed; also "
            "nested-repo branches with commits no remote has. Dry-run unless --prune."
        ),
    )
    p.add_argument(
        "--prune", action="store_true",
        help="Remove what is listed, asking once per kind, and report each action. "
             "Leaves a branch the integration branch does not contain, and a registry row "
             "whose branch is in neither this clone nor the remote, "
             "unless its leaf is Complete.",
    )
    p.add_argument("--fix", dest="prune", action=DeprecatedFlag, command="doctor",
                   new="doctor --prune")
    p.add_argument(
        "--kind", action="append", choices=sorted(cleanup_plan.KINDS),
        help="List and remove only this kind (repeatable). Default: every kind.",
    )
    p.add_argument("--yes", action="store_true", help="With --prune, do not ask.")
    add_base_arg(p)
    add_remote_arg(p)
    add_repo_root_arg(p)
    return p


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    raise SystemExit(cmd_doctor(ns))


if __name__ == "__main__":
    main()
