"""Workspace listing, uploads, settings, and remote test API routes."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from pm_gui_git_remote_verify import set_git_remote_tested_ok

from roadmap_gui_lib import (
    apply_llm_env_from_settings,
    save_settings_for_repo,
    settings_api_payload,
)
from roadmap_gui_remote import test_git_remote, test_llm_connection

from review_node import ReviewError, run_review

from specy_road.gui_app_helpers import (
    assert_under_allowed_root,
    get_repo_root,
    safe_rel_path,
)
from specy_road.pm_gui_concurrency import require_pm_gui_write_header_env_aware
from specy_road.gui_app_models import (
    GitTestBody,
    GuiSettingsPutBody,
    LlmReviewBody,
    LlmTestBody,
    SharedUploadBody,
)


def register_workspace_routes(api: APIRouter) -> None:
    @api.get("/workspace/files")
    def api_workspace_files(
        prefix: str = Query(..., pattern="^(shared|work)$"),
    ) -> dict[str, Any]:
        root = get_repo_root()
        base = root / prefix
        if not base.exists():
            base.mkdir(parents=True, exist_ok=True)
        files_out: list[dict[str, Any]] = []
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if not p.is_file():
                    continue
                if p.name.startswith("."):
                    continue
                rel = str(p.relative_to(root)).replace("\\", "/")
                try:
                    st = p.stat()
                    files_out.append(
                        {
                            "path": rel,
                            "name": p.name,
                            "bytes": st.st_size,
                        }
                    )
                except OSError:
                    continue
        return {"prefix": prefix, "files": files_out}

    @api.post("/workspace/upload")
    def api_workspace_upload(
        body: SharedUploadBody,
        _pm: None = Depends(require_pm_gui_write_header_env_aware),
    ) -> dict[str, str]:
        root = get_repo_root()
        raw = body.path.strip().replace("\\", "/").lstrip("/")
        if not raw.startswith("shared/"):
            raise HTTPException(status_code=400, detail="path must start with shared/")
        dest = safe_rel_path(root, raw)
        assert_under_allowed_root(root, dest, "shared")
        try:
            data = base64.b64decode(body.content_base64, validate=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail="invalid base64") from e
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return {"ok": "true", "path": raw}


def register_settings_and_remote(api: APIRouter) -> None:
    @api.get("/settings")
    def api_settings_get() -> dict[str, Any]:
        return settings_api_payload(get_repo_root())

    @api.put("/settings")
    def api_settings_put(body: GuiSettingsPutBody) -> dict[str, str]:
        save_settings_for_repo(
            get_repo_root(),
            inherit_llm=body.inherit_llm,
            inherit_git_remote=body.inherit_git_remote,
            inherit_pm_gui=body.inherit_pm_gui,
            llm=body.llm,
            git_remote=body.git_remote,
            pm_gui=body.pm_gui,
        )
        return {"ok": "true"}

    @api.post("/llm/test")
    def api_llm_test(body: LlmTestBody) -> dict[str, Any]:
        ok, msg = test_llm_connection(body.llm)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True, "message": msg}

    @api.post("/llm/review")
    def api_llm_review(body: LlmReviewBody) -> dict[str, str]:
        root = get_repo_root()
        apply_llm_env_from_settings(body.llm)
        try:
            report = run_review(
                body.node_id.strip(),
                root,
                planning_body=body.planning_body,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ReviewError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"report": report}

    @api.post("/git/test")
    def api_git_test(body: GitTestBody) -> dict[str, Any]:
        ok, msg = test_git_remote(body.git_remote)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        set_git_remote_tested_ok(get_repo_root(), True)
        return {"ok": True, "message": msg, "git_remote_tested_ok": True}
