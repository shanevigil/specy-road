"""Compose a PR/MR body markdown for finish-this-task (F-015).

The body inlines the dev-authored implementation summary first (the
"what got built" answer) and the original work-packet brief in a
collapsible <details> block (the "what was supposed to get built"
context). Reviewers — including QC reviewers who are not the
implementer — get both narratives in the PR view without having to
clone the repo and run ``specy-road brief``.

Snapshot semantics: the body is generated once at finish-this-task
time. The roadmap may change later (codename rename, planning sheet
edit); the PR body deliberately does NOT update.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _read_or_placeholder(path: Path, label: str) -> str:
    if not path.is_file():
        return f"_(no {label} on disk at `{path.name}`)_"
    try:
        return path.read_text(encoding="utf-8").rstrip()
    except (OSError, UnicodeDecodeError):
        return f"_(could not read {label} at `{path.name}`)_"


def compose_pr_body(
    *,
    work_dir: Path,
    node_id: str,
    title: str,
    codename: str | None,
    branch: str,
    integration_branch: str,
) -> str:
    """Render the PR/MR body markdown. Pure: no side effects."""
    impl_summary = _read_or_placeholder(
        work_dir / f"implementation-summary-{node_id}.md",
        "implementation summary",
    )
    brief = _read_or_placeholder(
        work_dir / f"brief-{node_id}.md",
        "work-packet brief",
    )
    cn = f" `{codename}`" if codename else ""
    head_title = f"# [{node_id}] {title}{cn}"
    snapshot_note = (
        "<!-- Snapshot generated at finish-this-task time. Roadmap node: "
        f"{node_id}. The roadmap may evolve after this PR is opened; this "
        "body does NOT update. The implementation summary is dev-authored; "
        "the work-packet brief is the deterministic compilation produced "
        "by `specy-road brief`. -->"
    )
    parts: list[str] = [
        head_title,
        "",
        snapshot_note,
        "",
        f"**Branch:** `{branch}`  →  **Integration branch:** `{integration_branch}`",
        "",
        "## Implementation summary (dev-authored)",
        "",
        impl_summary,
        "",
        "<details>",
        "<summary><strong>Original work-packet brief (snapshot)</strong></summary>",
        "",
        brief,
        "",
        "</details>",
        "",
    ]
    return "\n".join(parts)


def write_pr_body(
    *,
    work_dir: Path,
    node_id: str,
    title: str,
    codename: str | None,
    branch: str,
    integration_branch: str,
) -> Path:
    """Compose the body markdown and write it to ``work/pr-body-<NODE>.md``.

    Returns the path to the file. Caller is responsible for surfacing it
    in the printed PR/MR command (e.g. ``gh pr create --body-file``).
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / f"pr-body-{node_id}.md"
    body = compose_pr_body(
        work_dir=work_dir,
        node_id=node_id,
        title=title,
        codename=codename,
        branch=branch,
        integration_branch=integration_branch,
    )
    out.write_text(body, encoding="utf-8")
    return out


def pr_body_modes() -> Iterable[str]:
    """on_complete modes for which a PR body file is useful."""
    # 'merge' goes straight to git merge with no PR opened, so no body.
    return ("pr", "auto")
