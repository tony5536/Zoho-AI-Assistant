from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models.tool_models import ProjectContext, RecentProject
from app.services.mock_users import resolve_canonical_mock_user_id
from app.services.oauth_users import is_oauth_user_id, resolve_oauth_user_id

router = APIRouter()


def _scoped_user_id(user_id: str) -> str:
    if is_oauth_user_id(user_id):
        return resolve_oauth_user_id(user_id)
    return resolve_canonical_mock_user_id(user_id) or user_id


class HistoryMessage(BaseModel):
    id: int | None = None
    role: str
    content: str


class DeleteSessionResponse(BaseModel):
    success: bool
    session_id: str


class DeleteMessageResponse(BaseModel):
    success: bool
    message_id: int


class MemoryContextResponse(BaseModel):
    user_id: str
    welcome_message: str | None = None
    project_context: ProjectContext | None = None
    last_active_project: ProjectContext | None = None
    frequent_project: ProjectContext | None = None
    recent_queries: list[str] = Field(default_factory=list)


class SessionRestoreResponse(BaseModel):
    user_id: str
    restored: bool = False
    session_id: str | None = None
    restore_message: str | None = None
    welcome_message: str | None = None
    messages: list[HistoryMessage] = Field(default_factory=list)
    project_context: ProjectContext | None = None
    recent_projects: list[RecentProject] = Field(default_factory=list)
    last_active_project: ProjectContext | None = None
    frequent_project: ProjectContext | None = None
    recent_queries: list[str] = Field(default_factory=list)


class RecentSessionItem(BaseModel):
    session_id: str
    title: str
    updated_at: str


@router.get("/context", response_model=MemoryContextResponse)
async def memory_context(
    request: Request,
    user_id: str = Query(..., min_length=1),
    session_id: str = Query(..., min_length=1),
) -> MemoryContextResponse:
    """Restore per-user memory into the session and return a personalized welcome."""
    memory = request.app.state.memory
    user_id = _scoped_user_id(user_id)
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


@router.get("/recent-sessions", response_model=list[RecentSessionItem])
async def recent_sessions(
    request: Request,
    user_id: str = Query(..., min_length=1),
) -> list[RecentSessionItem]:
    """List recent chat sessions for an authenticated user."""
    memory = request.app.state.memory
    rows = await memory.get_recent_sessions(_scoped_user_id(user_id))
    return [RecentSessionItem(**row) for row in rows]


@router.get("/restore", response_model=SessionRestoreResponse)
async def restore_session(
    request: Request,
    user_id: str = Query(..., min_length=1),
    session_id: str | None = Query(default=None, min_length=1),
) -> SessionRestoreResponse:
    """Restore a chat session for an authenticated user (latest, or by session_id)."""
    memory = request.app.state.memory
    user_id = _scoped_user_id(user_id)
    restored = await memory.restore_user_session(user_id, session_id=session_id)

    if restored is None:
        snapshot = await memory.restore_user_memory_on_login(user_id)
        return SessionRestoreResponse(
            user_id=user_id,
            restored=False,
            welcome_message=snapshot.welcome_message,
            last_active_project=snapshot.last_active_project,
            frequent_project=snapshot.frequent_project,
            recent_queries=snapshot.recent_queries,
        )

    snapshot = restored["snapshot"]
    project_context = restored["project_context"]
    raw_messages = restored["messages"]
    if not isinstance(raw_messages, list):
        raw_messages = []

    return SessionRestoreResponse(
        user_id=user_id,
        restored=True,
        session_id=str(restored["session_id"]),
        restore_message=str(restored["restore_message"]),
        welcome_message=snapshot.welcome_message,
        messages=[
            HistoryMessage(
                id=m.get("id"),
                role=m["role"],
                content=m["content"],
            )
            for m in raw_messages
            if isinstance(m, dict) and m.get("role") and m.get("content") is not None
        ],
        project_context=project_context if isinstance(project_context, ProjectContext) else None,
        recent_projects=restored["recent_projects"]
        if isinstance(restored["recent_projects"], list)
        else [],
        last_active_project=snapshot.last_active_project,
        frequent_project=snapshot.frequent_project,
        recent_queries=snapshot.recent_queries,
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(
    request: Request,
    session_id: str,
    user_id: str = Query(..., min_length=1),
) -> DeleteSessionResponse:
    """Delete a stored conversation (all messages and session context)."""
    memory = request.app.state.memory
    deleted = await memory.delete_session(_scoped_user_id(user_id), session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    return DeleteSessionResponse(success=True, session_id=session_id)


@router.delete("/messages/{message_id}", response_model=DeleteMessageResponse)
async def delete_message(
    request: Request,
    message_id: int,
    user_id: str = Query(..., min_length=1),
) -> DeleteMessageResponse:
    """Delete a single message from the user's chat history."""
    memory = request.app.state.memory
    deleted = await memory.delete_message(_scoped_user_id(user_id), message_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found.")
    return DeleteMessageResponse(success=True, message_id=message_id)
