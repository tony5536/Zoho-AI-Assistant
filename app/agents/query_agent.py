from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import GraphState
from app.memory.manager import MemoryManager
from app.models.tool_models import ProjectContext, RecentProject, ToolResponse
from app.tools.zoho_tools import ZohoTools
from app.utils.intent import ParsedIntent, parse_intent
from app.utils.references import resolve_project_id
from app.utils.task_format import format_task_block, format_task_list
from app.utils.utilisation_format import format_utilisation_reply


class QueryAgent(BaseAgent):
    """Handles read-only Zoho operations and project context selection."""

    name = "query"

    def __init__(self, tools: ZohoTools, memory: MemoryManager) -> None:
        self._tools = tools
        self._memory = memory

    async def run(self, state: GraphState) -> dict[str, Any]:
        session_id = state["session_id"]
        message = state["user_message"]
        intent = parse_intent(message)
        context = state.get("project_context") or await self._memory.get_project_context(
            session_id
        )

        if intent.operation == "set_project_context":
            return await self._set_project_context(session_id, message, intent, context)

        if intent.operation == "list_projects":
            result = await self._tools.list_projects()
            await self._store_recent_projects(session_id, result)
            return await self._respond_tool(result, context)

        if intent.operation == "list_tasks":
            project_id = await self._resolve_project_id(session_id, message, intent, context)
            if not project_id:
                return self._error(self._unresolved_project_hint())
            context = await self._sync_project_context(session_id, project_id)
            return await self._respond_tool(
                await self._tools.list_tasks(
                    project_id,
                    status=intent.params.get("status"),
                    assignee=intent.params.get("assignee"),
                    due_date=intent.params.get("due_date"),
                ),
                context,
            )

        if intent.operation == "get_task_details":
            project_id = await self._resolve_project_id(session_id, message, intent, context)
            task_id = intent.params.get("task_id")
            if not project_id or not task_id:
                return self._error(
                    "Tell me the project and task id, e.g. task details TSK-101 in PRJ-001."
                )
            context = await self._sync_project_context(session_id, project_id)
            return await self._respond_tool(
                await self._tools.get_task_details(project_id, task_id),
                context,
            )

        if intent.operation == "list_project_members":
            project_id = await self._resolve_project_id(session_id, message, intent, context)
            if not project_id:
                return self._error(self._unresolved_project_hint())
            context = await self._sync_project_context(session_id, project_id)
            return await self._respond_tool(
                await self._tools.list_project_members(project_id),
                context,
            )

        if intent.operation == "get_task_utilisation":
            return await self._handle_utilisation(
                session_id, message, intent, context
            )

        return self._error(
            "I can list projects, tasks, members, task details, utilisation, or set project context. "
            'Try: "list projects", "list members", or "task details TSK-101".'
        )

    async def _handle_utilisation(
        self,
        session_id: str,
        message: str,
        intent: ParsedIntent,
        context: ProjectContext | None,
    ) -> dict[str, Any]:
        task_id = intent.params.get("task_id")
        if task_id:
            return await self._respond_tool(
                await self._tools.get_task_utilisation(task_id=task_id),
                context,
            )

        project_id = await self._resolve_utilisation_scope(
            session_id, message, intent, context
        )
        view = intent.params.get("view", "summary")
        result = await self._tools.get_task_utilisation(
            project_id=project_id,
            view=view,
        )
        return await self._respond_tool(result, context)

    async def _resolve_utilisation_scope(
        self,
        session_id: str,
        message: str,
        intent: ParsedIntent,
        context: ProjectContext | None,
    ) -> str | None:
        lower = message.lower()
        if any(
            phrase in lower
            for phrase in ("all projects", "across projects", "company-wide", "everyone")
        ):
            return None

        project_id = await self._resolve_project_id(session_id, message, intent, context)
        if project_id:
            return project_id

        if context and any(
            phrase in lower
            for phrase in ("current project", "this project", "our project")
        ):
            return context.project_id

        return None

    async def _sync_project_context(
        self,
        session_id: str,
        project_id: str,
    ) -> ProjectContext:
        """Remember the project the user is working in for follow-up actions."""
        recent = await self._memory.get_recent_projects(session_id)
        match = next((p for p in recent if p.project_id == project_id), None)
        if match:
            return await self._memory.set_project_context(
                session_id, match.project_id, match.name
            )

        projects_result = await self._tools.list_projects()
        if projects_result.success and projects_result.data:
            project = next(
                (p for p in projects_result.data.projects if p.project_id == project_id),
                None,
            )
            if project:
                return await self._memory.set_project_context(
                    session_id, project.project_id, project.name
                )

        return await self._memory.set_project_context(session_id, project_id, project_id)

    async def _resolve_project_id(
        self,
        session_id: str,
        message: str,
        intent: ParsedIntent,
        context: ProjectContext | None,
    ) -> str | None:
        recent = await self._memory.get_recent_projects(session_id)
        return resolve_project_id(
            message,
            explicit_id=intent.params.get("project_id"),
            project_ref=intent.params.get("project_ref"),  # type: ignore[arg-type]
            recent_projects=recent,
            project_context=context,
        )

    async def _store_recent_projects(self, session_id: str, result: ToolResponse) -> None:
        if not result.success or result.data is None:
            return
        recent = [
            RecentProject(
                project_id=p.project_id,
                name=p.name,
                position=index + 1,
            )
            for index, p in enumerate(result.data.projects)
        ]
        await self._memory.set_recent_projects(session_id, recent)

    async def _set_project_context(
        self,
        session_id: str,
        message: str,
        intent: ParsedIntent,
        current: ProjectContext | None,
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(session_id, message, intent, current)
        if not project_id:
            return self._error(self._unresolved_project_hint())

        recent = await self._memory.get_recent_projects(session_id)
        match = next((p for p in recent if p.project_id == project_id), None)
        if match:
            ctx = await self._memory.set_project_context(
                session_id, match.project_id, match.name
            )
            return {
                "reply": f"Current project set to {ctx.project_name} ({ctx.project_id}).",
                "active_agent": self.name,
                "status": "ok",
                "project_context": ctx,
                "tool_result": {"context": ctx.model_dump()},
            }

        projects_result = await self._tools.list_projects()
        if not projects_result.success or projects_result.data is None:
            return self._error("Could not load projects.")

        project = next(
            (p for p in projects_result.data.projects if p.project_id == project_id),
            None,
        )
        if project is None:
            return self._error(f"Project {project_id} not found.")

        ctx = await self._memory.set_project_context(
            session_id,
            project.project_id,
            project.name,
        )
        return {
            "reply": f"Current project set to {ctx.project_name} ({ctx.project_id}).",
            "active_agent": self.name,
            "status": "ok",
            "project_context": ctx,
            "tool_result": {"context": ctx.model_dump()},
        }

    async def _respond_tool(
        self,
        result: ToolResponse,
        context: ProjectContext | None = None,
    ) -> dict[str, Any]:
        if not result.success:
            message = result.error.message if result.error else "Request failed."
            return self._error(message)

        return {
            "reply": self._format_success(result, context),
            "active_agent": self.name,
            "status": "ok",
            "tool_result": result.to_api_dict(),
            "project_context": context,
        }

    def _format_success(
        self,
        result: ToolResponse,
        context: ProjectContext | None = None,
    ) -> str:
        if result.tool == "list_projects" and result.data:
            count = result.data.count
            noun = "project" if count == 1 else "projects"
            lines = [
                f"{i + 1}. {p.name} ({p.project_id}) — {p.status}"
                for i, p in enumerate(result.data.projects)
            ]
            return f"You have {count} {noun}:\n" + "\n".join(lines)
        if result.tool == "list_tasks" and result.data:
            label = (
                context.project_name
                if context and context.project_id == result.data.project_id
                else result.data.project_id
            )
            return format_task_list(
                result.data.tasks,
                header=f"Tasks in {label}",
            )
        if result.tool == "get_task_utilisation" and result.data:
            return format_utilisation_reply(result.data)
        if result.tool == "get_task_details" and result.data:
            d = result.data
            block = format_task_block(d)
            if d.description:
                return f"{block}\nDescription: {d.description}"
            return block
        if result.tool == "list_project_members" and result.data:
            lines = [f"- {m.name} ({m.role or 'member'})" for m in result.data.members]
            header = f"Members for {result.data.project_id}"
            return f"{header}:\n" + ("\n".join(lines) if lines else "(no members)")
        return "Done."

    def _unresolved_project_hint(self) -> str:
        return (
            "I couldn't resolve which project you mean. "
            'List projects first, then try "show tasks for the first one", '
            '"current project", or "PRJ-001".'
        )

    def _error(self, message: str) -> dict[str, Any]:
        return {
            "reply": message,
            "active_agent": self.name,
            "status": "error",
            "tool_result": None,
        }
