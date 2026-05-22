"""Format task records for conversational list/detail replies."""

from app.models.tool_models import TaskDetails, TaskSummary


def _display_status(status: str) -> str:
    return status.replace("_", " ").title()


def _display_priority(priority: str | None) -> str:
    if not priority:
        return "Normal"
    return priority.replace("_", " ").title()


def format_task_block(task: TaskSummary | TaskDetails) -> str:
    """Single task block for list replies."""
    due = getattr(task, "due_date", None) or "Not set"
    priority = _display_priority(getattr(task, "priority", None))
    return (
        f"{task.task_id} — {task.name}\n"
        f"Status: {_display_status(task.status)}\n"
        f"Assignee: {task.assignee}\n"
        f"Due Date: {due}\n"
        f"Priority: {priority}"
    )


def format_task_list(
    tasks: list[TaskSummary | TaskDetails],
    *,
    header: str,
) -> str:
    if not tasks:
        return f"{header}:\n(no tasks)"
    blocks = [format_task_block(task) for task in tasks]
    return f"{header}:\n\n" + "\n\n".join(blocks)
