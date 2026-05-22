import re
from contextvars import ContextVar

import httpx

_DISPLAY_TASK_KEY = re.compile(r"^TSK-\d+$", re.IGNORECASE)

from app.models.tool_models import (
    DeleteTaskResult,
    ListProjectMembersResult,
    ListProjectsResult,
    ListTasksResult,
    TaskDetails,
    TaskMutationResult,
    TaskUtilisation,
    ToolError,
    ToolName,
    ToolResponse,
)
from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.services.zoho_client import ZohoClient
from app.tools.mock_data import MockDataStore
from app.utils.config import Settings

_current_user: ContextVar[str | None] = ContextVar("_current_user", default=None)


def set_current_user(user_id: str | None) -> None:
    _current_user.set(user_id)


def get_current_user() -> str | None:
    return _current_user.get()


class ZohoTools:
    """Eight Zoho Projects tools — live API when authenticated, mock otherwise."""

    def __init__(
        self,
        settings: Settings,
        token_store: TokenStore,
        auth_service: ZohoAuthService,
        client: ZohoClient,
        store: MockDataStore | None = None,
    ) -> None:
        self._settings = settings
        self._token_store = token_store
        self._auth = auth_service
        self._client = client
        self._mock = MockDataStore() if store is None else store

    def get_task(self, task_id: str):
        ref = task_id.upper() if _DISPLAY_TASK_KEY.match(task_id.strip()) else task_id
        return self._mock.get_task(ref, user_id=self._mock_user())

    def _mock_user(self) -> str | None:
        return get_current_user()

    async def list_projects(self) -> ToolResponse:
        live = await self._live_call("list_projects")
        if live is not None:
            return ToolResponse(tool="list_projects", success=True, data=live)
        projects = self._mock.list_projects(user_id=self._mock_user())
        return ToolResponse(
            tool="list_projects",
            success=True,
            data=ListProjectsResult(projects=projects, count=len(projects)),
        )

    async def list_tasks(
        self,
        project_id: str,
        *,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> ToolResponse:
        uid = self._mock_user()
        if not self._mock.get_project(project_id, user_id=uid) and not await self._has_live():
            return self._error("list_tasks", "PROJECT_NOT_FOUND", f"Project {project_id} not found.")

        live = await self._live_call(
            "list_tasks",
            project_id,
            status=status,
            assignee=assignee,
            due_date=due_date,
        )
        if live is not None:
            return ToolResponse(tool="list_tasks", success=True, data=live)

        if not self._mock.get_project(project_id, user_id=uid):
            return self._error("list_tasks", "PROJECT_NOT_FOUND", f"Project {project_id} not found.")
        tasks = self._mock.list_tasks(
            project_id,
            user_id=uid,
            status=status,
            assignee=assignee,
            due_date=due_date,
        )
        return ToolResponse(
            tool="list_tasks",
            success=True,
            data=ListTasksResult(project_id=project_id, tasks=tasks, count=len(tasks)),
        )

    async def get_task_details(self, project_id: str, task_id: str) -> ToolResponse:
        resolved = await self._resolve_task_ref(task_id, project_id)
        if resolved:
            task_id, project_id = resolved
        live = await self._live_call("get_task_details", project_id, task_id)
        if live is not None:
            return ToolResponse(tool="get_task_details", success=True, data=live)

        details = self._mock.get_task_details(project_id, task_id, user_id=self._mock_user())
        if details is None:
            return self._error("get_task_details", "TASK_NOT_FOUND", f"Task {task_id} not found.")
        return ToolResponse(tool="get_task_details", success=True, data=details)

    async def list_project_members(self, project_id: str) -> ToolResponse:
        live = await self._live_call("list_project_members", project_id)
        if live is not None:
            return ToolResponse(tool="list_project_members", success=True, data=live)

        uid = self._mock_user()
        if not self._mock.get_project(project_id, user_id=uid):
            return self._error(
                "list_project_members",
                "PROJECT_NOT_FOUND",
                f"Project {project_id} not found.",
            )
        members = self._mock.list_project_members(project_id, user_id=uid)
        return ToolResponse(
            tool="list_project_members",
            success=True,
            data=ListProjectMembersResult(
                project_id=project_id,
                members=members,
                count=len(members),
            ),
        )

    async def create_task(
        self,
        project_id: str,
        name: str,
        assignee: str = "Unassigned",
        hours_estimated: float = 8.0,
    ) -> ToolResponse:
        live = await self._live_call(
            "create_task",
            project_id,
            name,
            assignee=assignee,
            hours_estimated=hours_estimated,
        )
        if live is not None:
            return ToolResponse(
                tool="create_task",
                success=True,
                data=TaskMutationResult(success=True, task=live, message=f"Created task {live.task_id}."),
            )

        task = self._mock.create_task(
            project_id=project_id,
            name=name,
            user_id=self._mock_user(),
            assignee=assignee,
            hours_estimated=hours_estimated,
        )
        if task is None:
            return self._error(
                "create_task",
                "PROJECT_NOT_FOUND",
                f"Cannot create task: project {project_id} not found.",
            )
        return ToolResponse(
            tool="create_task",
            success=True,
            data=TaskMutationResult(
                success=True,
                task=task,
                message=f"Created task {task.task_id}.",
            ),
        )

    async def update_task(
        self,
        task_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        hours_estimated: float | None = None,
        due_date: str | None = None,
        priority: str | None = None,
        project_id: str | None = None,
    ) -> ToolResponse:
        resolved = await self._resolve_task_ref(task_id, project_id)
        if resolved:
            task_id, project_id = resolved
        else:
            project_id = project_id or self._resolve_project_for_task(task_id)
        if not project_id:
            return self._error("update_task", "TASK_NOT_FOUND", f"Task {task_id} not found.")

        live = await self._live_call(
            "update_task",
            project_id,
            task_id,
            name=name,
            status=status,
            assignee=assignee,
            hours_estimated=hours_estimated,
            due_date=due_date,
            priority=priority,
        )
        if live is not None:
            return ToolResponse(
                tool="update_task",
                success=True,
                data=TaskMutationResult(success=True, task=live, message=f"Updated task {task_id}."),
            )

        task = self._mock.update_task(
            task_id,
            user_id=self._mock_user(),
            name=name,
            status=status,
            assignee=assignee,
            hours_estimated=hours_estimated,
            due_date=due_date,
            priority=priority,
        )
        if task is None:
            return self._error("update_task", "TASK_NOT_FOUND", f"Task {task_id} not found.")
        return ToolResponse(
            tool="update_task",
            success=True,
            data=TaskMutationResult(success=True, task=task, message=f"Updated task {task_id}."),
        )

    async def delete_task(self, task_id: str, *, project_id: str | None = None) -> ToolResponse:
        resolved = await self._resolve_task_ref(task_id, project_id)
        if resolved:
            task_id, project_id = resolved
        else:
            project_id = project_id or self._resolve_project_for_task(task_id)

        uid = self._mock_user()
        mock_task = self._mock.get_task(task_id, user_id=uid)
        if mock_task:
            if not project_id:
                project_id = mock_task.project_id
            if self._mock.delete_task(task_id, user_id=uid):
                return ToolResponse(
                    tool="delete_task",
                    success=True,
                    data=DeleteTaskResult(
                        success=True,
                        task_id=task_id,
                        message=f"Deleted task {task_id}.",
                    ),
                )
            return self._error("delete_task", "TASK_NOT_FOUND", f"Task {task_id} not found.")

        if not project_id:
            return self._error("delete_task", "TASK_NOT_FOUND", f"Task {task_id} not found.")

        if await self._has_live():
            try:
                await self._token_bundle()
                await self._execute_live("delete_task", project_id, task_id)
                return ToolResponse(
                    tool="delete_task",
                    success=True,
                    data=DeleteTaskResult(
                        success=True,
                        task_id=task_id,
                        message=f"Deleted task {task_id}.",
                    ),
                )
            except Exception as exc:
                return self._error("delete_task", "API_ERROR", str(exc))

        return self._error("delete_task", "TASK_NOT_FOUND", f"Task {task_id} not found.")

    async def get_task_utilisation(
        self,
        task_id: str | None = None,
        *,
        project_id: str | None = None,
        view: str = "summary",
    ) -> ToolResponse:
        if task_id:
            task = self._mock.get_task_org(task_id)
            if task is None and await self._has_live():
                project_id = project_id or self._resolve_project_for_task(task_id)
                if project_id:
                    try:
                        token, domain = await self._token_bundle()
                        details = await self._client.get_task_details(
                            token, project_id, task_id, api_domain=domain
                        )
                        percent = 0.0
                        if details.hours_estimated > 0:
                            percent = round(
                                (details.hours_logged / details.hours_estimated) * 100, 1
                            )
                        return ToolResponse(
                            tool="get_task_utilisation",
                            success=True,
                            data=TaskUtilisation(
                                task_id=details.task_id,
                                project_id=details.project_id,
                                name=details.name,
                                hours_logged=details.hours_logged,
                                hours_estimated=details.hours_estimated,
                                utilisation_percent=percent,
                            ),
                        )
                    except Exception:
                        pass
            if task is None:
                return self._error(
                    "get_task_utilisation",
                    "TASK_NOT_FOUND",
                    f"Task {task_id} not found.",
                )
            percent = 0.0
            if task.hours_estimated > 0:
                percent = round((task.hours_logged / task.hours_estimated) * 100, 1)
            return ToolResponse(
                tool="get_task_utilisation",
                success=True,
                data=TaskUtilisation(
                    task_id=task.task_id,
                    project_id=task.project_id,
                    name=task.name,
                    hours_logged=task.hours_logged,
                    hours_estimated=task.hours_estimated,
                    utilisation_percent=percent,
                ),
            )

        if project_id and not self._mock.get_project_org(project_id) and not await self._has_live():
            return self._error(
                "get_task_utilisation",
                "PROJECT_NOT_FOUND",
                f"Project {project_id} not found.",
            )

        summary = self._mock.build_utilisation_summary(
            view=view,
            project_id=project_id,
        )
        return ToolResponse(tool="get_task_utilisation", success=True, data=summary)

    async def _live_call(self, operation: str, *args, **kwargs):
        if self._settings.zoho_use_mock or not await self._has_live():
            return None
        try:
            return await self._execute_live(operation, *args, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401:
                return None
            user_id = get_current_user()
            if not user_id:
                return None
            await self._token_store.refresh_access_token(user_id, self._auth)
            try:
                return await self._execute_live(operation, *args, **kwargs)
            except Exception:
                return None
        except Exception as exc:
            if isinstance(exc, RuntimeError) and ("Zoho token refresh failed" in str(exc) or "Cannot refresh access token" in str(exc)):
                raise
            return None

    async def _execute_live(self, operation: str, *args, **kwargs):
        token, domain = await self._token_bundle()
        if operation == "list_projects":
            return await self._client.list_projects(token, api_domain=domain)
        if operation == "list_tasks":
            return await self._client.list_tasks(token, args[0], api_domain=domain, **kwargs)
        if operation == "get_task_details":
            return await self._client.get_task_details(
                token, args[0], args[1], api_domain=domain
            )
        if operation == "list_project_members":
            members = await self._client.list_project_members(token, args[0], api_domain=domain)
            return ListProjectMembersResult(
                project_id=args[0], members=members, count=len(members)
            )
        if operation == "create_task":
            return await self._client.create_task(
                token, args[0], args[1], api_domain=domain, **kwargs
            )
        if operation == "update_task":
            return await self._client.update_task(
                token, args[0], args[1], api_domain=domain, **kwargs
            )
        if operation == "delete_task":
            await self._client.delete_task(token, args[0], args[1], api_domain=domain)
            return True
        return None

    async def _has_live(self) -> bool:
        if self._settings.zoho_use_mock:
            return False
        user_id = get_current_user()
        if not user_id:
            return False
        if await self._token_store.is_demo_user(user_id):
            return False
        return await self._token_store.has_valid_token(user_id)

    async def _token_bundle(self) -> tuple[str, str | None]:
        user_id = get_current_user()
        if not user_id:
            raise RuntimeError("No authenticated user")
        token = await self._token_store.ensure_valid_access_token(user_id, self._auth)
        if not token:
            raise RuntimeError("No valid access token")
        domain = await self._token_store.get_api_domain(user_id)
        return token, domain

    def _resolve_project_for_task(self, task_id: str) -> str | None:
        task = self.get_task(task_id)
        return task.project_id if task else None

    async def _resolve_task_ref(
        self, task_id: str, project_id: str | None = None
    ) -> tuple[str, str] | None:
        """Map display key (TSK-501) or API id to (api_task_id, project_id)."""
        ref = task_id.strip()
        if not ref:
            return None
        lookup = ref.upper() if _DISPLAY_TASK_KEY.match(ref) else ref
        mock_task = self._mock.get_task(lookup, user_id=self._mock_user())
        if mock_task:
            return mock_task.task_id, mock_task.project_id

        if not await self._has_live():
            return None
        try:
            token, domain = await self._token_bundle()
            return await self._client.find_task_reference(
                token,
                ref,
                api_domain=domain,
                project_id=project_id,
            )
        except Exception:
            return None

    def _error(self, tool: ToolName, code: str, message: str) -> ToolResponse:
        return ToolResponse(
            tool=tool,
            success=False,
            error=ToolError(code=code, message=message),
        )


def create_zoho_tools(
    settings: Settings,
    token_store: TokenStore,
    auth_service: ZohoAuthService,
    store: MockDataStore | None = None,
) -> ZohoTools:
    return ZohoTools(
        settings=settings,
        token_store=token_store,
        auth_service=auth_service,
        client=ZohoClient(settings),
        store=store,
    )


MockZohoTools = ZohoTools
