"""Shared utilisation status helpers (no mock_data / aggregate imports)."""

_UTILISATION_EXCLUDED_STATUSES = frozenset({
    "completed",
    "done",
    "closed",
    "archived",
    "cancelled",
    "deleted",
})


def _normalize_task_status(status: str | None) -> str:
    if not status:
        return ""
    return status.lower().strip().replace(" ", "_").replace("-", "_")


def is_active_for_utilisation(task: dict) -> bool:
    """Tasks excluded from utilisation analytics (deleted tasks are removed from the store)."""
    return _normalize_task_status(task.get("status")) not in _UTILISATION_EXCLUDED_STATUSES
