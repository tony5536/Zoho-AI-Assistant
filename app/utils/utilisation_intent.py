"""Rule-based detection for utilisation and workload analytics queries."""

import re

# Specific views checked before generic utilisation keywords
_VIEW_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"who\s+has\s+(?:the\s+)?most\s+tasks|most\s+tasks\s+this\s+month|"
            r"most\s+tasks\s+assigned|employee\s+with\s+(?:the\s+)?most\s+tasks",
            re.I,
        ),
        "most_tasks",
    ),
    (
        re.compile(
            r"highest\s+workload|most\s+workload|heaviest\s+workload|"
            r"busiest\s+employee|who\s+is\s+(?:the\s+)?busiest|"
            r"which\s+employee\s+has\s+(?:the\s+)?highest",
            re.I,
        ),
        "highest_workload",
    ),
    (
        re.compile(
            r"task\s+distribution|distribution\s+summary|workload\s+distribution|"
            r"breakdown\s+by\s+employee|tasks\s+per\s+employee",
            re.I,
        ),
        "distribution",
    ),
]

_UTILISATION_KEYWORDS = (
    "utilisation",
    "utilization",
    "workload",
    "capacity",
    "hours logged",
    "logged hours",
    "burn",
    "overallocated",
)


def is_utilisation_query(message: str) -> bool:
    lower = message.lower()
    if any(k in lower for k in _UTILISATION_KEYWORDS):
        return True
    return any(pattern.search(message) for pattern, _ in _VIEW_RULES)


def detect_utilisation_view(message: str) -> str:
    for pattern, view in _VIEW_RULES:
        if pattern.search(message):
            return view
    return "summary"
