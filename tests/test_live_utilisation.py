"""Live-mode utilisation aggregation from task lists (no fabricated hours)."""

import pytest

from app.models.tool_models import TaskSummary, UtilisationSummary
from app.services.zoho_auth import ZohoAuthService
from app.services.token_store import TokenStore
from app.services.zoho_client import ZohoClient
from app.tools.mock_data import MockDataStore
from app.utils.utilisation_helpers import is_active_for_utilisation
from app.tools.zoho_tools import ZohoTools
from app.utils.config import Settings
from app.utils.utilisation_aggregate import build_utilisation_from_tasks


def _task(
    task_id: str,
    *,
    status: str = "open",
    hours_logged: float = 4.0,
    hours_estimated: float = 8.0,
    due_date: str | None = "2020-01-01",
) -> TaskSummary:
    return TaskSummary(
        task_id=task_id,
        project_id="PRJ-001",
        name=f"Task {task_id}",
        status=status,
        assignee="Alex Morgan",
        hours_logged=hours_logged,
        hours_estimated=hours_estimated,
        due_date=due_date,
    )


def test_active_excludes_completed_archived() -> None:
    tasks = [
        _task("TSK-1", status="open"),
        _task("TSK-2", status="completed", hours_logged=10.0, hours_estimated=10.0),
        _task("TSK-3", status="archived"),
    ]
    summary = build_utilisation_from_tasks(tasks)
    assert summary.total_tasks == 1
    assert summary.completed_task_count == 2
    assert summary.active_task_count == 1


def test_member_task_counts_and_overdue() -> None:
    tasks = [
        _task("TSK-1", status="open", due_date="2020-01-01"),
        _task("TSK-2", status="in_progress", due_date="2099-12-31"),
        TaskSummary(
            task_id="TSK-3",
            project_id="PRJ-001",
            name="Sam task",
            status="open",
            assignee="Sam Patel",
            hours_logged=2.0,
            hours_estimated=4.0,
            due_date="2020-06-01",
        ),
    ]
    summary = build_utilisation_from_tasks(tasks)
    assert summary.overdue_task_count == 2
    assert len(summary.by_assignee) == 2
    alex = next(a for a in summary.by_assignee if a.assignee == "Alex Morgan")
    sam = next(a for a in summary.by_assignee if a.assignee == "Sam Patel")
    assert alex.task_count == 2
    assert sam.task_count == 1


def test_status_grouping_optional() -> None:
    tasks = [_task("TSK-1", status="open"), _task("TSK-2", status="on_hold")]
    summary = build_utilisation_from_tasks(tasks)
    assert summary.status_groups is not None
    assert summary.status_groups.get("open") == 1
    assert summary.status_groups.get("on_hold") == 1


def test_fallback_note_preserved() -> None:
    summary = build_utilisation_from_tasks(
        [],
        fallback_note="Live API returned no tasks.",
    )
    assert summary.fallback_note == "Live API returned no tasks."
    assert summary.total_tasks == 0


@pytest.fixture
def store() -> MockDataStore:
    return MockDataStore()


@pytest.fixture
def tools(store: MockDataStore) -> ZohoTools:
    settings = Settings(zoho_use_mock=True)
    return ZohoTools(
        settings,
        TokenStore(settings),
        ZohoAuthService(settings),
        ZohoClient(settings),
        store=store,
    )


@pytest.mark.asyncio
async def test_mock_mode_unchanged(tools: ZohoTools) -> None:
    from app.tools.zoho_tools import set_current_user

    set_current_user("mock-jamie")
    result = await tools.get_task_utilisation()
    assert result.success
    assert isinstance(result.data, UtilisationSummary)
    assert result.data.fallback_note is None
    assert result.data.total_tasks > 0


def test_is_active_for_utilisation_excludes_terminal_statuses() -> None:
    for status in ("completed", "archived", "deleted", "cancelled"):
        assert not is_active_for_utilisation({"status": status})
    assert is_active_for_utilisation({"status": "open"})
