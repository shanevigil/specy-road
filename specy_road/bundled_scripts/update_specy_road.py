#!/usr/bin/env python3
"""Fast-forward a git clone of specy-road to match the upstream branch.

Uses the latest commit on the configured remote branch (default: main).
A future mode may checkout the latest release tag instead; see --help.

PyPI-only installs cannot use this command — use pip to upgrade.

After a successful fast-forward, optional ``--install-gui-stack`` runs the same
steps as ``specy-road init gui --install-gui`` (editable ``.[gui-next]`` pip
install and ``gui/pm-gantt`` npm build when sources exist).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Canonical upstream (SSH/HTTPS variants accepted via normalization).
CANONICAL_OWNER_REPO = "shanevigil/specy-road"

# Untracked paths removed by ``--reset-to-origin`` after ``git reset --hard``
# (typical Vite output under ``specy_road/pm_gantt_static/``).
RESET_CLEAN_PATHSPECS: tuple[str, ...] = ("specy_road/pm_gantt_static",)


def normalize_github_repo_path(url: str) -> str | None:
    """Return 'owner/repo' for a github.com remote URL, else None."""
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    if u.startswith("git@"):
        # git@github.com:owner/repo
        rest = u.split("@", 1)[1]
        if ":" not in rest:
            return None
        host, path = rest.split(":", 1)
        if host.lower() != "github.com":
            return None
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}".lower()
        return None
    u_lower = u.lower()
    if "github.com" not in u_lower:
        return None
    idx = u_lower.index("github.com")
    gh = len("github.com")
    start = idx + gh
    tail = u[start:].strip("/")
    # https://github.com/owner/repo or github.com/owner/repo
    parts = tail.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}".lower()
    return None


def is_canonical_specy_road_remote(url: str) -> bool:
    path = normalize_github_repo_path(url)
    return path == CANONICAL_OWNER_REPO.lower()


def _git_output(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _git_succeeds(cwd: Path, *args: str) -> bool:
    r = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode == 0


def _git_toplevel(start: Path) -> Path | None:
    if not _git_succeeds(start, "rev-parse", "--show-toplevel"):
        return None
    out = _git_output(start, "rev-parse", "--show-toplevel")
    return Path(out)


def _remote_url(cwd: Path, remote: str) -> str | None:
    if not _git_succeeds(cwd, "remote", "get-url", remote):
        return None
    return _git_output(cwd, "remote", "get-url", remote)


def _find_kit_root_from(start: Path, remote: str) -> Path | None:
    """Walk ancestors; return first git root whose *remote* is canonical."""
    cur = start.resolve()
    seen: set[Path] = set()
    while True:
        top = _git_toplevel(cur)
        if top is not None and top not in seen:
            seen.add(top)
            url = _remote_url(top, remote)
            if url and is_canonical_specy_road_remote(url):
                return top
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _default_kit_root(remote: str) -> Path:
    import specy_road

    pkg_dir = Path(specy_road.__file__).resolve().parent
    found = _find_kit_root_from(pkg_dir, remote)
    if found is not None:
        return found
    found = _find_kit_root_from(Path.cwd(), remote)
    if found is not None:
        return found
    print(
        "error: could not find a git checkout of specy-road with "
        f"remote {remote!r} pointing at github.com/{CANONICAL_OWNER_REPO}.\n"
        "  If you use a PyPI install only, upgrade with:\n"
        "    pip install --upgrade specy-road\n"
        "  If the kit is a clone or submodule, pass:\n"
        "    specy-road update --path <DIR>",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _working_tree_clean(cwd: Path) -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return not r.stdout.strip()


def _exit_bad_remote(remote: str, url: str | None) -> None:
    msg = (
        f"error: {remote!r} does not point at "
        f"github.com/{CANONICAL_OWNER_REPO} (got {url!r})."
    )
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def _assert_canonical_remote(kit: Path, remote: str) -> None:
    url = _remote_url(kit, remote)
    if not url or not is_canonical_specy_road_remote(url):
        _exit_bad_remote(remote, url)


def _guard_clean_tree(kit: Path, allow_dirty: bool) -> None:
    if _working_tree_clean(kit):
        return
    if not allow_dirty:
        print(
            "error: working tree is not clean "
            "(commit, stash, or discard changes first). "
            "Use --allow-dirty to override.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        "warning: working tree is dirty; fast-forward may fail or "
        "combine with local changes.",
        file=sys.stderr,
    )


def _print_dry_run_commands(kit: Path, remote: str, branch: str) -> None:
    fetch = ("git", "fetch", remote)
    checkout = ("git", "checkout", branch)
    merge = ("git", "merge", "--ff-only", f"{remote}/{branch}")
    print(f"Kit root: {kit}")
    print("Would run:")
    print(f"  {' '.join(fetch)}")
    print(f"  {' '.join(checkout)}")
    print(f"  {' '.join(merge)}")


def _print_reset_dry_run_commands(kit: Path, remote: str, branch: str) -> None:
    print(f"Kit root: {kit}")
    print(
        "Would run (destructive: discards local commits and uncommitted changes):",
    )
    print(f"  git fetch {remote}")
    print(f"  git checkout {branch}")
    print(f"  git reset --hard {remote}/{branch}")
    for rel in RESET_CLEAN_PATHSPECS:
        print(f"  git clean -fd -- {rel}")


def _emit_reset_warning() -> None:
    print(
        "warning: --reset-to-origin discards local commits and uncommitted "
        "changes, then removes untracked files under known build paths.",
        file=sys.stderr,
    )


def _git_reset_to_match_origin(kit: Path, remote: str, branch: str) -> None:
    subprocess.check_call(["git", "fetch", remote], cwd=kit)
    subprocess.check_call(["git", "checkout", branch], cwd=kit)
    subprocess.check_call(
        ["git", "reset", "--hard", f"{remote}/{branch}"],
        cwd=kit,
    )


def _git_clean_reset_build_paths(kit: Path) -> None:
    for rel in RESET_CLEAN_PATHSPECS:
        p = kit / rel
        if not p.exists():
            continue
        subprocess.check_call(["git", "clean", "-fd", "--", rel], cwd=kit)


def _git_fast_forward(kit: Path, remote: str, branch: str) -> None:
    subprocess.check_call(["git", "fetch", remote], cwd=kit)
    subprocess.check_call(["git", "checkout", branch], cwd=kit)
    try:
        subprocess.check_call(
            ["git", "merge", "--ff-only", f"{remote}/{branch}"],
            cwd=kit,
        )
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local {branch!r} to "
            f"{remote}/{branch}.",
            file=sys.stderr,
        )
        print(
            "  Resolve the branch (rebase, reset, or merge) after team "
            "agreement, then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


def _run_update(
    kit: Path,
    *,
    remote: str,
    branch: str,
    dry_run: bool,
    allow_dirty: bool,
    reset_to_origin: bool,
) -> None:
    _assert_canonical_remote(kit, remote)
    if reset_to_origin:
        if dry_run:
            _emit_reset_warning()
            _print_reset_dry_run_commands(kit, remote, branch)
            return
        _emit_reset_warning()
        _git_reset_to_match_origin(kit, remote, branch)
        _git_clean_reset_build_paths(kit)
        return
    _guard_clean_tree(kit, allow_dirty)
    if dry_run:
        _print_dry_run_commands(kit, remote, branch)
        return
    _git_fast_forward(kit, remote, branch)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        metavar="DIR",
        help="Root of the specy-road git clone (default: auto-discover).",
    )
    p.add_argument(
        "--remote",
        default="origin",
        metavar="NAME",
        help="Remote to fetch and merge from (default: origin).",
    )
    p.add_argument(
        "--branch",
        default="main",
        metavar="BRANCH",
        help="Branch to fast-forward (default: main).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the git commands; do not run them.",
    )
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow a dirty working tree (not recommended). Ignored with "
        "--reset-to-origin.",
    )
    p.add_argument(
        "--reset-to-origin",
        action="store_true",
        help=(
            "Destructive: fetch and reset --hard to match the remote branch tip, "
            "then git clean known build dirs (e.g. specy_road/pm_gantt_static/). "
            "Discards local commits and uncommitted changes. Default update "
            "remains a fast-forward merge on a clean tree."
        ),
    )
    p.add_argument(
        "--install-gui-stack",
        action="store_true",
        help=(
            "After git: run pip install -e '.[gui-next]' and build gui/pm-gantt "
            "(same as: specy-road init gui --install-gui). "
            "Use with --dry-run to print what would run."
        ),
    )
    return p


def _resolve_kit_explicit(start: Path, remote: str) -> Path:
    top = _git_toplevel(start)
    if top is None:
        print(f"error: not a git work tree: {start}", file=sys.stderr)
        raise SystemExit(2)
    url = _remote_url(top, remote)
    if not url or not is_canonical_specy_road_remote(url):
        _exit_bad_remote(remote, url)
    return top


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.path is not None:
        kit = _resolve_kit_explicit(args.path.resolve(), args.remote)
    else:
        kit = _default_kit_root(args.remote)

    _run_update(
        kit,
        remote=args.remote,
        branch=args.branch,
        dry_run=args.dry_run,
        allow_dirty=args.allow_dirty,
        reset_to_origin=args.reset_to_origin,
    )

    if not args.dry_run:
        ok_msg = (
            f"[ok] specy-road kit at {kit} matches "
            f"{args.remote}/{args.branch} (hard reset)."
            if args.reset_to_origin
            else f"[ok] specy-road kit at {kit} is fast-forwarded to "
            f"{args.remote}/{args.branch}."
        )
        print(ok_msg, flush=True)

    if args.install_gui_stack:
        from specy_road.cli_init import run_install_gui

        if not args.dry_run:
            print(
                "Installing editable [gui-next] and PM Gantt UI build …",
                flush=True,
            )
        run_install_gui(
            dry_run=args.dry_run,
            reinstall=False,
            do_pip=True,
            npm_only=False,
            skip_npm_after_pip=False,
        )
        if not args.dry_run:
            print(
                "[ok] gui-next stack refresh finished (see messages above).",
                flush=True,
            )


if __name__ == "__main__":
    main()
