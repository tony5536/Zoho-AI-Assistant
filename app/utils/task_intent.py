"""Natural-language parsing helpers for task actions (rule-based, no LLM)."""

import re
from typing import Any

_CREATE_TASK_RE = re.compile(r"\b(create|add|new)\s+(?:a\s+)?task\b", re.IGNORECASE)

_TASK_NAME_PATTERNS = [
    re.compile(
        r"(?:create|add|new)\s+(?:a\s+)?task\s+(?:called|named|titled)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:create|add|new)\s+(?:a\s+)?task\s+(.+)",
        re.IGNORECASE,
    ),
]

_TRAILING_CLAUSE_RE = re.compile(
    r"\s+(?:in|for|on|to)\s+(?:PRJ-\d+|the\s+.+|project\b.+)$",
    re.IGNORECASE,
)
_ASSIGNEE_CLAUSE_RE = re.compile(r"\s+assign(?:ee)?\s+.+$", re.IGNORECASE)
_LEADING_LABEL_RE = re.compile(r"^(?:called|named|titled)\s+", re.IGNORECASE)


_TSK_PATTERN = re.compile(r"\b(TSK-\d+)\b", re.IGNORECASE)

_DELETE_TASK_PATTERNS = [
    re.compile(
        r"\b(delete|remove)\s+(?:a\s+)?(?:the\s+)?task\s+(TSK-\d+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(delete|remove)\s+(TSK-\d+)\b", re.IGNORECASE),
]

_CONFIRM_PHRASES = frozenset(
    {"yes", "confirm", "confirmed", "approve", "approved", "proceed", "ok", "okay"}
)


def is_create_task_message(message: str) -> bool:
    return bool(_CREATE_TASK_RE.search(message))


def is_delete_task_message(message: str) -> bool:
    if any(p.search(message) for p in _DELETE_TASK_PATTERNS):
        return True
    if re.search(r"\b(delete|remove)\b", message, re.IGNORECASE) and _TSK_PATTERN.search(
        message
    ):
        return True
    return False


def is_confirmation_message(message: str) -> bool:
    return message.strip().lower() in _CONFIRM_PHRASES


def extract_delete_task_id(message: str) -> str | None:
    for pattern in _DELETE_TASK_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(2).upper()
    if re.search(r"\b(delete|remove)\b", message, re.IGNORECASE):
        tsk = _TSK_PATTERN.search(message)
        if tsk:
            return tsk.group(1).upper()
    return None


def extract_task_name(message: str) -> str | None:
    """Extract task title from natural-language create prompts."""
    quoted = _extract_quoted(message)
    if quoted:
        return _clean_task_name(quoted)

    for pattern in _TASK_NAME_PATTERNS:
        match = pattern.search(message)
        if match:
            name = _clean_task_name(match.group(1))
            if name and not _looks_like_full_command(name, message):
                return name
    return None


def _looks_like_full_command(name: str, message: str) -> bool:
    """Reject captures that are effectively the whole user message."""
    normalized_name = re.sub(r"\s+", " ", name.strip().lower())
    normalized_message = re.sub(r"\s+", " ", message.strip().lower())
    if normalized_name == normalized_message:
        return True
    if normalized_name.startswith("create ") and "task" in normalized_name:
        return True
    return False


def _extract_quoted(text: str) -> str | None:
    match = re.search(r'"([^"]+)"|\'([^\']+)\'', text)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _clean_task_name(raw: str) -> str:
    name = raw.strip().strip("\"'")
    name = _LEADING_LABEL_RE.sub("", name)
    name = _TRAILING_CLAUSE_RE.sub("", name)
    name = _ASSIGNEE_CLAUSE_RE.sub("", name)
    name = re.split(r"[.!?]\s+", name, maxsplit=1)[0]
    return name.rstrip(".,!? ").strip()


_UPDATE_TASK_RE = re.compile(
    r"\b(update|change|modify)\s+(?:a\s+)?(?:the\s+)?task\b",
    re.IGNORECASE,
)

