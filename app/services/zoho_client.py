import logging
import re
from typing import Any

import httpx

_DISPLAY_TASK_KEY = re.compile(r"^TSK-\d+$", re.IGNORECASE)


def _task_ref_matches(raw: dict, ref: str, ref_upper: str) -> bool:
    api_id = str(raw.get("id_string") or raw.get("id") or "")
    if api_id == ref or api_id.upper() == ref_upper:
        return True
    key = raw.get("key") or raw.get("task_key")
    if key and str(key).upper() == ref_upper:
        return True
    prefix = raw.get("prefix") or raw.get("task_prefix") or "TSK"
    number = raw.get("number") or raw.get("task_number")
    if number is not None:
        composite = f"{prefix}-{number}".upper()
        if composite == ref_upper:
            return True
        if _DISPLAY_TASK_KEY.match(ref) and str(number) == ref_upper.split("-", 1)[-1]:
            return True
    return False

from app.models.tool_models import (
    ListProjectsResult,
    ListTasksResult,
    ProjectMember,
    ProjectSummary,
    TaskDetails,
    TaskSummary,
)
from app.utils.config import Settings

logger = logging.getLogger(__name__)


class ZohoClient:
    """Zoho Projects REST API client (OAuth bearer token)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._resolved_portal_id: str | None = None

    def _base_url(self, portal_id: str, api_domain: str | None = None) -> str:
        domain = (api_domain or self._settings.zoho_api_domain).rstrip("/")
        return f"{domain}/restapi/portal/{portal_id}"

    async def _get_portal_id(self, access_token: str, api_domain: str | None = None) -> str:
        if self._resolved_portal_id:
            return self._resolved_portal_id

        configured = self._settings.zoho_portal_id
        # If the portal ID is numeric, use it directly
        if configured.isdigit():
            logger.info("Configured ZOHO_PORTAL_ID '%s' is numeric; using it directly", configured)
            self._resolved_portal_id = configured
            return configured

        # Otherwise, query /portals/ to resolve the name to the numeric ID
        domain = (api_domain or self._settings.zoho_api_domain).rstrip("/")
        url = f"{domain}/restapi/portals/"
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        logger.info(
            "Resolving portal ID dynamically for name '%s' via URL: %s",
            configured,
            url,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                portals = payload.get("portals", [])
                
                # Check for match
                for p in portals:
                    p_name = p.get("name", "")
                    p_id = str(p.get("id") or p.get("id_string") or "")
                    if p_name.lower() == configured.lower() or p_id == configured:
                        logger.info(
                            "Resolved portal name '%s' to numeric ID '%s'",
                            configured,
                            p_id,
                        )
                        self._resolved_portal_id = p_id
                        return p_id

                # Fallback: if list is not empty, use the first portal's ID
                if portals:
                    first_id = str(portals[0].get("id") or portals[0].get("id_string") or "")
                    logger.warning(
                        "No matching portal name found for '%s'. Falling back to the first portal ID in the list: '%s'",
                        configured,
                        first_id,
                    )
                    self._resolved_portal_id = first_id
                    return first_id

                logger.warning(
                    "No portals returned by Zoho API. Falling back to configured string: '%s'",
                    configured,
                )
                self._resolved_portal_id = configured
                return configured
        except Exception as exc:
            logger.error("Error resolving portal ID dynamically: %s. Falling back to configured value.", exc)
            # Do not cache error so we can retry on next request, but return configured as fallback
            return configured

    async def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        api_domain: str | None = None,
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict[str, Any]:
        portal_id = await self._get_portal_id(access_token, api_domain)
        url = f"{self._base_url(portal_id, api_domain)}{path}"
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        logger.info("Making Zoho Projects API request: %s %s", method, url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
            )
            logger.info("Zoho Projects API responded with status: %s", response.status_code)
            if response.status_code == 401:
                logger.error("Zoho Projects API returned 401 Unauthorized. Access token may be expired or portal ID is invalid.")
            response.raise_for_status()
            if not response.content:
                return {}
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(payload["error"].get("message", "Zoho API error"))
            return payload


    async def list_projects(self, access_token: str, api_domain: str | None = None) -> ListProjectsResult:
        payload = await self._request("GET", "/projects/", access_token, api_domain=api_domain)
        projects = [
            ProjectSummary(
                project_id=str(p.get("id_string") or p.get("id")),
                name=p.get("name", ""),
                status=self._map_project_status(p),
                owner=self._owner_name(p),
            )
            for p in payload.get("projects", [])
        ]
        return ListProjectsResult(projects=projects, count=len(projects))

    async def list_tasks(
        self,
        access_token: str,
        project_id: str,
        *,
        api_domain: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> ListTasksResult:
        params: dict[str, str] = {"owner": "all"}
        if status:
            zoho_status = "completed" if status.lower() in ("completed", "done", "closed") else "notcompleted"
            if status.lower() in ("all", "open", "in_progress", "on_hold"):
                params["status"] = "all" if status.lower() == "all" else "notcompleted"
            else:
                params["status"] = zoho_status
        if assignee and assignee.lower() != "all":
            params["owner"] = assignee
        if due_date:
            due = due_date.lower()
            if due in ("today", "tomorrow", "overdue"):
                params["time"] = due

        payload = await self._request(
            "GET",
            f"/projects/{project_id}/tasks/",
            access_token,
            api_domain=api_domain,
            params=params,
        )
        tasks = [self._map_task(t, project_id) for t in payload.get("tasks", [])]
        return ListTasksResult(project_id=project_id, tasks=tasks, count=len(tasks))

    async def find_task_reference(
        self,
        access_token: str,
        task_ref: str,
        *,
        api_domain: str | None = None,
        project_id: str | None = None,
    ) -> tuple[str, str] | None:
        """Resolve a display key (e.g. TSK-501) or API id to (api_task_id, project_id)."""
        ref = task_ref.strip()
        if not ref:
            return None
        ref_upper = ref.upper()

        projects = await self.list_projects(access_token, api_domain=api_domain)
        project_ids = (
            [project_id]
            if project_id
            else [p.project_id for p in projects.projects]
        )

        for pid in project_ids:
            payload = await self._request(
                "GET",
                f"/projects/{pid}/tasks/",
                access_token,
                api_domain=api_domain,
                params={"owner": "all"},
            )
            for raw in payload.get("tasks", []):
                if _task_ref_matches(raw, ref, ref_upper):
                    return str(raw.get("id_string") or raw.get("id")), pid

        if project_id:
            try:
                await self._request(
                    "GET",
                    f"/projects/{project_id}/tasks/{ref}/",
                    access_token,
                    api_domain=api_domain,
                )
                return ref, project_id
            except httpx.HTTPStatusError:
                pass
        return None

    async def get_task_details(
        self,
        access_token: str,
        project_id: str,
        task_id: str,
        *,
        api_domain: str | None = None,
    ) -> TaskDetails:
        payload = await self._request(
            "GET",
            f"/projects/{project_id}/tasks/{task_id}/",
            access_token,
            api_domain=api_domain,
        )
        task = payload.get("tasks", [payload])[0] if payload.get("tasks") else payload
        summary = self._map_task(task, project_id)
        return TaskDetails(
            **summary.model_dump(),
            description=task.get("description") or "",
            due_date=task.get("end_date"),
            priority=task.get("priority") or task.get("priority_name"),
            created_time=task.get("created_time"),
        )

    async def list_project_members(
        self,
        access_token: str,
        project_id: str,
        *,
        api_domain: str | None = None,
    ) -> list[ProjectMember]:
        payload = await self._request(
            "GET",
            f"/projects/{project_id}/users/",
            access_token,
            api_domain=api_domain,
        )
        users = payload.get("users", payload.get("project_users", []))
        members: list[ProjectMember] = []
        for user in users:
            members.append(
                ProjectMember(
                    user_id=str(user.get("id") or user.get("zpuid") or ""),
                    name=user.get("name") or user.get("full_name", ""),
                    email=user.get("email"),
                    role=user.get("role") or user.get("profile_name"),
                )
            )
        return members

    async def create_task(
        self,
        access_token: str,
        project_id: str,
        name: str,
        *,
        api_domain: str | None = None,
        assignee: str = "Unassigned",
        hours_estimated: float = 8.0,
    ) -> TaskSummary:
        data: dict[str, str] = {"name": name}
        if assignee and assignee != "Unassigned":
            data["person_responsible"] = assignee
        payload = await self._request(
            "POST",
            f"/projects/{project_id}/tasks/",
            access_token,
            api_domain=api_domain,
            data=data,
        )
        task = payload.get("tasks", [payload])[0] if payload.get("tasks") else payload
        return self._map_task(task, project_id)

    async def update_task(
        self,
        access_token: str,
        project_id: str,
        task_id: str,
        *,
        api_domain: str | None = None,
        name: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        hours_estimated: float | None = None,
        due_date: str | None = None,
        priority: str | None = None,
    ) -> TaskSummary:
        data: dict[str, str] = {}
        if name:
            data["name"] = name
        if status:
            data["custom_status"] = status
        if assignee:
            data["person_responsible"] = assignee
        if hours_estimated is not None:
            data["work"] = str(hours_estimated)
        if due_date:
            data["end_date"] = due_date
        if priority:
            data["priority"] = priority
        payload = await self._request(
            "POST",
            f"/projects/{project_id}/tasks/{task_id}/",
            access_token,
            api_domain=api_domain,
            data=data,
        )
        task = payload.get("tasks", [payload])[0] if payload.get("tasks") else payload
        return self._map_task(task, project_id)

    async def delete_task(
        self,
        access_token: str,
        project_id: str,
        task_id: str,
        *,
        api_domain: str | None = None,
    ) -> None:
        await self._request(
            "DELETE",
            f"/projects/{project_id}/tasks/{task_id}/",
            access_token,
            api_domain=api_domain,
        )

    def _map_task(self, raw: dict, project_id: str) -> TaskSummary:
        owners = raw.get("details", {}).get("owners", [])
        assignee = owners[0]["name"] if owners else raw.get("person_responsible", "Unassigned")
        logged = self._parse_hours(raw.get("work") or raw.get("log_hours") or "0")
        estimated = self._parse_hours(raw.get("duration") or raw.get("work") or "8")
        status = "completed" if raw.get("completed") else raw.get("status", "open")
        return TaskSummary(
            task_id=str(raw.get("id_string") or raw.get("id")),
            project_id=str(raw.get("project_id") or project_id),
            name=raw.get("name", ""),
            status=str(status),
            assignee=str(assignee),
            hours_logged=logged,
            hours_estimated=estimated,
            due_date=raw.get("end_date") or raw.get("due_date"),
            priority=raw.get("priority") or raw.get("priority_name"),
        )

    def _map_project_status(self, raw: dict) -> str:
        if raw.get("project_status"):
            return str(raw["project_status"])
        if raw.get("status"):
            return str(raw["status"])
        return "active"

    def _owner_name(self, raw: dict) -> str:
        owner = raw.get("owner_name") or raw.get("owner")
        if isinstance(owner, dict):
            return owner.get("name", "")
        return str(owner or "")

    def _parse_hours(self, value: str | float | int) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if ":" in text:
            parts = text.split(":")
            try:
                return float(parts[0]) + float(parts[1]) / 60.0
            except ValueError:
                return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0
