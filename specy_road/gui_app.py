"""FastAPI server for the PM Gantt SPA: roadmap CRUD, planning files, settings."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

def _scripts_dir() -> Path:
    """Locate ``scripts/`` (roadmap Python modules)."""
    env = os.environ.get("SPECY_ROAD_SCRIPTS")
    if env:
        p = Path(env).resolve()
        if p.is_dir():
            return p
    pkg = Path(__file__).resolve().parent
    here = pkg.parent / "scripts"
    if here.is_dir():
        return here
    cwd = Path.cwd() / "scripts"
    if cwd.is_dir():
        return cwd
    raise RuntimeError(
        "Cannot locate scripts/ (roadmap modules). Run specy-road gui from the "
        "repository root, or set SPECY_ROAD_SCRIPTS to the scripts directory.",
    )


_SCRIPTS = _scripts_dir()
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fastapi import Body, FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from roadmap_chunk_utils import find_chunk_path, roadmap_dir  # noqa: E402
from roadmap_crud_ops import (  # noqa: E402
    append_node_to_chunk,
    edit_node_set_pairs,
    merged_ids,
    run_validate_raise,
)
from roadmap_layout import (  # noqa: E402
    compute_depths,
    dependency_edges,
    ordered_tree_rows,
    sibling_sort_key,
)
from roadmap_gui_lib import (  # noqa: E402
    load_registry,
    load_settings,
    registry_by_node_id,
    resolve_repo_root,
    save_settings,
)
from roadmap_gui_remote import build_pr_hints, build_registry_enrichment  # noqa: E402
from roadmap_gui_tree import indent_parent_id, outdent_parent_id  # noqa: E402
from roadmap_load import load_roadmap  # noqa: E402
from planning_artifacts import normalize_planning_dir, planning_artifact_paths  # noqa: E402

_PKG_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _PKG_DIR / "pm_gantt_static"


def _get_repo_root() -> Path:
    env = os.environ.get("SPECY_ROAD_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return resolve_repo_root(_PKG_DIR.parent)


def _safe_rel_path(repo_root: Path, rel: str) -> Path:
    raw = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not raw or ".." in raw.split("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    p = (repo_root / raw).resolve()
    try:
        p.relative_to(repo_root.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes repo") from e
    return p


def next_child_id(nodes: list[dict], parent_id: str | None) -> str:
    children = [n["id"] for n in nodes if n.get("parent_id") == parent_id]
    if parent_id is None:
        nums: list[int] = []
        for cid in children:
            if cid.startswith("M") and "." not in cid[1:]:
                try:
                    nums.append(int(cid[1:]))
                except ValueError:
                    continue
        n = max(nums, default=-1) + 1
        return f"M{n}"
    prefix = parent_id + "."
    nums = []
    for cid in children:
        if cid.startswith(prefix):
            tail = cid[len(prefix) :]
            if tail.isdigit():
                nums.append(int(tail))
    n = max(nums, default=0) + 1
    return f"{parent_id}.{n}"


def _reindex_sibling_orders(
    root: Path,
    nodes: list[dict],
    parent_id: str | None,
    ordered_ids: list[str],
) -> None:
    by_id = {n["id"]: n for n in nodes}
    for nid in ordered_ids:
        if nid not in by_id:
            raise ValueError(f"unknown node id {nid!r}")
        if by_id[nid].get("parent_id") != parent_id:
            raise ValueError(f"node {nid} has wrong parent for reorder")
    for i, nid in enumerate(ordered_ids):
        edit_node_set_pairs(root, nid, [("sibling_order", str(i))])


class PatchPair(BaseModel):
    key: str
    value: str


class PatchBody(BaseModel):
    pairs: list[PatchPair]


class ReorderBody(BaseModel):
    parent_id: str | None = None
    ordered_child_ids: list[str]


class AddNodeBody(BaseModel):
    reference_node_id: str
    position: str = Field(..., pattern="^(above|below)$")
    title: str = Field(..., min_length=1)
    type: str = Field(default="task", pattern="^(vision|phase|milestone|task)$")


class SettingsBody(BaseModel):
    settings: dict[str, Any]


class PutFileBody(BaseModel):
    content: str


def create_app() -> FastAPI:
    app = FastAPI(title="specy-road PM Gantt API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/repo")
    def api_repo() -> dict[str, str]:
        r = _get_repo_root()
        return {"repo_root": str(r)}

    @app.get("/api/roadmap")
    def api_roadmap() -> dict[str, Any]:
        root = _get_repo_root()
        try:
            doc = load_roadmap(root)
        except (OSError, SystemExit, ValueError) as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        nodes = doc.get("nodes") or []
        reg = load_registry(root)
        by_reg = registry_by_node_id(reg)
        settings = load_settings()
        gr = settings.get("git_remote") or {}
        pr_hints = build_pr_hints(by_reg, gr)
        git_enrichment = build_registry_enrichment(by_reg, gr)
        tree_rows = ordered_tree_rows(nodes)
        ordered = [t[0] for t in tree_rows]
        row_depths = [d for _, d in tree_rows]
        depths = compute_depths(nodes)
        edges = dependency_edges(nodes)
        return {
            "version": doc.get("version"),
            "nodes": nodes,
            "registry": reg,
            "registry_by_node": by_reg,
            "tree": [
                {"id": n["id"], "outline_depth": d, "row_index": i}
                for i, (n, d) in enumerate(tree_rows)
            ],
            "dependency_depths": depths,
            "edges": [{"from": a, "to": b} for a, b in edges],
            "ordered_ids": [n["id"] for n in ordered],
            "row_depths": row_depths,
            "pr_hints": pr_hints,
            "git_enrichment": git_enrichment,
        }

    @app.patch("/api/nodes/{node_id}")
    def api_patch_node(node_id: str, body: PatchBody) -> dict[str, str]:
        root = _get_repo_root()
        pairs = [(p.key, p.value) for p in body.pairs]
        try:
            edit_node_set_pairs(root, node_id, pairs)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true", "node_id": node_id}

    @app.post("/api/outline/reorder")
    def api_reorder(body: ReorderBody) -> dict[str, str]:
        root = _get_repo_root()
        nodes = load_roadmap(root)["nodes"]
        pid: str | None = body.parent_id
        try:
            _reindex_sibling_orders(root, nodes, pid, body.ordered_child_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true"}

    @app.post("/api/nodes/{node_id}/indent")
    def api_indent(node_id: str) -> dict[str, str]:
        root = _get_repo_root()
        nodes = load_roadmap(root)["nodes"]
        by_id = {n["id"]: n for n in nodes}
        tree_rows = ordered_tree_rows(nodes)
        new_parent = indent_parent_id(tree_rows, by_id, node_id)
        if new_parent is None:
            raise HTTPException(status_code=400, detail="cannot indent")
        try:
            edit_node_set_pairs(
                root,
                node_id,
                [("parent_id", new_parent)],
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true", "parent_id": new_parent}

    @app.post("/api/nodes/{node_id}/outdent")
    def api_outdent(node_id: str) -> dict[str, str]:
        root = _get_repo_root()
        nodes = load_roadmap(root)["nodes"]
        by_id = {n["id"]: n for n in nodes}
        target = outdent_parent_id(by_id, node_id)
        if target is None:
            raise HTTPException(status_code=400, detail="cannot outdent")
        val = "" if target == "" else target
        try:
            edit_node_set_pairs(root, node_id, [("parent_id", val)])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true", "parent_id": val or None}

    @app.post("/api/nodes/add")
    def api_add_node(body: AddNodeBody) -> dict[str, Any]:
        root = _get_repo_root()
        nodes = load_roadmap(root)["nodes"]
        by_id = {n["id"]: n for n in nodes}
        ref = body.reference_node_id
        if ref not in by_id:
            raise HTTPException(status_code=404, detail="reference node not found")
        ref_node = by_id[ref]
        parent_id: str | None = ref_node.get("parent_id")
        chunk_path = find_chunk_path(root, ref)
        if not chunk_path:
            raise HTTPException(status_code=500, detail="chunk for reference not found")
        chunk_arg = str(chunk_path.relative_to(roadmap_dir(root)))

        siblings = [n["id"] for n in nodes if n.get("parent_id") == parent_id]
        siblings.sort(key=lambda nid: sibling_sort_key(nid, by_id))
        if ref not in siblings:
            raise HTTPException(status_code=400, detail="reference not in sibling list")

        ix = siblings.index(ref)
        insert_at = ix if body.position == "above" else ix + 1

        new_id = next_child_id(nodes, parent_id)
        if new_id in merged_ids(root):
            raise HTTPException(status_code=409, detail="generated id already exists")

        new_node: dict[str, Any] = {
            "id": new_id,
            "parent_id": parent_id,
            "type": body.type,
            "title": body.title,
            "status": "Not Started",
            "dependencies": [],
            "touch_zones": [],
        }

        try:
            append_node_to_chunk(root, chunk_arg, new_node)
            run_validate_raise(root)
        except (SystemExit, OSError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        nodes2 = load_roadmap(root)["nodes"]
        by_id2 = {n["id"]: n for n in nodes2}
        sib = [n["id"] for n in nodes2 if n.get("parent_id") == parent_id]
        sib.sort(key=lambda nid: sibling_sort_key(nid, by_id2))
        if new_id not in sib:
            raise HTTPException(status_code=500, detail="new node missing after add")
        sib.remove(new_id)
        sib.insert(insert_at, new_id)
        try:
            for i, nid in enumerate(sib):
                edit_node_set_pairs(root, nid, [("sibling_order", str(i))])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        return {"ok": "true", "id": new_id}

    @app.get("/api/planning/{node_id}/artifacts")
    def api_planning_artifacts(node_id: str) -> dict[str, Any]:
        root = _get_repo_root()
        nodes = load_roadmap(root)["nodes"]
        by_id = {n["id"]: n for n in nodes}
        if node_id not in by_id:
            raise HTTPException(status_code=404, detail="node not found")
        pd = by_id[node_id].get("planning_dir")
        if not isinstance(pd, str) or not pd.strip():
            return {"planning_dir": None, "files": []}
        try:
            norm = normalize_planning_dir(pd.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        paths = planning_artifact_paths(root, norm)
        out = []
        for key, p in paths.items():
            if p.is_file():
                rel = str(p.relative_to(root)).replace("\\", "/")
                out.append({"role": key, "path": rel, "exists": True})
            elif p.is_dir():
                for md in sorted(p.rglob("*.md")):
                    rel = str(md.relative_to(root)).replace("\\", "/")
                    out.append({"role": key, "path": rel, "exists": True})
        return {"planning_dir": norm, "files": out}

    @app.get("/api/planning/file")
    def api_planning_get(path: str = Query(..., description="Repo-relative path")) -> dict[str, str]:
        root = _get_repo_root()
        p = _safe_rel_path(root, path)
        if not p.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": text}

    @app.put("/api/planning/file")
    def api_planning_put(
        path: str = Query(...),
        body: PutFileBody = Body(...),
    ) -> dict[str, str]:
        root = _get_repo_root()
        p = _safe_rel_path(root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.content, encoding="utf-8")
        return {"ok": "true", "path": path}

    @app.get("/api/settings")
    def api_settings_get() -> dict[str, Any]:
        return load_settings()

    @app.put("/api/settings")
    def api_settings_put(body: SettingsBody) -> dict[str, str]:
        save_settings(body.settings)
        return {"ok": "true"}

    if _STATIC_DIR.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=_STATIC_DIR / "assets"),
            name="assets",
        )

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            index = _STATIC_DIR / "index.html"
            if full_path == "" or full_path == "/":
                return FileResponse(index)
            target = (_STATIC_DIR / full_path).resolve()
            try:
                target.relative_to(_STATIC_DIR.resolve())
            except ValueError:
                return FileResponse(index)
            if target.is_file():
                return FileResponse(target)
            return FileResponse(index)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("SPECY_ROAD_GUI_HOST", "127.0.0.1")
    port = int(os.environ.get("SPECY_ROAD_GUI_PORT", "8765"))
    uvicorn.run(
        "specy_road.gui_app:app",
        host=host,
        port=port,
        reload=os.environ.get("SPECY_ROAD_GUI_RELOAD") == "1",
    )


if __name__ == "__main__":
    main()
