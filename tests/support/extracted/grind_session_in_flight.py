"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

def _entry(node_id, codename, branch=None):
    return {
        "node_id": node_id,
        "codename": codename,
        "branch": branch or f"feature/rm-{codename}",
    }

def _artifacts(repo_root, node_id, *, brief="brief", prompt="prompt"):
    work = repo_root / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / f"brief-{node_id}.md").write_text(brief, encoding="utf-8")
    (work / f"prompt-{node_id}.md").write_text(prompt, encoding="utf-8")
