"""PM GUI: publish roadmap/planning changes (scoped git commit + push)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from specy_road.gui_app_helpers import get_repo_root
from specy_road.gui_app_models import PublishRoadmapBody
from specy_road.pm_publish import publish_roadmap, publish_status_dict


def register_publish_routes(api: APIRouter) -> None:
    @api.get("/publish/status")
    def api_publish_status() -> dict:
        """Return git scope status for the Publish toolbar control."""
        return publish_status_dict(get_repo_root())

    @api.post("/publish")
    def api_publish(body: PublishRoadmapBody) -> dict:
        """Stage publish-scope paths, commit, and push to upstream."""
        root = get_repo_root()
        try:
            return publish_roadmap(root, body.message)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
