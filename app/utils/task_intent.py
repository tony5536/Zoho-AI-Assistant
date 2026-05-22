"""Natural-language parsing helpers for task actions (rule-based, no LLM)."""

import re

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
