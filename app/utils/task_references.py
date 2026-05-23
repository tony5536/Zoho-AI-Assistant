"""Resolve conversational task references (that task, it, current task)."""

import re

from app.models.tool_models import TaskContext

_TSK_PATTERN = re.compile(r"\b(TSK-\d+)\b", re.IGNORECASE)

_CONTEXTUAL_TASK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(that|this|the)\s+task\b", re.IGNORECASE),
    re.compile(r"\bcurrent\s+task\b", re.IGNORECASE),
    re.compile(
        r"\b(?:update|change|modify|delete|remove|mark|assign)\s+it\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bassign\s+it\s+to\b", re.IGNORECASE),
    re.compile(r"\b(?:mark|set)\s+it\s+(?:as|to)\b", re.IGNORECASE),
]

_MISSING_TASK_MESSAGE = (
    "I couldn't determine which task you mean. "
    "Please specify a task id like TSK-101."
)


def missing_task_context_message() -> str:
    return _MISSING_TASK_MESSAGE


def get_last_task_from_session(task_context: TaskContext | None) -> TaskContext | None:
    """Return the session's last active task, if any."""
    return task_context


def extract_task_reference(message: str) -> bool:
    """True when the message refers to the session task without an explicit id."""
    if _TSK_PATTERN.search(message):
        return False
    return any(pattern.search(message) for pattern in _CONTEXTUAL_TASK_PATTERNS)


def resolve_task_reference(
    message: str,
    *,
    explicit_id: str | None = None,
    task_context: TaskContext | None = None,
) -> str | None:
    """
    Resolve a task_id from an explicit TSK id or session task context.
    Priority: explicit id > contextual phrase > None.
    """
    if explicit_id:
        return explicit_id.upper()

    if _TSK_PATTERN.search(message):
        match = _TSK_PATTERN.search(message)
        return match.group(1).upper() if match else None

    if extract_task_reference(message):
        ctx = get_last_task_from_session(task_context)
        if ctx:
            return ctx.task_id
        return None

    return None
