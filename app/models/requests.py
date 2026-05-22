from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message to the assistant")
    session_id: str = Field(..., min_length=1, description="Conversation session identifier")
    user_id: str | None = Field(default=None, description="Optional user id for memory scoping")
    confirm: bool = Field(
        default=False,
        description="When true, executes the pending action identified by action_id",
    )
    action_id: str | None = Field(
        default=None,
        description="Pending action id to confirm (from prior confirmation_required response)",
    )
    cancel: bool = Field(
        default=False,
        description="When true, dismiss pending actions without executing them",
    )
