from copy import deepcopy

from app.services.mock_users import resolve_canonical_mock_user_id
from app.utils.utilisation_aggregate import build_utilisation_from_tasks
from app.utils.utilisation_helpers import is_active_for_utilisation
from app.models.tool_models import (
    ProjectMember,
    ProjectSummary,
    TaskDetails,
    TaskSummary,
    UtilisationSummary,
)

_INITIAL_PROJECTS: list[dict] = [
    {
        "project_id": "PRJ-001",
        "name": "Website Redesign",
        "status": "active",
        "owner": "Jamie Lee",
        "owner_user_id": "mock-jamie",
    },
    {
        "project_id": "PRJ-002",
        "name": "Mobile App Launch",
        "status": "active",
        "owner": "Alex Morgan",
        "owner_user_id": "mock-alex",
    },
    {
        "project_id": "PRJ-003",
        "name": "Internal IT Rollout",
        "status": "on_hold",
        "owner": "Jamie Lee",
        "owner_user_id": "mock-jamie",
    },
    {
        "project_id": "PRJ-004",
        "name": "QA Automation",
        "status": "active",
        "owner": "Sam Patel",
        "owner_user_id": "mock-sam",
    },
    {
        "project_id": "PRJ-101",
        "name": "Customer Portal Revamp",
        "status": "active",
        "owner": "Tony Reno",
        "owner_user_id": "tony-reno",
    },
    {
        "project_id": "PRJ-102",
        "name": "Field Ops Mobile",
        "status": "active",
        "owner": "Tony Reno",
        "owner_user_id": "tony-reno",
    },
]

