from pydantic import BaseModel, Field

from app.models.tool_models import ProjectContext


class StoredMessage(BaseModel):
    role: str
    content: str


class UserMemorySnapshot(BaseModel):
    """Long-term memory loaded for a user across sessions."""

    user_id: str
    display_name: str | None = None
    last_active_project: ProjectContext | None = None
    frequent_project: ProjectContext | None = None
    recent_queries: list[str] = Field(default_factory=list)
    welcome_message: str | None = None
