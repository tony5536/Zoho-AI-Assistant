from app.graph.workflow import AssistantWorkflow
from app.memory.manager import MemoryManager
from app.models.requests import ChatRequest
from app.models.responses import ChatResponse, ResponseStatus
from app.tools.zoho_tools import ZohoTools, set_current_user


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
        set_current_user(request.user_id)

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

        if request.user_id:
            await self._memory.record_user_query(request.user_id, request.message)
            await self._memory.sync_user_memory_on_chat(
                request.user_id,
                request.session_id,
            )

        history = await self._memory.get_history(request.session_id)
        project_context = await self._memory.get_project_context(request.session_id)

        await self._memory.append(
            session_id=request.session_id,
            role="user",
            content=request.message,
            user_id=request.user_id,
        )

        state = {
            "session_id": request.session_id,
            "user_id": request.user_id,
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

        if request.user_id:
            if updated_context:
                await self._memory.save_default_project(request.user_id, updated_context)
            await self._memory.sync_user_memory_on_chat(
                request.user_id,
                request.session_id,
                user_message=request.message,
                assistant_reply=reply,
                project_context=updated_context,
            )

        await self._memory.append(
            session_id=request.session_id,
            role="assistant",
            content=reply,
            user_id=request.user_id,
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
