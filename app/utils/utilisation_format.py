from app.models.tool_models import AssigneeWorkload, TaskUtilisation, UtilisationSummary


def format_utilisation_reply(data: TaskUtilisation | UtilisationSummary) -> str:
    if isinstance(data, TaskUtilisation):
        return _format_single_task(data)
    return _format_summary(data)


def _format_single_task(task: TaskUtilisation) -> str:
    if task.utilisation_percent >= 100:
        pace = "at or above estimate"
    elif task.utilisation_percent >= 75:
        pace = "tracking high"
    elif task.utilisation_percent > 0:
        pace = "in progress"
    else:
        pace = "not yet started"
    return (
        f'"{task.name}" ({task.task_id}) is {pace}: '
        f"{task.hours_logged}h logged of {task.hours_estimated}h estimated "
        f"({task.utilisation_percent}% utilisation)."
    )


def _format_summary(summary: UtilisationSummary) -> str:
    scope = (
        f"in {summary.project_name}"
        if summary.project_name
        else "across all projects"
    )
    period = summary.period_label

    if summary.view == "most_tasks":
        return _format_most_tasks(summary, scope, period)
    if summary.view == "highest_workload":
        return _format_highest_workload(summary, scope, period)
    if summary.view == "distribution":
        return _format_distribution(summary, scope, period)
    return _format_overview(summary, scope, period)


def _format_most_tasks(summary: UtilisationSummary, scope: str, period: str) -> str:
    if not summary.by_assignee:
        return f"No task assignments found {scope} for {period}."
    top = summary.by_assignee[0]
    lines = [
        f"For {period} {scope}, {top.assignee} has the most assigned tasks "
        f"({top.task_count} task{'s' if top.task_count != 1 else ''}).",
        "",
        "Task count by team member:",
        *_assignee_lines(summary.by_assignee, key="task_count"),
    ]
    return "\n".join(lines)


def _format_highest_workload(summary: UtilisationSummary, scope: str, period: str) -> str:
    if not summary.by_assignee:
        return f"No workload data found {scope} for {period}."
    by_hours = sorted(summary.by_assignee, key=lambda a: a.hours_logged, reverse=True)
    top = by_hours[0]
    lines = [
        f"For {period} {scope}, {top.assignee} carries the highest workload "
        f"with {top.hours_logged}h logged ({top.avg_utilisation_percent}% avg utilisation).",
        "",
        "Logged hours by team member:",
        *_assignee_lines(by_hours, key="hours_logged"),
    ]
    return "\n".join(lines)


def _format_distribution(summary: UtilisationSummary, scope: str, period: str) -> str:
    if not summary.by_assignee:
        return f"No tasks to summarise {scope} for {period}."
    lines = [
        f"Task distribution {scope} ({period}): "
        f"{summary.total_tasks} tasks, "
        f"{summary.total_hours_logged}h logged / {summary.total_hours_estimated}h estimated.",
        "",
        "By assignee (tasks | logged | avg utilisation):",
        *_assignee_lines(summary.by_assignee, key="full"),
    ]
    if summary.tasks:
        lines.extend(["", "Top tasks by utilisation:"])
        for row in summary.tasks[:5]:
            lines.append(
                f"  - {row.name} ({row.assignee}): "
                f"{row.utilisation_percent}% ({row.hours_logged}h/{row.hours_estimated}h)"
            )
    return "\n".join(lines)


def _append_fallback_note(text: str, summary: UtilisationSummary) -> str:
    if not summary.fallback_note:
        return text
    return f"{text}\n\nNote: {summary.fallback_note}"


def _format_status_breakdown(summary: UtilisationSummary) -> list[str]:
    lines: list[str] = []
    if summary.active_task_count is not None:
        lines.append(f"Active tasks (in utilisation): {summary.active_task_count}")
    if summary.completed_task_count is not None and summary.completed_task_count > 0:
        lines.append(
            f"Completed/archived (excluded from active counts): {summary.completed_task_count}"
        )
    if summary.overdue_task_count is not None and summary.overdue_task_count > 0:
        lines.append(f"Overdue active tasks: {summary.overdue_task_count}")
    if summary.status_groups:
        grouped = ", ".join(f"{k}: {v}" for k, v in sorted(summary.status_groups.items()))
        lines.append(f"By status: {grouped}")
    return lines


def _format_overview(summary: UtilisationSummary, scope: str, period: str) -> str:
    if not summary.by_assignee:
        base = f"No utilisation data {scope} for {period}."
        extra = _format_status_breakdown(summary)
        if extra:
            base = base + "\n" + "\n".join(extra)
        return _append_fallback_note(base, summary)
    overall = 0.0
    if summary.total_hours_estimated > 0:
        overall = round(
            (summary.total_hours_logged / summary.total_hours_estimated) * 100,
            1,
        )
    lines = [
        f"Utilisation snapshot {scope} ({period}): "
        f"{summary.total_tasks} tasks, "
        f"{summary.total_hours_logged}h logged of {summary.total_hours_estimated}h estimated "
        f"({overall}% overall).",
    ]
    if summary.top_by_workload:
        lines.append(
            f"Highest workload: {summary.top_by_workload}. "
            f"Most tasks assigned: {summary.top_by_tasks}."
        )
    breakdown = _format_status_breakdown(summary)
    lines.extend(
        [
            "",
            "Team breakdown:",
            *_assignee_lines(summary.by_assignee, key="full"),
        ]
    )
    if breakdown:
        lines.extend(["", *breakdown])
    return _append_fallback_note("\n".join(lines), summary)


def _assignee_lines(
    assignees: list[AssigneeWorkload],
    *,
    key: str,
) -> list[str]:
    lines: list[str] = []
    for person in assignees:
        if key == "task_count":
            lines.append(f"  - {person.assignee}: {person.task_count} tasks")
        elif key == "hours_logged":
            lines.append(
                f"  - {person.assignee}: {person.hours_logged}h logged "
                f"({person.avg_utilisation_percent}% avg utilisation)"
            )
        else:
            lines.append(
                f"  - {person.assignee}: {person.task_count} tasks, "
                f"{person.hours_logged}h/{person.hours_estimated}h, "
                f"{person.avg_utilisation_percent}% avg"
            )
    return lines
