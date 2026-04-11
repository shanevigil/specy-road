"""FastAPI server for the PM Gantt SPA: roadmap CRUD, planning files, settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

def _scripts_dir() -> Path:
    """Locate bundled roadmap Python modules (``bundled_scripts/``)."""
    env = os.environ.get("SPECY_ROAD_SCRIPTS")
    if env:
        p = Path(env).resolve()
        if p.is_dir():
            return p
    pkg = Path(__file__).resolve().parent
    bundled = pkg / "bundled_scripts"
    if bundled.is_dir():
        return bundled
    legacy = pkg.parent / "scripts"
    if legacy.is_dir():
        return legacy
    cwd = Path.cwd() / "scripts"
    if cwd.is_dir():
        return cwd
    raise RuntimeError(
        "Cannot locate bundled_scripts/ (roadmap modules). Reinstall specy-road, "
        "or set SPECY_ROAD_SCRIPTS to that directory.",
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
from roadmap_gui_tree import can_indent_outline, can_outdent_outline  # noqa: E402
from roadmap_layout import (  # noqa: E402
    compute_depths,
    dependency_edges_detailed,
    dependency_inheritance_display,
    ordered_tree_rows,
    sibling_sort_key,
)
from roadmap_gui_lib import (  # noqa: E402
    apply_llm_env_from_settings,
    load_registry,
    load_settings,
    registry_by_node_id,
    resolve_repo_root,
    roadmap_fingerprint,
    save_settings,
)
from roadmap_gui_remote import (  # noqa: E402
    build_pr_hints,
    build_registry_enrichment,
    test_git_remote,
    test_llm_connection,
)
from roadmap_load import load_roadmap  # noqa: E402
from roadmap_node_keys import new_node_key  # noqa: E402
from roadmap_outline_ops import (  # noqa: E402
    apply_indent,
    apply_outdent,
    move_node_outline,
    reorder_siblings,
)
from planning_artifacts import normalize_planning_dir, planning_artifact_paths  # noqa: E402
from scaffold_planning import scaffold_planning_for_node  # noqa: E402

from review_node import ReviewError, run_review  # noqa: E402

from specy_road.constitution_scaffold import (  # noqa: E402
    ConstitutionExistsError,
    write_constitution,
)

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


class PatchPair(BaseModel):
    key: str
    value: str


class PatchBody(BaseModel):
    pairs: list[PatchPair]


class ReorderBody(BaseModel):
    parent_id: str | None = None
    ordered_child_ids: list[str]


class MoveOutlineBody(BaseModel):
    node_key: str
    new_parent_id: str | None = None
    new_index: int = Field(0, ge=0)


class AddNodeBody(BaseModel):
    reference_node_id: str
    position: str = Field(..., pattern="^(above|below)$")
    title: str = Field(..., min_length=1)
    type: str = Field(default="task", pattern="^(vision|phase|milestone|task)$")


class SettingsBody(BaseModel):
    settings: dict[str, Any]


class LlmTestBody(BaseModel):
    llm: dict[str, Any]


class LlmReviewBody(BaseModel):
    node_id: str
    llm: dict[str, Any]


class GitTestBody(BaseModel):
    git_remote: dict[str, Any]


class PutFileBody(BaseModel):
    content: str


class ConstitutionScaffoldBody(BaseModel):
    force: bool = False


class PlanningScaffoldBody(BaseModel):
    planning_dir: str | None = None
    force: bool = False


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
        edges = dependency_edges_detailed(nodes)
        by_id = {n["id"]: n for n in nodes}
        dep_inheritance = dependency_inheritance_display(nodes)
        outline_actions: dict[str, dict[str, bool]] = {}
        for n in nodes:
            nid = n["id"]
            outline_actions[nid] = {
                "can_indent": can_indent_outline(nodes, by_id, nid),
                "can_outdent": can_outdent_outline(by_id, nid),
            }
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
            "edges": edges,
            "ordered_ids": [n["id"] for n in ordered],
            "row_depths": row_depths,
            "pr_hints": pr_hints,
            "git_enrichment": git_enrichment,
            "dependency_inheritance": dep_inheritance,
            "outline_actions": outline_actions,
        }

    @app.get("/api/roadmap/fingerprint")
    def api_roadmap_fingerprint() -> dict[str, int]:
        root = _get_repo_root()
        return {"fingerprint": roadmap_fingerprint(root)}

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
        pid: str | None = body.parent_id
        try:
            reorder_siblings(root, pid, body.ordered_child_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true"}

    @app.post("/api/outline/move")
    def api_outline_move(body: MoveOutlineBody) -> dict[str, str]:
        root = _get_repo_root()
        try:
            move_node_outline(
                root,
                body.node_key,
                body.new_parent_id,
                body.new_index,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true"}

    @app.post("/api/nodes/{node_id}/indent")
    def api_indent(node_id: str) -> dict[str, Any]:
        root = _get_repo_root()
        try:
            changed = apply_indent(root, node_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "changed": changed}

    @app.post("/api/nodes/{node_id}/outdent")
    def api_outdent(node_id: str) -> dict[str, Any]:
        root = _get_repo_root()
        try:
            changed = apply_outdent(root, node_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "changed": changed}

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
            "node_key": new_node_key(),
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

    @app.post("/api/constitution/scaffold")
    def api_constitution_scaffold(
        body: ConstitutionScaffoldBody = Body(default_factory=ConstitutionScaffoldBody),
    ) -> dict[str, Any]:
        root = _get_repo_root()
        force = bool(body.force)
        try:
            result = write_constitution(root, force=force)
        except ConstitutionExistsError as e:
            raise HTTPException(
                status_code=409,
                detail={"message": str(e), "existing": list(e.existing)},
            ) from e
        return {
            "written": list(result.written),
            "skipped_existing": list(result.skipped_existing),
        }

    @app.post("/api/planning/{node_id}/scaffold")
    def api_planning_scaffold(
        node_id: str,
        body: PlanningScaffoldBody = Body(default_factory=PlanningScaffoldBody),
    ) -> dict[str, Any]:
        root = _get_repo_root()
        try:
            return scaffold_planning_for_node(
                root,
                node_id.strip(),
                planning_dir=body.planning_dir,
                force=body.force,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

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

    @app.post("/api/llm/test")
    def api_llm_test(body: LlmTestBody) -> dict[str, Any]:
        ok, msg = test_llm_connection(body.llm)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True, "message": msg}

    @app.post("/api/llm/review")
    def api_llm_review(body: LlmReviewBody) -> dict[str, str]:
        root = _get_repo_root()
        apply_llm_env_from_settings(body.llm)
        try:
            report = run_review(body.node_id.strip(), root)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ReviewError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"report": report}

    @app.post("/api/git/test")
    def api_git_test(body: GitTestBody) -> dict[str, Any]:
        ok, msg = test_git_remote(body.git_remote)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True, "message": msg}

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
