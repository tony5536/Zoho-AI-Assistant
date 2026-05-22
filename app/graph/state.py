from typing import Any, Literal, TypedDict

from app.models.tool_models import PendingAction, ProjectContext

Route = Literal["query", "action"]
ResponseStatus = Literal["ok", "confirmation_required", "error"]


class GraphState(TypedDict, total=False):
    session_id: str
    user_id: str | None
    user_message: str
    history: list[dict[str, str]]
    route: Route
    reply: str
    active_agent: str
    status: ResponseStatus
    confirm: bool
    action_id: str | None
    project_context: ProjectContext | None
    tool_result: dict[str, Any] | None
    pending_action: PendingAction | None
    requires_confirmation: bool
