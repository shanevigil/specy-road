"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os
from specy_road.planning_sheet_bootstrap import promote_placeholder
import subprocess
import uuid
import yaml

NS = uuid.UUID("05b23f6c-3e4d-4ac9-b0a0-022b4fe7f7f1")

def key(nid: str) -> str:
    return str(uuid.uuid5(NS, nid))

def node(nid: str, *, parent: str | None = None, typ: str = "task", status: str = "Not Started",
         deps: tuple[str, ...] = (), codename: str | None = "", title: str | None = None) -> dict:
    n = {"id": nid, "node_key": key(nid), "title": title or f"Leaf {nid}", "type": typ, "parent_id": parent,
         "sibling_order": int(nid.rsplit(".", 1)[-1].lstrip("M")), "status": status,
         "dependencies": [key(d) for d in deps], "touch_zones": [f"src/{nid}.py"], "acceptance": ["it works"],
         "planning_dir": f"planning/{nid}.md"}
    if codename is not None:
        n["codename"] = codename or nid.lower().replace(".", "-")
    return n

def git(repo: Path, *args: str, when: datetime | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "pat", "GIT_AUTHOR_EMAIL": "pat@example.com",
           "GIT_COMMITTER_NAME": "pat", "GIT_COMMITTER_EMAIL": "pat@example.com"}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()

def write_graph(repo: Path, nodes: list[dict], unauthored: tuple[str, ...] = ()) -> None:
    (repo / "roadmap" / "phases").mkdir(parents=True, exist_ok=True)
    (repo / "roadmap" / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M.json"]}))
    (repo / "roadmap" / "phases" / "M.json").write_text(json.dumps({"nodes": nodes}, indent=1))
    for n in nodes:
        sheet = repo / n["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        approach = promote_placeholder(n["id"]) if n["id"] in unauthored else "Write it."
        sheet.write_text(f"# {n['title']}\n\n## Intent\n\nDo it.\n\n## Approach\n\n{approach}\n")

def commit(repo: Path, msg: str, when: datetime | None = None) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg, when=when)

def make_repo(tmp_path: Path, nodes: list[dict], *, entries: tuple[dict, ...] = (),
              unauthored: tuple[str, ...] = (), when: datetime | None = None) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "dev")
    write_graph(repo, nodes, unauthored)
    (repo / "roadmap" / "registry.yaml").write_text(yaml.safe_dump({"version": 1, "entries": list(entries)}))
    (repo / "roadmap" / "git-workflow.yaml").write_text("version: 1\nintegration_branch: dev\nremote: origin\n")
    (repo / ".gitignore").write_text("work/\n.specyrd/cache/\n")
    commit(repo, "graph", when)
    return repo

def set_status(repo: Path, nid: str, status: str) -> None:
    path = repo / "roadmap" / "phases" / "M.json"
    doc = json.loads(path.read_text())
    next(n for n in doc["nodes"] if n["id"] == nid)["status"] = status
    path.write_text(json.dumps(doc, indent=1))

def branch_with(repo: Path, codename: str, *, complete: str | None = None, path: str | None = None) -> str:
    git(repo, "checkout", "-q", "-b", f"feature/rm-{codename}", "dev")
    if complete:
        set_status(repo, complete, "Complete")
    if path:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n")
    commit(repo, f"work on {codename}")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "dev")
    return sha

def claim(nid: str) -> dict:
    c = nid.lower().replace(".", "-")
    return {"codename": c, "node_id": nid, "branch": f"feature/rm-{c}", "touch_zones": [f"src/{nid}.py"]}

D1 = {"id": "D1", "kind": "decision", "node": "M1.1", "summary": "Pick the parser", "asked": "2026-11-01",
      "status": "open", "why_now": "M1.1 cannot start without it",
      "options": [{"label": "yaml", "effect": "one more dependency"}, {"label": "json", "effect": "no comments"}],
      "recommendation": "yaml", "recommendation_reason": "people edit these files by hand",
      "default_if_unanswered": "json after the deadline"}

D2 = {**D1, "id": "D2", "node": "M2.1", "summary": "Somewhere else", "needed_by": "2026-12-01"}
