"""Pick the best GitHub PR / GitLab MR row when APIs return multiple matches."""

from __future__ import annotations

from typing import Any


def github_pulls_for_branch(pulls: list[dict[str, Any]], branch_name: str) -> list[dict[str, Any]]:
    """Prefer PRs whose head matches `branch_name`; if none, keep full list (API oddities)."""
    br = branch_name.strip()
    matched = [p for p in pulls if (p.get("head") or {}).get("ref") == br]
    return matched if matched else pulls


def pick_latest_github_pr(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return max(candidates, key=lambda p: str(p.get("updated_at") or ""))


def gitlab_mrs_for_branch(mrs: list[dict[str, Any]], branch_name: str) -> list[dict[str, Any]]:
    """Prefer MRs whose source_branch matches; if none, use full list."""
    br = branch_name.strip()
    matched = [m for m in mrs if (m.get("source_branch") or "") == br]
    return matched if matched else mrs


def pick_latest_gitlab_mr(mrs: list[dict[str, Any]]) -> dict[str, Any]:
    return max(mrs, key=lambda m: str(m.get("updated_at") or ""))
