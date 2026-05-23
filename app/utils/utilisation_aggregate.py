"""Build utilisation summaries from task lists (live API or mock)."""

from datetime import date

from app.models.tool_models import (
    AssigneeWorkload,
    TaskSummary,
    TaskUtilisationRow,
    UtilisationSummary,
)
from app.tools.mock_data import is_active_for_utilisation

_COMPLETED_STATUSES = frozenset({"completed", "done", "closed", "archived", "cancelled", "deleted"})


def _normalize_status(status: str | None) -> str:
    if not status:
        return ""
    return status.lower().strip().replace(" ", "_").replace("-", "_")


def _task_as_dict(task: TaskSummary) -> dict:
    return {
        "status": task.status,
        "due_date": task.due_date,
        "assignee": task.assignee,
        "hours_logged": task.hours_logged,
        "hours_estimated": task.hours_estimated,
        "task_id": task.task_id,
        "project_id": task.project_id,
        "name": task.name,
    }


def _is_overdue(task: TaskSummary) -> bool:
    normalized = _normalize_status(task.status)
    if normalized in _COMPLETED_STATUSES:
        return False
    if not task.due_date:
        return False
    if task.due_date.lower() == "overdue":
        return True
    try:
        due = date.fromisoformat(task.due_date[:10])
    except ValueError:
        return False
    return due < date.today()


def build_utilisation_from_tasks(
    tasks: list[TaskSummary],
    *,
    view: str = "summary",
    project_id: str | None = None,
    project_name: str | None = None,
    fallback_note: str | None = None,
) -> UtilisationSummary:
    """Aggregate utilisation metrics; excludes completed/archived/deleted from active totals."""
    active_tasks = [t for t in tasks if is_active_for_utilisation(_task_as_dict(t))]
    completed_count = sum(
        1
        for t in tasks
        if _normalize_status(t.status) in _COMPLETED_STATUSES
    )
    overdue_count = sum(1 for t in active_tasks if _is_overdue(t))

    status_groups: dict[str, int] = {}
    for task in tasks:
        key = _normalize_status(task.status) or "unknown"
        status_groups[key] = status_groups.get(key, 0) + 1

    rows: list[TaskUtilisationRow] = []
    assignee_map: dict[str, dict] = {}

    for task in active_tasks:
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

    total_logged = round(sum(t.hours_logged for t in active_tasks), 1)
    total_estimated = round(sum(t.hours_estimated for t in active_tasks), 1)

    return UtilisationSummary(
        view=view,
        scope="project" if project_id else "all_projects",
        project_id=project_id,
        project_name=project_name,
        total_tasks=len(active_tasks),
        total_hours_logged=total_logged,
        total_hours_estimated=total_estimated,
        by_assignee=sorted(by_assignee, key=lambda a: a.task_count, reverse=True),
        top_by_tasks=top_by_tasks,
        top_by_workload=top_by_workload,
        tasks=sorted(rows, key=lambda r: r.utilisation_percent, reverse=True),
        active_task_count=len(active_tasks),
        completed_task_count=completed_count,
        overdue_task_count=overdue_count,
        status_groups=status_groups or None,
        fallback_note=fallback_note,
    )
