import re
from dataclasses import dataclass, field

from app.utils.references import extract_project_ref
from app.utils.task_intent import (
    extract_delete_task_id,
    extract_task_name,
    is_confirmation_message,
    is_create_task_message,
    is_delete_task_message,
)
from app.utils.utilisation_intent import detect_utilisation_view, is_utilisation_query


@dataclass
class ParsedIntent:
    operation: str
    params: dict = field(default_factory=dict)


def parse_intent(message: str) -> ParsedIntent:
    """Lightweight keyword/regex intent detection (no LLM)."""
    text = message.strip()
    lower = text.lower()

    if is_confirmation_message(text):
        return ParsedIntent(operation="confirm_action")

    if is_utilisation_query(text):
        project_id = _extract_id(text, r"\b(PRJ-\d+)\b")
        return ParsedIntent(
            operation="get_task_utilisation",
            params={
                "task_id": _extract_id(text, r"\b(TSK-\d+)\b"),
                "view": detect_utilisation_view(text),
                **_project_params(text, project_id),
            },
        )

    if _matches(
        lower,
        (
            "what projects do i have",
            "which projects do i have",
            "what projects",
            "which projects",
            "my projects",
            "list projects",
            "show projects",
            "all projects",
        ),
    ) or (
        "projects" in lower
        and "task" not in lower
        and not _matches(lower, ("project members", "team members", "members"))
    ):
        return ParsedIntent(operation="list_projects")

    if _matches(lower, ("list tasks", "show tasks", "tasks in", "tasks for", "tasks from")):
        project_id = _extract_id(text, r"\b(PRJ-\d+)\b")
        return ParsedIntent(
            operation="list_tasks",
            params={
                **_project_params(text, project_id),
                "status": _extract_status(lower),
                "assignee": _extract_assignee(text),
                "due_date": _extract_due_date(lower),
            },
        )

    if _matches(lower, ("task details", "show task", "get task", "details for task")):
        return ParsedIntent(
            operation="get_task_details",
            params={
                "task_id": _extract_id(text, r"\b(TSK-\d+)\b"),
                **_project_params(text, _extract_id(text, r"\b(PRJ-\d+)\b")),
            },
        )

    if _matches(lower, ("list members", "project members", "team members", "who is on")):
        project_id = _extract_id(text, r"\b(PRJ-\d+)\b")
        return ParsedIntent(
            operation="list_project_members",
            params=_project_params(text, project_id),
        )

    if _matches(lower, ("use project", "switch to", "focus on", "set project", "select project")):
        project_id = _extract_id(text, r"\b(PRJ-\d+)\b")
        name = _extract_quoted(text)
        return ParsedIntent(
            operation="set_project_context",
            params={**_project_params(text, project_id), "project_name": name},
        )

    ref = extract_project_ref(text)
    if ref and _matches(lower, ("use", "switch", "select", "focus", "set")):
        if not _matches(lower, ("list tasks", "show tasks", "tasks for", "tasks in")):
            return ParsedIntent(
                operation="set_project_context",
                params=_project_params(text, _extract_id(text, r"\b(PRJ-\d+)\b")),
            )

    if is_create_task_message(text):
        project_id = _extract_id(text, r"\b(PRJ-\d+)\b")
        return ParsedIntent(
            operation="create_task",
            params={
                **_project_params(text, project_id),
                "name": extract_task_name(text),
                "assignee": _extract_assignee(text),
            },
        )

    if _matches(lower, ("update task", "change task", "modify task")):
        return ParsedIntent(
            operation="update_task",
            params={
                "task_id": _extract_id(text, r"\b(TSK-\d+)\b"),
                "name": _extract_quoted(text),
                "status": _extract_status(lower),
            },
        )

    if is_delete_task_message(text):
        return ParsedIntent(
            operation="delete_task",
            params={"task_id": extract_delete_task_id(text)},
        )

    return ParsedIntent(operation="unknown")


def _project_params(text: str, project_id: str | None) -> dict:
    params: dict = {"project_id": project_id}
    if not project_id:
        ref = extract_project_ref(text)
        if ref:
            params["project_ref"] = ref
    return params


def _matches(lower: str, keywords: tuple[str, ...]) -> bool:
    return any(k in lower for k in keywords)


def _extract_id(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_quoted(text: str) -> str | None:
    match = re.search(r'"([^"]+)"|\'([^\']+)\'', text)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _extract_after(lower: str, *markers: str) -> str | None:
    for marker in markers:
        if marker in lower:
            idx = lower.index(marker) + len(marker)
            fragment = lower[idx:].strip(" :\"'")
            return fragment.split(".")[0].strip() if fragment else None
    return None


def _extract_assignee(text: str) -> str | None:
    match = re.search(r"assign(?:ee)?\s+([A-Za-z][A-Za-z\s]+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_status(lower: str) -> str | None:
    for status in ("open", "in_progress", "completed", "on_hold"):
        if status.replace("_", " ") in lower or status in lower:
            return status
    return None


def _extract_due_date(lower: str) -> str | None:
    for token in ("today", "tomorrow", "overdue", "this week", "this month"):
        if token in lower:
            return token
    match = re.search(r"\bdue\s+(\d{4}-\d{2}-\d{2})\b", lower)
    return match.group(1) if match else None
