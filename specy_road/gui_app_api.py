"""Assemble the PM Gantt JSON API router."""

from __future__ import annotations

from fastapi import APIRouter

from specy_road.gui_app_routes_core import register_core
from specy_road.gui_app_routes_nodes import (
    register_add_node,
    register_node_mutations,
)
from specy_road.gui_app_routes_planning import register_planning_routes
from specy_road.gui_app_routes_workspace import (
    register_settings_and_remote,
    register_workspace_routes,
)


def make_api_router() -> APIRouter:
    api = APIRouter(prefix="/api")
    register_core(api)
    register_node_mutations(api)
    register_add_node(api)
    register_planning_routes(api)
    register_workspace_routes(api)
    register_settings_and_remote(api)
    return api