_MARK_STATUS_RE = re.compile(
    r"\bmark\s+(TSK-\d+)\s+as\s+(\w+(?:\s+\w+)?)",
    re.IGNORECASE,
)

_ASSIGN_TO_RE = re.compile(
    r"\bassign\s+(TSK-\d+)\s+to\s+(.+?)(?:\s*$|\.)",
    re.IGNORECASE,
)

_PRIORITY_RE = re.compile(
    r"\b(?:change|set|update)\s+priority\s+of\s+(TSK-\d+)\s+to\s+(\w+)",
    re.IGNORECASE,
)

_DUE_DATE_RE = re.compile(
    r"\b(?:change|set|update)\s+due\s+date\s+of\s+(TSK-\d+)\s+to\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

_STATUS_ALIASES: dict[str, str] = {
    "complete": "completed",
    "completed": "completed",
    "done": "completed",
    "open": "open",
    "in progress": "in_progress",
    "in_progress": "in_progress",
    "on hold": "on_hold",
    "on_hold": "on_hold",
}


def is_update_task_message(message: str) -> bool:
    """True when the message requests a task field change (not create/delete)."""
    if not _TSK_PATTERN.search(message):
        return False
    lower = message.lower()
    if _UPDATE_TASK_RE.search(message):
        return True
    if _MARK_STATUS_RE.search(message):
        return True
    if _ASSIGN_TO_RE.search(message):
        return True
    if _PRIORITY_RE.search(message):
        return True
    if _DUE_DATE_RE.search(message):
        return True
    if any(
        phrase in lower
        for phrase in (
            "mark ",
            "assign ",
            "set due date",
            "change due date",
            "change priority",
            "set priority",
        )
    ):
        return True
    return False


def parse_update_task_params(message: str) -> dict[str, Any]:
    """Extract task_id and fields to update from conversational phrasing."""
    params: dict[str, Any] = {}
    task_match = _TSK_PATTERN.search(message)
    if task_match:
        params["task_id"] = task_match.group(1).upper()

    mark = _MARK_STATUS_RE.search(message)
    if mark:
        params["task_id"] = mark.group(1).upper()
        raw_status = mark.group(2).strip().lower()
        params["status"] = _STATUS_ALIASES.get(raw_status, raw_status.replace(" ", "_"))

    assign = _ASSIGN_TO_RE.search(message)
    if assign:
        params["task_id"] = assign.group(1).upper()
        params["assignee"] = assign.group(2).strip().rstrip(".,!? ")

    priority = _PRIORITY_RE.search(message)
    if priority:
        params["task_id"] = priority.group(1).upper()
        params["priority"] = priority.group(2).strip().lower()

    due = _DUE_DATE_RE.search(message)
    if due:
        params["task_id"] = due.group(1).upper()
        params["due_date"] = due.group(2)

    if _UPDATE_TASK_RE.search(message):
        quoted = _extract_quoted(message)
        if quoted:
            params["name"] = quoted
        lower = message.lower()
        for status in ("open", "in_progress", "completed", "on_hold"):
            if status.replace("_", " ") in lower or status in lower:
                params["status"] = status
                break
        assignee_match = re.search(
            r"assign(?:ee)?\s+to\s+([A-Za-z][A-Za-z\s]+)",
            message,
            re.IGNORECASE,
        )
        if assignee_match:
            params["assignee"] = assignee_match.group(1).strip()

    return params


def is_get_task_details_message(message: str) -> bool:
    """True when the user wants full details for a specific task."""
    if not _TSK_PATTERN.search(message):
        return False
    lower = message.lower()
    return any(
        phrase in lower
        for phrase in (
            "task details",
            "details for",
            "show details",
            "get details",
            "show task",
            "get task",
            "open task",
            "details for task",
            "details of task",
            "details on task",
        )
    )


def is_list_project_members_message(message: str) -> bool:
    """True when the user wants the member list for a project."""
    lower = message.lower()
    return any(
        phrase in lower
        for phrase in (
            "list members",
            "list project members",
            "project members",
            "team members",
            "show members",
            "who is on",
            "who is in",
            "who's in",
            "members for",
            "members of",
        )
    )
