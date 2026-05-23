from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import GraphState
from app.memory.manager import MemoryManager
from app.models.tool_models import PendingAction, ProjectContext, ToolError, ToolResponse
from app.tools.zoho_tools import ZohoTools
from app.utils.intent import parse_intent
from app.utils.references import resolve_project_id
from app.utils.task_intent import is_confirmation_message
from app.utils.task_references import (
    extract_task_reference,
    missing_task_context_message,
    resolve_task_reference,
)

WRITE_TOOLS = frozenset({"create_task", "update_task", "delete_task"})


class ActionAgent(BaseAgent):
    """Handles write operations with human-in-the-loop confirmation."""

    name = "action"

    def __init__(self, tools: ZohoTools, memory: MemoryManager) -> None:
        self._tools = tools
        self._memory = memory

    async def run(self, state: GraphState) -> dict[str, Any]:
        session_id = state["session_id"]
        context = state.get("project_context") or await self._memory.get_project_context(
            session_id
        )

        if state.get("confirm") or is_confirmation_message(state["user_message"]):
            return await self._execute_confirmed(session_id, state.get("action_id"), context)

        intent = parse_intent(state["user_message"])
        if intent.operation == "confirm_action":
            return await self._execute_confirmed(session_id, state.get("action_id"), context)

        if intent.operation not in WRITE_TOOLS:
            return self._error(
                "I can create, update, or delete tasks for you. "
                'For example: "Create a task called API Integration".'
            )

        task_context = await self._memory.get_task_context(session_id)
        return await self._stage_confirmation(
            session_id,
            state["user_message"],
            intent,
            context,
            task_context=task_context,
        )

    async def _stage_confirmation(
        self,
        session_id: str,
        message: str,
        intent,
        context: ProjectContext | None,
        *,
        task_context=None,
    ) -> dict[str, Any]:
        tool = intent.operation
        recent = await self._memory.get_recent_projects(session_id)
        resolved_project_id = resolve_project_id(
            message,
            explicit_id=intent.params.get("project_id"),
            project_ref=intent.params.get("project_ref"),  # type: ignore[arg-type]
            recent_projects=recent,
            project_context=context,
        )
        resolved_task_id = resolve_task_reference(
            message,
            explicit_id=intent.params.get("task_id"),
            task_context=task_context,
        )
        payload, summary, error = self._build_payload(
            tool,
            intent.params,
            context,
            resolved_project_id=resolved_project_id,
            resolved_task_id=resolved_task_id,
            message=message,
        )
        if error:
            return self._error(error)

        pending = await self._memory.create_pending_action(
            session_id=session_id,
            tool=tool,
            summary=summary,
            payload=payload,
        )
        return {
            "reply": self._confirmation_reply(tool, pending, context),
            "active_agent": self.name,
            "status": "confirmation_required",
            "requires_confirmation": True,
            "pending_action": pending,
            "project_context": context,
        }

    async def _execute_confirmed(
        self,
        session_id: str,
        action_id: str | None,
        context: ProjectContext | None,
    ) -> dict[str, Any]:
        if not action_id:
            pending = await self._memory.get_latest_pending(session_id)
            if pending is None:
                return self._error("I could not find a pending action to confirm.")
            action_id = pending.action_id

        pending = await self._memory.get_pending_action(session_id, action_id)
        if pending is None:
            return self._error("That confirmation has expired or was already handled.")

        result = await self._run_tool(pending)
        if not result.success:
            message = result.error.message if result.error else "Something went wrong."
            return self._error(message)

        await self._memory.resolve_pending_action(action_id)
        updated_context = context
        if pending.tool == "create_task" and result.data and result.data.task:
            task = result.data.task
            updated_context = await self._memory.set_project_context(
                session_id,
                task.project_id,
                await self._project_display_name(task.project_id, context),
            )
            await self._memory.set_task_context(session_id, task.task_id, task.name)
        if pending.tool == "update_task" and result.data and result.data.task:
            task = result.data.task
            await self._memory.set_task_context(session_id, task.task_id, task.name)

        return {
            "reply": self._format_success(pending, result, updated_context),
            "active_agent": self.name,
            "status": "ok",
            "requires_confirmation": False,
            "pending_action": None,
            "tool_result": result.to_api_dict(),
            "project_context": updated_context,
        }

    async def _project_display_name(
        self,
        project_id: str,
        context: ProjectContext | None,
    ) -> str:
        if context and context.project_id == project_id:
            return context.project_name
        projects = await self._tools.list_projects()
        if projects.success and projects.data:
            match = next(
                (p for p in projects.data.projects if p.project_id == project_id),
                None,
            )
            if match:
                return match.name
        return project_id

    async def _run_tool(self, pending: PendingAction) -> ToolResponse:
        payload = pending.payload
        if pending.tool == "create_task":
            return await self._tools.create_task(**payload)
        if pending.tool == "update_task":
            data = dict(payload)
            task_id = data.pop("task_id")
            project_id = data.pop("project_id", None)
            return await self._tools.update_task(task_id, project_id=project_id, **data)
        if pending.tool == "delete_task":
            return await self._tools.delete_task(
                payload["task_id"],
                project_id=payload.get("project_id"),
            )
        return ToolResponse(
            tool="create_task",
            success=False,
            error=ToolError(code="UNSUPPORTED", message=f"Unknown tool: {pending.tool}"),
        )

    def _build_payload(
        self,
        tool: str,
        params: dict,
        context: ProjectContext | None,
        *,
        resolved_project_id: str | None = None,
        resolved_task_id: str | None = None,
        message: str = "",
    ) -> tuple[dict, str, str | None]:
        if tool == "create_task":
            project_id = (
                resolved_project_id
                or params.get("project_id")
                or (context.project_id if context else None)
            )
            name = params.get("name")
            if not name:
                return (
                    {},
                    "",
                    "What should the task be called? "
                    'Try: "Create a task called API Integration".',
                )
            if not project_id:
                return (
                    {},
                    "",
                    "Which project should this task go in? "
                    'Say "use project PRJ-001" or pick one from your project list first.',
                )
            project_label = self._project_label(project_id, context)
            payload = {
                "project_id": project_id,
                "name": name,
                "assignee": params.get("assignee") or "Unassigned",
                "hours_estimated": 8.0,
            }
            summary = f'Add "{name}" to {project_label}'
            return payload, summary, None

        if tool == "update_task":
            task_id = resolved_task_id or params.get("task_id")
            if not task_id:
                if params.get("task_ref") == "contextual" or (
                    message and not params.get("task_id")
                ):
                    return {}, "", missing_task_context_message()
                return {}, "", "Which task should I update? Include the task id (e.g. TSK-101)."
            skip = {"task_id", "project_id", "project_ref"}
            updates = {
                k: v for k, v in params.items() if k not in skip and v is not None
            }
            if not updates:
                return (
                    {},
                    "",
                    "Tell me what to change (name, status, assignee, priority, or due date).",
                )
            project_id = (
                resolved_project_id
                or params.get("project_id")
                or (context.project_id if context else None)
            )
            if not project_id:
                task = self._tools.get_task(task_id)
                project_id = task.project_id if task else None
            payload = {"task_id": task_id, "project_id": project_id, **updates}
            summary = self._update_summary(task_id, updates)
            return payload, summary, None

        if tool == "delete_task":
            task_id = resolved_task_id or params.get("task_id")
            if not task_id:
                if params.get("task_ref") == "contextual" or extract_task_reference(message):
                    return {}, "", missing_task_context_message()
                return (
                    {},
                    "",
                    "Which task should be removed? Include the task id, e.g. "
                    '"delete task TSK-102" or "remove TSK-102".',
                )
            project_id = (
                resolved_project_id
                or params.get("project_id")
                or (context.project_id if context else None)
            )
            if not project_id:
                task = self._tools.get_task(task_id)
                project_id = task.project_id if task else None
            task = self._tools.get_task(task_id)
            payload = {
                "task_id": task_id,
                "project_id": project_id,
                "task_name": task.name if task else None,
            }
            summary = self._delete_summary(task_id)
            return payload, summary, None

        return {}, "", f"Unsupported action: {tool}"

    def _update_summary(self, task_id: str, updates: dict) -> str:
        task = self._tools.get_task(task_id)
        label = f'"{task.name}"' if task else task_id
        parts: list[str] = []
        if "status" in updates:
            status = str(updates["status"]).replace("_", " ")
            parts.append(f"status to {status}")
        if "assignee" in updates:
            parts.append(f"assignee to {updates['assignee']}")
        if "priority" in updates:
            parts.append(f"priority to {updates['priority']}")
        if "due_date" in updates:
            parts.append(f"due date to {updates['due_date']}")
        if "name" in updates:
            parts.append(f'name to "{updates["name"]}"')
        if "hours_estimated" in updates:
            parts.append(f"estimate to {updates['hours_estimated']}h")
        if parts:
            return f"Update {label} ({task_id}): " + ", ".join(parts)
        return f"Update {label} ({task_id})"

    def _delete_summary(self, task_id: str) -> str:
        task = self._tools.get_task(task_id)
        if task:
            return f'Remove task "{task.name}" ({task_id})'
        return f"Remove task {task_id}"

    def _project_label(
        self,
        project_id: str,
        context: ProjectContext | None,
    ) -> str:
        if context and context.project_id == project_id:
            return f"{context.project_name} ({project_id})"
        return project_id

    def _confirmation_reply(
        self,
        tool: str,
        pending: PendingAction,
        context: ProjectContext | None,
    ) -> str:
        if tool == "create_task":
            name = pending.payload.get("name", "this task")
            project_id = pending.payload.get("project_id", "")
            label = self._project_label(project_id, context)
            return (
                f'I\'ll add "{name}" to {label}. '
                f"A task ID will be assigned automatically.\n\n"
                f"Confirm to create it, or cancel to leave things as they are."
            )
        if tool == "update_task":
            task_id = pending.payload.get("task_id", "")
            task = self._tools.get_task(task_id) if task_id else None
            if task:
                return (
                    f'You are about to update "{task.name}" ({task_id}).\n'
                    f"{pending.summary}.\n\n"
                    f"Confirm to apply this change, or cancel to keep the task as-is."
                )
            return (
                f"{pending.summary}.\n\n"
                f"Confirm to apply this change, or cancel to keep the task as-is."
            )
        if tool == "delete_task":
            task_id = pending.payload.get("task_id", "")
            task = self._tools.get_task(task_id) if task_id else None
            if task:
                return (
                    f'You are about to permanently delete "{task.name}" ({task_id}).\n\n'
                    f"Confirm to proceed, or cancel to keep this task."
                )
            return (
                f"You are about to permanently delete {task_id}.\n\n"
                f"Confirm to proceed, or cancel to keep this task."
            )
        return f"{pending.summary}. Confirm to proceed, or cancel."

    def _format_success(
        self,
        pending: PendingAction,
        result: ToolResponse,
        context: ProjectContext | None,
    ) -> str:
        if pending.tool == "create_task" and result.data and result.data.task:
            task = result.data.task
            label = self._project_label(task.project_id, context)
            return (
                f'Done! "{task.name}" is now in {label} '
                f"(task ID {task.task_id})."
            )
        if pending.tool == "update_task" and result.data and result.data.task:
            task = result.data.task
            return f'Updated "{task.name}" ({task.task_id}).'
        if pending.tool == "delete_task":
            task_id = pending.payload.get("task_id", "")
            task_name = pending.payload.get("task_name")
            if task_name:
                return f'Task "{task_name}" ({task_id}) has been removed.'
            return f"Task {task_id} has been removed."
        if result.data and hasattr(result.data, "message"):
            return result.data.message
        return "All set — your change is complete."

    def _error(self, message: str) -> dict[str, Any]:
        return {
            "reply": message,
            "active_agent": self.name,
            "status": "error",
            "requires_confirmation": False,
            "pending_action": None,
            "tool_result": None,
        }
