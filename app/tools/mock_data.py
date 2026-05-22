from copy import deepcopy

from app.models.tool_models import (
    AssigneeWorkload,
    ProjectMember,
    ProjectSummary,
    TaskDetails,
    TaskSummary,
    TaskUtilisationRow,
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
}


class MockDataStore:
    """In-memory Zoho Projects data scoped per mock user."""

    def __init__(self) -> None:
        self._projects = deepcopy(_INITIAL_PROJECTS)
        self._tasks = deepcopy(_INITIAL_TASKS)
        self._task_counter = 500

    def _project_ids_for_user(self, user_id: str | None) -> set[str]:
        if not user_id:
            return set()
        return {
            p["project_id"]
            for p in self._projects
            if p.get("owner_user_id") == user_id
        }

    def user_can_access_project(self, user_id: str | None, project_id: str) -> bool:
        """True when the project belongs to the user in mock data (or is unknown to mock)."""
        if not user_id:
            return False
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

    def delete_task(self, task_id: str, user_id: str | None = None) -> bool:
        if not self.get_task(task_id, user_id=user_id):
            return False
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t["task_id"] != task_id]
        return len(self._tasks) < before

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
        """Resolve any organisation task (utilisation / reporting only)."""
        for task in self._tasks:
            if task["task_id"] == task_id:
                return TaskSummary(**task)
        return None

    def list_all_tasks_org(self, project_id: str | None = None) -> list[TaskSummary]:
        """All tasks across the mock organisation (not scoped to one user)."""
        if project_id:
            return [
                TaskSummary(**task)
                for task in self._tasks
                if task["project_id"] == project_id
            ]
        return [TaskSummary(**task) for task in self._tasks]

    def build_utilisation_summary(
        self,
        *,
        view: str = "summary",
        project_id: str | None = None,
    ) -> UtilisationSummary:
        """Organisation-wide utilisation analytics across all mock users/projects."""
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

        tasks = self.list_all_tasks_org(project_id)
        project_name = None
        if project_id:
            project = self.get_project_org(project_id)
            project_name = project.name if project else None

        rows: list[TaskUtilisationRow] = []
        assignee_map: dict[str, dict] = {}

        for task in tasks:
            percent = 0.0
            if task.hours_estimated > 0:
                percent = round((task.hours_logged / task.hours_estimated) * 100, 1)
            rows.append(
                TaskUtilisationRow(
                    task_id=task.task_id,
                    project_id=task.project_id,
                    name=task.name,
                    assignee=task.assignee,
                    hours_logged=task.hours_logged,
                    hours_estimated=task.hours_estimated,
                    utilisation_percent=percent,
                )
            )
            bucket = assignee_map.setdefault(
                task.assignee,
                {"task_count": 0, "hours_logged": 0.0, "hours_estimated": 0.0, "percents": []},
            )
            bucket["task_count"] += 1
            bucket["hours_logged"] += task.hours_logged
            bucket["hours_estimated"] += task.hours_estimated
            bucket["percents"].append(percent)

        by_assignee: list[AssigneeWorkload] = []
        for assignee, stats in assignee_map.items():
            percents = stats["percents"]
            avg = round(sum(percents) / len(percents), 1) if percents else 0.0
            by_assignee.append(
                AssigneeWorkload(
                    assignee=assignee,
                    task_count=stats["task_count"],
                    hours_logged=round(stats["hours_logged"], 1),
                    hours_estimated=round(stats["hours_estimated"], 1),
                    avg_utilisation_percent=avg,
                )
            )

        by_assignee.sort(key=lambda a: a.hours_logged, reverse=True)
        top_by_tasks = max(by_assignee, key=lambda a: a.task_count).assignee if by_assignee else None
        top_by_workload = by_assignee[0].assignee if by_assignee else None

        total_logged = round(sum(t.hours_logged for t in tasks), 1)
        total_estimated = round(sum(t.hours_estimated for t in tasks), 1)

        return UtilisationSummary(
            view=view,
            scope="project" if project_id else "all_projects",
            project_id=project_id,
            project_name=project_name,
            total_tasks=len(tasks),
            total_hours_logged=total_logged,
            total_hours_estimated=total_estimated,
            by_assignee=sorted(by_assignee, key=lambda a: a.task_count, reverse=True),
            top_by_tasks=top_by_tasks,
            top_by_workload=top_by_workload,
            tasks=sorted(rows, key=lambda r: r.utilisation_percent, reverse=True),
        )
