import re
from typing import Literal

from app.models.tool_models import ProjectContext, RecentProject

ProjectRef = Literal["first", "second", "third", "last", "current", "that"]

_ORDINAL_INDEX: dict[ProjectRef, int] = {
    "first": 0,
    "second": 1,
    "third": 2,
}

_ORDINAL_TOKEN_MAP: dict[str, ProjectRef] = {
    "one": "first",
    "1": "first",
    "first": "first",
    "1st": "first",
    "two": "second",
    "2": "second",
    "second": "second",
    "2nd": "second",
    "three": "third",
    "3": "third",
    "third": "third",
    "3rd": "third",
}

# "project two", "project 2" — checked before generic ordinal patterns
_PROJECT_REF_PATTERN = re.compile(
    r"\bproject\s+(one|two|three|1|2|3|first|second|third|1st|2nd|3rd)\b",
    re.IGNORECASE,
)

_REF_PATTERNS: list[tuple[re.Pattern[str], ProjectRef]] = [
    (re.compile(r"\b(first|1st)\b(?:\s+(one|project))?", re.I), "first"),
    (re.compile(r"\b(second|2nd)\b(?:\s+(one|project))?", re.I), "second"),
    (re.compile(r"\b(third|3rd)\b(?:\s+(one|project))?", re.I), "third"),
    (re.compile(r"\b(last)\b(?:\s+(one|project))?", re.I), "last"),
    (re.compile(r"\b(current|this)\s+project\b", re.I), "current"),
    (re.compile(r"\b(that|the)\s+project\b", re.I), "that"),
    (re.compile(r"\b(that|the)\s+one\b", re.I), "that"),
]


def _normalize_ordinal_token(token: str) -> ProjectRef | None:
    return _ORDINAL_TOKEN_MAP.get(token.lower())


def extract_project_ref(message: str) -> ProjectRef | None:
    """Detect ordinal or contextual project reference in user text."""
    project_match = _PROJECT_REF_PATTERN.search(message)
    if project_match:
        return _normalize_ordinal_token(project_match.group(1))

    for pattern, ref in _REF_PATTERNS:
        if pattern.search(message):
            return ref
    return None


def resolve_project_id(
    message: str,
    *,
    explicit_id: str | None = None,
    project_ref: ProjectRef | str | None = None,
    recent_projects: list[RecentProject] | None = None,
    project_context: ProjectContext | None = None,
) -> str | None:
    """
    Resolve a project_id from explicit id, stored list, or contextual phrases.
    Priority: explicit PRJ id > ordinal ref > contextual ref > current context fallback.
    """
    if explicit_id:
        return explicit_id.upper()

    recent = recent_projects or []
    ref: ProjectRef | str | None = project_ref or extract_project_ref(message)

    if ref in _ORDINAL_INDEX:
        index = _ORDINAL_INDEX[ref]
        if index < len(recent):
            return recent[index].project_id
        return None

    if ref == "last":
        if recent:
            return recent[-1].project_id
        return None

    if ref == "current":
        if project_context:
            return project_context.project_id
        return None

    if ref == "that":
        if project_context:
            return project_context.project_id
        if recent:
            return recent[-1].project_id
        return None

    if project_context and _implies_current_project(message):
        return project_context.project_id

    return None


def _implies_current_project(message: str) -> bool:
    lower = message.lower()
    if extract_project_ref(message) is not None:
        return False
    if any(
        phrase in lower
        for phrase in (
            "list tasks",
            "show tasks",
            "tasks for",
            "tasks in",
            "tasks from",
        )
    ):
        return True
    return is_contextual_task_filter(lower)


def is_contextual_task_filter(lower: str) -> bool:
    """Follow-up filters (e.g. overdue only) that keep the active project."""
    if "project" in lower and any(
        cue in lower for cue in ("list projects", "show projects", "my projects", "which projects")
    ):
        return False
    has_filter = any(
        token in lower
        for token in ("overdue", "open", "in progress", "completed", "on hold", "only")
    )
    has_task_cue = any(
        token in lower for token in ("task", "ones", "those", "them")
    )
    return has_filter and (has_task_cue or "only" in lower)
