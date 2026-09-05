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
    inherit_pm_gui: bool = True
    llm: dict[str, Any] = Field(default_factory=dict)
    git_remote: dict[str, Any] = Field(default_factory=dict)
    pm_gui: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] | None = Field(
        default=None,
        description="Web search settings for brainstorm. Global scope; "
        "omitted by clients that do not manage it.",
    )


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


class ResearchTestBody(BaseModel):
    research: dict[str, Any]


class BrainstormSessionBody(BaseModel):
    slug: str | None = None
    topic: str | None = None
    under: str | None = None
    mode: str = Field(default="brainstorm", pattern="^(brainstorm|roadmap)$")


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class BrainstormChatBody(BaseModel):
    slug: str
    messages: list[ChatMessage]
    llm: dict[str, Any]
    research: dict[str, Any] | None = None
    count: int = Field(default=20, ge=1, le=200)


class BrainstormIdeaBody(BaseModel):
    slug: str
    title: str = Field(..., min_length=1)
    rationale: str | None = None
    kind: str = Field(
        default="feature",
        pattern="^(feature|capability|risk|research|experiment)$",
    )
    effort: str | None = None
    evidence: list[str] | None = None


class BrainstormTriageBody(BaseModel):
    slug: str
    idea_id: str
    status: str | None = Field(
        default=None,
        pattern="^(proposed|accepted|rejected|revised)$",
    )
    title: str | None = None
    rationale: str | None = None
    kind: str | None = Field(
        default=None,
        pattern="^(feature|capability|risk|research|experiment)$",
    )
    effort: str | None = None
    recommendation: str | None = Field(
        default=None,
        pattern="^(strong|consider|park)$",
    )


class BrainstormPromoteBody(BaseModel):
    slug: str
    under: str | None = None
    type: str = Field(default="milestone", pattern="^(vision|phase|milestone|task)$")
    dry_run: bool = False
