import logging

from app.graph.workflow import AssistantWorkflow
from app.memory.manager import MemoryManager
from app.models.requests import ChatRequest
from app.models.responses import ChatResponse, ResponseStatus
from app.services.mock_users import resolve_canonical_mock_user_id
from app.tools.zoho_tools import ZohoTools, set_current_user

logger = logging.getLogger(__name__)

_AUTH_ERROR_MARKERS = (
    "Zoho OAuth error",
    "Zoho API error",
    "Zoho token refresh failed",
    "refresh token is empty",
    "no valid Zoho tokens",
    "Please login again",
)

_SAFE_CHAT_ERROR_REPLY = (
    "Something went wrong while processing your message. Please try again."
)


def _is_auth_runtime_error(exc: BaseException) -> bool:
    if not isinstance(exc, RuntimeError):
        return False
    msg = str(exc)
    return any(marker in msg for marker in _AUTH_ERROR_MARKERS)


class AssistantService:
    """Orchestrates memory, LangGraph workflow, and structured API responses."""

    def __init__(
        self,
        memory: MemoryManager,
        tools: ZohoTools,
        workflow: AssistantWorkflow | None = None,
    ) -> None:
        self._memory = memory
        self._tools = tools
        self._workflow = workflow or AssistantWorkflow(tools=tools, memory=memory)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Run chat with a safe boundary so tool/workflow failures never crash /chat."""
        user_id = resolve_canonical_mock_user_id(request.user_id)
        set_current_user(user_id)
        try:
            return await self._chat_impl(request, user_id=user_id)
        except Exception as exc:
            if _is_auth_runtime_error(exc):
                raise
            logger.exception(
                "Unhandled chat error session_id=%s user_id=%s",
                request.session_id,
                request.user_id,
            )
            project_context = await self._memory.get_project_context(request.session_id)
            return ChatResponse(
                session_id=request.session_id,
                reply=_SAFE_CHAT_ERROR_REPLY,
                agent="system",
                status="error",
                requires_confirmation=False,
                pending_action=None,
                project_context=project_context,
            )

    async def _chat_impl(
        self, request: ChatRequest, *, user_id: str | None
    ) -> ChatResponse:
        if request.cancel:
            await self._memory.dismiss_pending_action(
                request.session_id,
                request.action_id,
            )
            return ChatResponse(
                session_id=request.session_id,
                reply="Change discarded — no updates were made.",
                agent="action",
                status="ok",
                requires_confirmation=False,
                pending_action=None,
                project_context=await self._memory.get_project_context(request.session_id),
            )

        user_message = request.message
        if request.confirm:
            user_message = "confirm"

        if user_id:
            await self._memory.record_user_query(user_id, request.message)
            await self._memory.sync_user_memory_on_chat(
                user_id,
                request.session_id,
            )

        history = await self._memory.get_history(request.session_id)
        project_context = await self._memory.get_project_context(request.session_id)

        await self._memory.append(
            session_id=request.session_id,
            role="user",
            content=request.message,
            user_id=user_id,
        )

        state = {
            "session_id": request.session_id,
            "user_id": user_id,
            "user_message": user_message,
            "history": history,
            "project_context": project_context,
            "confirm": request.confirm,
            "action_id": request.action_id,
        }

        result = await self._workflow.invoke(state)
        reply = result.get("reply", "I could not process that request.")
        agent = result.get("active_agent", "unknown")
        routed_to = result.get("route")
        status: ResponseStatus = result.get("status", "ok")
        requires_confirmation = result.get("requires_confirmation", False)
        pending_action = result.get("pending_action")
        tool_result = result.get("tool_result")
        updated_context = result.get("project_context") or project_context

        if user_id:
            if updated_context:
                await self._memory.save_default_project(user_id, updated_context)
            await self._memory.sync_user_memory_on_chat(
                user_id,
                request.session_id,
                user_message=request.message,
                assistant_reply=reply,
                project_context=updated_context,
            )

        await self._memory.append(
            session_id=request.session_id,
            role="assistant",
            content=reply,
            user_id=user_id,
        )

        return ChatResponse(
            session_id=request.session_id,
            reply=reply,
            agent=agent,
            routed_to=routed_to,
            status=status,
            requires_confirmation=requires_confirmation,
            pending_action=pending_action,
            project_context=updated_context,
            data=tool_result,
        )