_INITIAL_TASKS: list[dict] = [
    {
        "task_id": "TSK-101",
        "project_id": "PRJ-001",
        "name": "API Integration",
        "status": "open",
        "assignee": "Jamie Lee",
        "hours_logged": 8.0,
        "hours_estimated": 16.0,
        "due_date": "2026-05-28",
        "description": "Connect external services to the project portal.",
        "priority": "high",
    },
    {
        "task_id": "TSK-102",
        "project_id": "PRJ-001",
        "name": "Design homepage mockups",
        "status": "in_progress",
        "assignee": "Alex Morgan",
        "hours_logged": 12.0,
        "hours_estimated": 20.0,
        "due_date": "2026-06-01",
        "description": "Homepage wireframes and visual design.",
        "priority": "medium",
    },
    {
        "task_id": "TSK-501",
        "project_id": "PRJ-101",
        "name": "SSO integration",
        "status": "open",
        "assignee": "Tony Reno",
        "hours_logged": 6.0,
        "hours_estimated": 14.0,
        "due_date": "2026-06-15",
        "description": "Single sign-on for the customer portal.",
        "priority": "high",
    },
    {
        "task_id": "TSK-502",
        "project_id": "PRJ-101",
        "name": "Portal dashboard UI",
        "status": "in_progress",
        "assignee": "Priya Shah",
        "hours_logged": 10.0,
        "hours_estimated": 18.0,
        "due_date": "2026-05-25",
        "description": "Responsive dashboard layouts and component library.",
        "priority": "medium",
    },
    {
        "task_id": "TSK-503",
        "project_id": "PRJ-101",
        "name": "API rate limiting",
        "status": "open",
        "assignee": "Alex Morgan",
        "hours_logged": 2.0,
        "hours_estimated": 10.0,
        "due_date": "2026-05-28",
        "description": "Throttle public API endpoints for the portal.",
        "priority": "high",
    },
    {
        "task_id": "TSK-504",
        "project_id": "PRJ-101",
        "name": "User acceptance testing",
        "status": "completed",
        "assignee": "Tony Reno",
        "hours_logged": 12.0,
        "hours_estimated": 12.0,
        "due_date": "2026-05-20",
        "description": "UAT sign-off for portal milestone one.",
        "priority": "low",
    },
    {
        "task_id": "TSK-505",
        "project_id": "PRJ-101",
        "name": "Accessibility audit",
        "status": "open",
        "assignee": "Priya Shah",
        "hours_logged": 0.0,
        "hours_estimated": 8.0,
        "due_date": "2026-06-02",
        "description": "WCAG review for portal flows.",
        "priority": "medium",
    },
    {
        "task_id": "TSK-511",
        "project_id": "PRJ-102",
        "name": "Offline sync module",
        "status": "in_progress",
        "assignee": "Alex Morgan",
        "hours_logged": 14.0,
        "hours_estimated": 24.0,
        "due_date": "2026-05-27",
        "description": "Queue and replay field updates when offline.",
        "priority": "high",
    },
    {
        "task_id": "TSK-512",
        "project_id": "PRJ-102",
        "name": "GPS check-in workflow",
        "status": "open",
        "assignee": "Tony Reno",
        "hours_logged": 3.0,
        "hours_estimated": 12.0,
        "due_date": "2026-06-05",
        "description": "Geofenced check-in for field technicians.",
        "priority": "medium",
    },
    {
        "task_id": "TSK-513",
        "project_id": "PRJ-102",
        "name": "Push notification templates",
        "status": "open",
        "assignee": "Priya Shah",
        "hours_logged": 1.0,
        "hours_estimated": 6.0,
        "due_date": "2026-06-08",
        "description": "Template copy and triggers for mobile alerts.",
        "priority": "low",
    },
    {
        "task_id": "TSK-514",
        "project_id": "PRJ-102",
        "name": "Field pilot rollout",
        "status": "in_progress",
        "assignee": "Tony Reno",
        "hours_logged": 8.0,
        "hours_estimated": 16.0,
        "due_date": "2026-05-30",
        "description": "Pilot with three regional field teams.",
        "priority": "high",
    },
    {
        "task_id": "TSK-515",
        "project_id": "PRJ-102",
        "name": "Crash reporting integration",
        "status": "open",
        "assignee": "Alex Morgan",
        "hours_logged": 0.0,
        "hours_estimated": 10.0,
        "due_date": "2026-06-10",
        "description": "Wire mobile crash logs to the ops dashboard.",
        "priority": "medium",
    },
    {
        "task_id": "TSK-301",
        "project_id": "PRJ-003",
        "name": "VPN rollout",
        "status": "open",
        "assignee": "Sam Patel",
        "hours_logged": 4.0,
        "hours_estimated": 12.0,
        "due_date": "2026-06-10",
        "priority": "high",
    },
    {
        "task_id": "TSK-302",
        "project_id": "PRJ-003",
        "name": "Laptop provisioning",
        "status": "in_progress",
        "assignee": "Jamie Lee",
        "hours_logged": 6.0,
        "hours_estimated": 8.0,
        "due_date": "2026-06-08",
        "priority": "medium",
    },
    {
        "task_id": "TSK-201",
        "project_id": "PRJ-002",
        "name": "User onboarding flow",
        "status": "in_progress",
        "assignee": "Alex Morgan",
        "hours_logged": 5.0,
        "hours_estimated": 10.0,
        "due_date": "2026-05-30",
        "priority": "high",
    },
    {
        "task_id": "TSK-202",
        "project_id": "PRJ-002",
        "name": "Push notification setup",
        "status": "open",
        "assignee": "Alex Morgan",
        "hours_logged": 0.0,
        "hours_estimated": 6.0,
        "due_date": "2026-06-05",
        "priority": "low",
    },
    {
        "task_id": "TSK-401",
        "project_id": "PRJ-004",
        "name": "Test plan review",
        "status": "in_progress",
        "assignee": "Sam Patel",
        "hours_logged": 10.0,
        "hours_estimated": 14.0,
        "due_date": "2026-05-29",
        "priority": "high",
    },
    {
        "task_id": "TSK-402",
        "project_id": "PRJ-004",
        "name": "Selenium suite setup",
        "status": "open",
        "assignee": "Sam Patel",
        "hours_logged": 2.0,
        "hours_estimated": 18.0,
        "due_date": "2026-06-12",
        "priority": "medium",
    },
]

_shared_store: "MockDataStore | None" = None


def get_shared_mock_store(*, reset: bool = False) -> "MockDataStore":
    """Single in-memory store for mock mode so analytics stay consistent across tool instances."""
    global _shared_store
    if _shared_store is None:
        _shared_store = MockDataStore()
    elif reset:
        _shared_store.reset()
    return _shared_store


_PROJECT_MEMBERS: dict[str, list[dict]] = {
    "PRJ-001": [
        {"user_id": "USR-1", "name": "Alex Morgan", "email": "alex@example.com", "role": "Designer"},
        {"user_id": "USR-2", "name": "Jamie Lee", "email": "jamie@example.com", "role": "Developer"},
    ],
    "PRJ-002": [
        {"user_id": "USR-1", "name": "Alex Morgan", "email": "alex@example.com", "role": "Lead"},
    ],
    "PRJ-003": [
        {"user_id": "USR-2", "name": "Jamie Lee", "email": "jamie@example.com", "role": "Owner"},
        {"user_id": "USR-3", "name": "Sam Patel", "email": "sam@example.com", "role": "IT"},
    ],
    "PRJ-004": [
        {"user_id": "USR-3", "name": "Sam Patel", "email": "sam@example.com", "role": "QA Lead"},
    ],
    "PRJ-101": [
        {
            "user_id": "USR-10",
            "name": "Tony Reno",
            "email": "tony.reno@example.com",
            "role": "Project Manager",
        },
        {
            "user_id": "USR-11",
            "name": "Alex Morgan",
            "email": "alex@example.com",
            "role": "Lead Developer",
        },
        {
            "user_id": "USR-12",
            "name": "Priya Shah",
            "email": "priya@example.com",
            "role": "UX Designer",
        },
    ],
    "PRJ-102": [
        {
            "user_id": "USR-10",
            "name": "Tony Reno",
            "email": "tony.reno@example.com",
            "role": "Project Manager",
        },
        {
            "user_id": "USR-11",
            "name": "Alex Morgan",
            "email": "alex@example.com",
            "role": "Mobile Developer",
        },
        {
            "user_id": "USR-12",
            "name": "Priya Shah",
            "email": "priya@example.com",
            "role": "QA Engineer",
        },
    ],
}


