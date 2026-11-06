"""Commit message for roadmap registry registration on the integration branch."""

from __future__ import annotations

# GitHub Actions / GitLab / Azure Pipelines often honor these in commit messages
# (best-effort).
REGISTRATION_COMMIT_CI_SKIP_SUFFIX = " [skip ci] [ci skip] ***NO_CI***"


def registration_commit_message(codename: str, *, include_ci_skip: bool) -> str:
    base = f"chore(rm-{codename}): register as in-progress"
    if include_ci_skip:
        return base + REGISTRATION_COMMIT_CI_SKIP_SUFFIX
    return base


def with_policy_trailer(message: str, digest: str, commit: str) -> str:
    """``message`` with the review policy pin trailer after a blank line; the subject line is unchanged."""
    return f"{message}\n\nReview-policy: sha256:{digest} at {commit}"
