"""Self-heal stale registry claims and warn about orphans (F-014)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


from specy_road.registry_yaml import read_registry, write_registry


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
        reg = read_registry(registry_path)
        before = list(reg.get("entries") or [])
        reg["entries"] = [e for e in before if e.get("codename") != codename]
        if len(reg["entries"]) == len(before):
            return True
        write_registry(registry_path, reg)
        git_runner("add", str(registry_path))
        git_runner(
            "commit",
            "-m",
            f"chore(rm-{codename}): self-heal stale claim for {node_id} (F-014)",
            "--",
            str(registry_path),
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


#: Why a pre-pickup scan reports a claim. It cannot tell a dead claim from one
#: held by another clone that has not pushed its branch, so it says so.
SCAN_CAUSE = (
    "the registry claims this node but its feature branch is in neither ref "
    "checked. A claim held by another clone whose branch is not pushed looks "
    "the same from here: confirm it is dead with its owner before removing it."
)

#: Why a failed pickup reports its own claim.
ROLLBACK_CAUSE = (
    "do-next-available-task failed AFTER registering the claim but BEFORE "
    "the feature branch was created; the automatic cleanup also failed."
)


def _branch_refs(branch: str, remote: str) -> tuple[str, str]:
    return f"refs/heads/{branch}", f"refs/remotes/{remote}/{branch}"


def claim_branch_found(repo_root: Path, branch: str, remote: str) -> bool:
    """Whether ``branch`` exists as a local ref or, failing that, a remote one.

    The local ref is checked first and settles it alone: a workflow that pushes
    feature branches only at merge keeps every live claim's branch local, and
    each of those claims would otherwise read as stale.
    """
    local_ref, remote_ref = _branch_refs(branch, remote)
    return any(
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=repo_root, capture_output=True, check=False,
        ).returncode == 0
        for ref in (local_ref, remote_ref)
    )


def emit_stale_claim_warning(
    node_id: str,
    codename: str,
    *,
    branch: str,
    remote: str,
    cause: str,
) -> None:
    """Loud, structured warning for a claim whose branch exists nowhere checked.

    Callers establish that first (:func:`claim_branch_found`): the fix lines
    delete the claim, so printing them for a live one tells its reader to
    destroy work in progress.
    """
    local_ref, remote_ref = _branch_refs(branch, remote)
    print("=" * 70, file=sys.stderr)
    print("WARNING: stale registry claim was left behind", file=sys.stderr)
    print(f"  node:     {node_id}", file=sys.stderr)
    print(f"  codename: {codename}", file=sys.stderr)
    print(f"  checked:  local {local_ref} (absent)", file=sys.stderr)
    print(f"            remote {remote_ref} (absent)", file=sys.stderr)
    print(f"  cause:    {cause}", file=sys.stderr)
    print("  fix:      one of:", file=sys.stderr)
    print(
        f"            - `specy-road abort-task-pickup --force` "
        f"(after `git checkout -b {branch}`),",
        file=sys.stderr,
    )
    print(
        "            - or remove the row for codename "
        f"{codename!r} from roadmap/registry.yaml manually, commit, push.",
        file=sys.stderr,
    )
    print("=" * 70, file=sys.stderr)


def warn_unresolved_rollback(
    *,
    repo_root: Path,
    node_id: str,
    codename: str,
    branch: str,
    remote: str,
) -> None:
    """A failed pickup kept its claim: warn as stale only if the branch is gone."""
    if claim_branch_found(repo_root, branch, remote):
        print(
            f"note: the claim for {node_id} stays registered and is not stale: "
            f"{branch} exists. `git checkout {branch}` to resume it.",
            file=sys.stderr,
        )
        return
    emit_stale_claim_warning(
        node_id, codename, branch=branch, remote=remote, cause=ROLLBACK_CAUSE,
    )


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
        if not claim_branch_found(repo_root, branch, remote):
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
        emit_stale_claim_warning(
            e.get("node_id", "?"), e.get("codename", "?"),
            branch=e["branch"], remote=remote, cause=SCAN_CAUSE,
        )
