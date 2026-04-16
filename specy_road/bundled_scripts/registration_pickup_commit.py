"""Commit message for roadmap registry registration on the integration branch."""

from __future__ import annotations

import sys

# GitHub Actions / GitLab / Azure Pipelines often honor these in commit messages
# (best-effort).
REGISTRATION_COMMIT_CI_SKIP_SUFFIX = " [skip ci] [ci skip] ***NO_CI***"


def registration_commit_message(codename: str, *, include_ci_skip: bool) -> str:
    base = f"chore(rm-{codename}): register as in-progress"
    if include_ci_skip:
        return base + REGISTRATION_COMMIT_CI_SKIP_SUFFIX
    return base


def warn_degraded_pickup(
    *,
    no_sync: bool,
    no_push_registry: bool,
    remote: str,
    base: str,
) -> None:
    """Tell stderr when sync and/or push are skipped — others may not see the claim remotely."""
    if not (no_sync or no_push_registry):
        return
    parts: list[str] = []
    if no_sync:
        parts.append("skipped integration-branch fetch/ff-merge (--no-sync)")
    if no_push_registry:
        parts.append("skipped push after register (--no-push-registry)")
    detail = "; ".join(parts)
    print(
        f"warning: do-next-available-task: {detail}. "
        f"Others will not see your registry claim on {remote}/{base} until you sync and push.",
        file=sys.stderr,
    )
