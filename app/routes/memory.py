from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.models.tool_models import ProjectContext
router = APIRouter()


class MemoryContextResponse(BaseModel):
    user_id: str
    welcome_message: str | None = None
    project_context: ProjectContext | None = None
    last_active_project: ProjectContext | None = None
    frequent_project: ProjectContext | None = None
    recent_queries: list[str] = Field(default_factory=list)


@router.get("/context", response_model=MemoryContextResponse)
async def memory_context(
    request: Request,
    user_id: str = Query(..., min_length=1),
    session_id: str = Query(..., min_length=1),
) -> MemoryContextResponse:
    """Restore per-user memory into the session and return a personalized welcome."""
    memory = request.app.state.memory
    snapshot = await memory.restore_user_memory_on_login(user_id)
    project_context = await memory.apply_user_memory_to_session(user_id, session_id)
    welcome = snapshot.welcome_message
    if project_context and welcome:
        welcome = f"{welcome} Current project: {project_context.project_name}."
    elif project_context:
        welcome = f"Current project: {project_context.project_name}."
    return MemoryContextResponse(
        user_id=user_id,
        welcome_message=welcome,
        project_context=project_context,
        last_active_project=snapshot.last_active_project,
        frequent_project=snapshot.frequent_project,
        recent_queries=snapshot.recent_queries,
    )