class MockDataStore:
    """In-memory Zoho Projects data scoped per mock user."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Restore seed projects/tasks for deterministic demos and tests."""
        self._projects = deepcopy(_INITIAL_PROJECTS)
        self._tasks = deepcopy(_INITIAL_TASKS)
        self._task_counter = 600

    def _project_ids_for_user(self, user_id: str | None) -> set[str]:
        uid = resolve_canonical_mock_user_id(user_id)
        if not uid:
            return set()
        return {
            p["project_id"]
            for p in self._projects
            if p.get("owner_user_id") == uid
        }

    def user_can_access_project(self, user_id: str | None, project_id: str) -> bool:
        """True when the project belongs to the user in mock data (or is unknown to mock)."""
        uid = resolve_canonical_mock_user_id(user_id)
        if not uid:
            return False
        user_id = uid
        owner: str | None = None
        found = False
        for project in self._projects:
            if project["project_id"] == project_id:
                found = True
                owner = project.get("owner_user_id")
                break
        if not found:
            return True
        return owner == user_id

    def _task_visible(self, task: dict, user_id: str | None) -> bool:
        if not user_id:
            return False
        return task["project_id"] in self._project_ids_for_user(user_id)

    def list_projects(self, user_id: str | None = None) -> list[ProjectSummary]:
        allowed = self._project_ids_for_user(user_id)
        return [
            ProjectSummary(**{k: v for k, v in p.items() if k in ProjectSummary.model_fields})
            for p in self._projects
            if p["project_id"] in allowed
        ]

    def get_project(self, project_id: str, user_id: str | None = None) -> ProjectSummary | None:
        if project_id not in self._project_ids_for_user(user_id):
            return None
        for project in self._projects:
            if project["project_id"] == project_id:
                return ProjectSummary(
                    **{k: v for k, v in project.items() if k in ProjectSummary.model_fields}
                )
        return None

    def list_tasks(
        self,
        project_id: str,
        *,
        user_id: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> list[TaskSummary]:
        if project_id not in self._project_ids_for_user(user_id):
            return []
        tasks = [
            TaskSummary(**{k: v for k, v in task.items() if k in TaskSummary.model_fields})
            for task in self._tasks
            if task["project_id"] == project_id and self._task_visible(task, user_id)
        ]
        if status and status.lower() != "all":
            tasks = [t for t in tasks if t.status.lower() == status.lower().replace(" ", "_")]
        if assignee:
            tasks = [t for t in tasks if assignee.lower() in t.assignee.lower()]
        if due_date:
            prefix = due_date[:7] if len(due_date) >= 7 else due_date
            filtered: list[TaskSummary] = []
            for t in tasks:
                raw = next((x for x in self._tasks if x["task_id"] == t.task_id), None)
                if raw and str(raw.get("due_date", "")).startswith(prefix):
                    filtered.append(t)
            tasks = filtered
        return tasks

    def list_project_members(self, project_id: str, user_id: str | None = None) -> list[ProjectMember]:
        if project_id not in self._project_ids_for_user(user_id):
            return []
        raw = _PROJECT_MEMBERS.get(project_id, [])
        return [ProjectMember(**member) for member in raw]

    def get_task_details(
        self, project_id: str, task_id: str, user_id: str | None = None
    ) -> TaskDetails | None:
        if project_id not in self._project_ids_for_user(user_id):
            return None
        for task in self._tasks:
            if task["task_id"] == task_id and task["project_id"] == project_id:
                base = {k: v for k, v in task.items() if k in TaskSummary.model_fields}
                return TaskDetails(
                    **base,
                    description=task.get("description", ""),
                    created_time=task.get("created_time"),
                )
        return None

    def get_task(self, task_id: str, user_id: str | None = None) -> TaskSummary | None:
        for task in self._tasks:
            if task["task_id"] == task_id and self._task_visible(task, user_id):
                return TaskSummary(**task)
        return None

    def create_task(
        self,
        project_id: str,
        name: str,
        *,
        user_id: str | None = None,
        assignee: str = "Unassigned",
        hours_estimated: float = 8.0,
    ) -> TaskSummary | None:
        if not self.get_project(project_id, user_id=user_id):
            return None
        self._task_counter += 1
        task = {
            "task_id": f"TSK-{self._task_counter}",
            "project_id": project_id,
            "name": name,
            "status": "open",
            "assignee": assignee,
            "hours_logged": 0.0,
            "hours_estimated": hours_estimated,
            "due_date": None,
            "priority": "medium",
        }
        self._tasks.append(task)
        return TaskSummary(**task)

    def update_task(
        self,
        task_id: str,
        *,
        user_id: str | None = None,
        name: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        hours_estimated: float | None = None,
        due_date: str | None = None,
        priority: str | None = None,
    ) -> TaskSummary | None:
        if not self.get_task(task_id, user_id=user_id):
            return None
        for task in self._tasks:
            if task["task_id"] != task_id:
                continue
            if name is not None:
                task["name"] = name
            if status is not None:
                task["status"] = status
            if assignee is not None:
                task["assignee"] = assignee
            if hours_estimated is not None:
                task["hours_estimated"] = hours_estimated
            if due_date is not None:
                task["due_date"] = due_date
            if priority is not None:
                task["priority"] = priority
            return TaskSummary(**{k: v for k, v in task.items() if k in TaskSummary.model_fields})
        return None

    def _purge_task(self, task_id: str) -> bool:
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t["task_id"] != task_id]
        return len(self._tasks) < before

    def delete_task(self, task_id: str, user_id: str | None = None) -> bool:
        if not self.get_task(task_id, user_id=user_id):
            return False
        return self._purge_task(task_id)

    def list_all_tasks(
        self, project_id: str | None = None, user_id: str | None = None
    ) -> list[TaskSummary]:
        if project_id:
            return self.list_tasks(project_id, user_id=user_id)
        allowed = self._project_ids_for_user(user_id)
        return [
            TaskSummary(**task)
            for task in self._tasks
            if task["project_id"] in allowed
        ]

    def get_project_org(self, project_id: str) -> ProjectSummary | None:
        """Resolve any organisation project (utilisation / reporting only)."""
        for project in self._projects:
            if project["project_id"] == project_id:
                return ProjectSummary(
                    **{k: v for k, v in project.items() if k in ProjectSummary.model_fields}
                )
        return None

    def get_task_org(self, task_id: str) -> TaskSummary | None:
        """Resolve any active organisation task (utilisation / reporting only)."""
        for task in self._tasks:
            if task["task_id"] == task_id and is_active_for_utilisation(task):
                return TaskSummary(
                    **{k: v for k, v in task.items() if k in TaskSummary.model_fields}
                )
        return None

    def list_tasks_for_utilisation(
        self, project_id: str | None = None
    ) -> list[TaskSummary]:
        """Active organisation tasks included in utilisation analytics."""
        tasks = [
            task
            for task in self._tasks
            if is_active_for_utilisation(task)
            and (project_id is None or task["project_id"] == project_id)
        ]
        return [
            TaskSummary(**{k: v for k, v in task.items() if k in TaskSummary.model_fields})
            for task in tasks
        ]

    def list_all_tasks_org(self, project_id: str | None = None) -> list[TaskSummary]:
        """All tasks across the mock organisation (not scoped to one user)."""
        return self.list_tasks_for_utilisation(project_id)

    def get_assignee_task_count(self, project_id: str | None = None) -> dict[str, int]:
        """Active-task counts per assignee across the mock workspace (analytics only)."""
        if project_id and not self.get_project_org(project_id):
            return {}
        counts: dict[str, int] = {}
        for task in self.list_tasks_for_utilisation(project_id):
            counts[task.assignee] = counts.get(task.assignee, 0) + 1
        return counts

    def build_utilisation_summary(
        self,
        *,
        view: str = "summary",
        project_id: str | None = None,
        user_id: str | None = None,
    ) -> UtilisationSummary:
        """Utilisation analytics across the mock workspace (not user-owned projects)."""
        del user_id  # CRUD remains user-scoped; analytics is workspace-wide.
        if project_id and not self.get_project_org(project_id):
            return UtilisationSummary(
                view=view,
                scope="project",
                project_id=project_id,
                project_name=None,
                total_tasks=0,
                total_hours_logged=0.0,
                total_hours_estimated=0.0,
                by_assignee=[],
                top_by_tasks=None,
                top_by_workload=None,
                tasks=[],
            )

        tasks = self.list_tasks_for_utilisation(project_id)
        project_name = None
        if project_id:
            project = self.get_project_org(project_id)
            project_name = project.name if project else None

        return build_utilisation_from_tasks(
            tasks,
            view=view,
            project_id=project_id,
            project_name=project_name,
        )
