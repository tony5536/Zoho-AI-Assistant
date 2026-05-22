from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.tool_models import PendingAction, ProjectContext

ResponseStatus = Literal["ok", "confirmation_required", "error"]


class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    agent: str = Field(description="Agent that produced the final response")
    routed_to: str | None = Field(default=None, description="Supervisor routing decision")
    status: ResponseStatus = "ok"
    requires_confirmation: bool = False
    pending_action: PendingAction | None = None
    project_context: ProjectContext | None = None
    data: dict[str, Any] | None = Field(
        default=None,
        description="Structured tool result payload when applicable",
    )
