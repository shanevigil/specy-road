"""Self-heal stale registry claims and warn about orphans (F-014)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


def attempt_self_cleanup(
    *,
    repo_root: Path,
    registry_path: Path,
    node_id: str,
    codename: str,
    base: str,
    remote: str,
    git_runner,
) -> bool:
    """Best-effort: undo the registry claim after a failed pickup.

    ``git_runner(*args)`` is a callable that runs ``git`` for side effects
    and raises on failure. Returns True on success, False if cleanup itself
    failed.
    """
    try:
        if not registry_path.is_file():
            return True
        with registry_path.open(encoding="utf-8") as f:
            reg = yaml.safe_load(f) or {"version": 1, "entries": []}
        before = list(reg.get("entries") or [])
        reg["entries"] = [e for e in before if e.get("codename") != codename]
        if len(reg["entries"]) == len(before):
            return True
        with registry_path.open("w", encoding="utf-8") as f:
            yaml.dump(reg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        git_runner("add", str(registry_path))
        git_runner(
            "commit",
            "-m",
            f"chore(rm-{codename}): self-heal stale claim for {node_id} (F-014)",
        )
        try:
            git_runner("push", remote, base)
        except subprocess.CalledProcessError:
            print(
                f"warning: self-heal commit applied locally but push to "
                f"{remote}/{base} failed; run `git push {remote} {base}` to share.",
                file=sys.stderr,
            )
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"warning: self-heal cleanup itself failed: {e}", file=sys.stderr)
        return False


def emit_stale_claim_warning(node_id: str, codename: str) -> None:
    """Loud, structured warning when self-heal cannot resolve a stale claim."""
    print("=" * 70, file=sys.stderr)
    print("WARNING: stale registry claim was left behind", file=sys.stderr)
    print(f"  node:     {node_id}", file=sys.stderr)
    print(f"  codename: {codename}", file=sys.stderr)
    print(
        "  cause:    do-next-available-task failed AFTER registering the "
        "claim but BEFORE the feature branch was created and pushed; the "
        "automatic cleanup also failed.",
        file=sys.stderr,
    )
    print("  fix:      one of:", file=sys.stderr)
    print(
        f"            - `specy-road abort-task-pickup --force` "
        f"(after `git checkout -b feature/rm-{codename}`),",
        file=sys.stderr,
    )
    print(
        "            - or remove the row for codename "
        f"{codename!r} from roadmap/registry.yaml manually, commit, push.",
        file=sys.stderr,
    )
    print("=" * 70, file=sys.stderr)


def detect_stale_claims(
    *,
    repo_root: Path,
    reg: dict,
    remote: str,
) -> list[dict]:
    """Return registry entries whose feature branch exists nowhere."""
    stale: list[dict] = []
    for e in reg.get("entries") or []:
        if not isinstance(e, dict):
            continue
        branch = e.get("branch") or ""
        if not branch.startswith("feature/rm-"):
            continue
        local_ok = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            cwd=repo_root, capture_output=True, check=False,
        ).returncode == 0
        remote_ok = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/remotes/{remote}/{branch}"],
            cwd=repo_root, capture_output=True, check=False,
        ).returncode == 0
        if not local_ok and not remote_ok:
            stale.append(e)
    return stale


def warn_about_stale_claims_before_pickup(
    *,
    repo_root: Path,
    reg: dict,
    remote: str,
) -> None:
    """Surface F-014's 'next pickup detects orphan' contract."""
    stale = detect_stale_claims(repo_root=repo_root, reg=reg, remote=remote)
    for e in stale:
        emit_stale_claim_warning(e.get("node_id", "?"), e.get("codename", "?"))
