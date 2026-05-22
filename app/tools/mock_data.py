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
        "owner": "Alex Morgan",
    },
    {
        "project_id": "PRJ-002",
        "name": "Mobile App Launch",
        "status": "active",
        "owner": "Jamie Lee",
    },
    {
        "project_id": "PRJ-003",
        "name": "Internal IT Rollout",
        "status": "on_hold",
        "owner": "Sam Patel",
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
        "task_id": "TSK-201",
        "project_id": "PRJ-002",
        "name": "User onboarding flow",
        "status": "in_progress",
        "assignee": "Sam Patel",
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
        "assignee": "Jamie Lee",
        "hours_logged": 0.0,
        "hours_estimated": 6.0,
        "due_date": "2026-06-05",
        "priority": "low",
    },
]

_PROJECT_MEMBERS: dict[str, list[dict]] = {
    "PRJ-001": [
        {"user_id": "USR-1", "name": "Alex Morgan", "email": "alex@example.com", "role": "Manager"},
        {"user_id": "USR-2", "name": "Jamie Lee", "email": "jamie@example.com", "role": "Developer"},
    ],
    "PRJ-002": [
        {"user_id": "USR-3", "name": "Sam Patel", "email": "sam@example.com", "role": "Lead"},
        {"user_id": "USR-2", "name": "Jamie Lee", "email": "jamie@example.com", "role": "Developer"},
    ],
    "PRJ-003": [
        {"user_id": "USR-4", "name": "Taylor Kim", "email": "taylor@example.com", "role": "Admin"},
    ],
}


class MockDataStore:
    """In-memory Zoho Projects data for mock tools."""

    def __init__(self) -> None:
        self._projects = deepcopy(_INITIAL_PROJECTS)
        self._tasks = deepcopy(_INITIAL_TASKS)
        self._task_counter = 300

    def list_projects(self) -> list[ProjectSummary]:
        return [ProjectSummary(**p) for p in self._projects]

    def get_project(self, project_id: str) -> ProjectSummary | None:
        for project in self._projects:
            if project["project_id"] == project_id:
                return ProjectSummary(**project)
        return None

    def list_tasks(
        self,
        project_id: str,
        *,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> list[TaskSummary]:
        tasks = [
            TaskSummary(**{k: v for k, v in task.items() if k in TaskSummary.model_fields})
            for task in self._tasks
            if task["project_id"] == project_id
        ]
        if status and status.lower() != "all":
            tasks = [t for t in tasks if t.status.lower() == status.lower().replace(" ", "_")]
        if assignee:
            tasks = [
                t
                for t in tasks
                if assignee.lower() in t.assignee.lower()
            ]
        if due_date:
            prefix = due_date[:7] if len(due_date) >= 7 else due_date
            filtered: list[TaskSummary] = []
            for t in tasks:
                raw = next((x for x in self._tasks if x["task_id"] == t.task_id), None)
                if raw and str(raw.get("due_date", "")).startswith(prefix):
                    filtered.append(t)
            tasks = filtered
        return tasks

    def list_project_members(self, project_id: str) -> list[ProjectMember]:
        raw = _PROJECT_MEMBERS.get(project_id, [])
        return [ProjectMember(**member) for member in raw]

    def get_task_details(self, project_id: str, task_id: str) -> TaskDetails | None:
        for task in self._tasks:
            if task["task_id"] == task_id and task["project_id"] == project_id:
                base = {k: v for k, v in task.items() if k in TaskSummary.model_fields}
                return TaskDetails(
                    **base,
                    description=task.get("description", ""),
                    due_date=task.get("due_date"),
                    priority=task.get("priority"),
                )
        return None

    def get_task(self, task_id: str) -> TaskSummary | None:
        for task in self._tasks:
            if task["task_id"] == task_id:
                return TaskSummary(**task)
        return None

    def create_task(
        self,
        project_id: str,
        name: str,
        assignee: str = "Unassigned",
        hours_estimated: float = 8.0,
    ) -> TaskSummary | None:
        if not self.get_project(project_id):
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
        name: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        hours_estimated: float | None = None,
    ) -> TaskSummary | None:
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
            return TaskSummary(**task)
        return None

    def delete_task(self, task_id: str) -> bool:
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t["task_id"] != task_id]
        return len(self._tasks) < before

    def list_all_tasks(self, project_id: str | None = None) -> list[TaskSummary]:
        if project_id:
            return self.list_tasks(project_id)
        return [TaskSummary(**task) for task in self._tasks]

    def build_utilisation_summary(
        self,
        *,
        view: str = "summary",
        project_id: str | None = None,
    ) -> UtilisationSummary:
        tasks = self.list_all_tasks(project_id)
        project_name = None
        if project_id:
            project = self.get_project(project_id)
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
