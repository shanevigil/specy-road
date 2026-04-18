"""Pydantic request/response models for the PM Gantt FastAPI app."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    type: str = Field(
        default="task",
        pattern="^(vision|phase|milestone|task|gate)$",
    )


class GuiSettingsPutBody(BaseModel):
    inherit_llm: bool = True
    inherit_git_remote: bool = False
    inherit_pm_gui: bool = True
    llm: dict[str, Any] = Field(default_factory=dict)
    git_remote: dict[str, Any] = Field(default_factory=dict)
    pm_gui: dict[str, Any] = Field(default_factory=dict)


class LlmTestBody(BaseModel):
    llm: dict[str, Any]


class LlmReviewBody(BaseModel):
    node_id: str
    llm: dict[str, Any]
    planning_body: str | None = Field(
        default=None,
        description="Live planning sheet markdown from the editor (overrides on-disk file).",
    )


class GitTestBody(BaseModel):
    git_remote: dict[str, Any]


class PutFileBody(BaseModel):
    content: str


class SharedUploadBody(BaseModel):
    path: str = Field(
        ...,
        description="Repo-relative path starting with shared/, e.g. shared/docs/x.png",
    )
    content_base64: str = Field(..., description="Raw file bytes, standard base64")


class ConstitutionScaffoldBody(BaseModel):
    force: bool = False


class PlanningScaffoldBody(BaseModel):
    planning_dir: str | None = None
    force: bool = False


class PublishRoadmapBody(BaseModel):
    """Commit message for scoped roadmap/planning publish (single line)."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Git commit message; must be a single line.",
    )
