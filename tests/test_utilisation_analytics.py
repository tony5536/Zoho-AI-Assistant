"""Utilisation analytics must reflect only active tasks and reset deterministically."""

import pytest

from app.models.tool_models import UtilisationSummary
from app.services.zoho_auth import ZohoAuthService
from app.services.token_store import TokenStore
from app.services.zoho_client import ZohoClient
from app.tools.mock_data import MockDataStore
from app.tools.zoho_tools import ZohoTools, set_current_user
from app.utils.config import Settings

_BASELINE_COUNTS = {
    "Alex Morgan": 3,
    "Sam Patel": 3,
    "Jamie Lee": 2,
}


def _assignee_counts(store: MockDataStore) -> dict[str, int]:
    summary = store.build_utilisation_summary(view="most_tasks")
    return {row.assignee: row.task_count for row in summary.by_assignee}


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


def test_baseline_utilisation_counts(store: MockDataStore) -> None:
    assert _assignee_counts(store) == _BASELINE_COUNTS
    assert store.build_utilisation_summary().total_tasks == 8


def test_create_task_increases_utilisation(store: MockDataStore) -> None:
    created = store.create_task(
        "PRJ-001",
        "Demo follow-up",
        user_id="mock-jamie",
        assignee="Jamie Lee",
    )
    assert created is not None
    counts = _assignee_counts(store)
    assert counts["Jamie Lee"] == _BASELINE_COUNTS["Jamie Lee"] + 1
    assert store.build_utilisation_summary().total_tasks == 9


def test_delete_task_decreases_utilisation(store: MockDataStore) -> None:
    assert store.delete_task("TSK-102", user_id="mock-jamie")
    assert store.get_task_org("TSK-102") is None
    counts = _assignee_counts(store)
    assert counts["Alex Morgan"] == _BASELINE_COUNTS["Alex Morgan"] - 1
    assert store.build_utilisation_summary().total_tasks == 7


def test_archived_status_excluded_from_utilisation(store: MockDataStore) -> None:
    store.update_task("TSK-101", user_id="mock-jamie", status="archived")
    assert store.get_task("TSK-101", user_id="mock-jamie") is not None
    assert store.get_task_org("TSK-101") is None
    counts = _assignee_counts(store)
    assert counts["Jamie Lee"] == _BASELINE_COUNTS["Jamie Lee"] - 1


def test_reset_restores_stable_utilisation(store: MockDataStore) -> None:
    store.create_task(
        "PRJ-002",
        "Temporary",
        user_id="mock-alex",
        assignee="Alex Morgan",
    )
    store.delete_task("TSK-301", user_id="mock-jamie")
    store.reset()
    assert _assignee_counts(store) == _BASELINE_COUNTS


@pytest.mark.asyncio
async def test_get_task_utilisation_tracks_create_and_delete(tools: ZohoTools) -> None:
    set_current_user("mock-jamie")

    before = await tools.get_task_utilisation()
    assert before.success
    assert isinstance(before.data, UtilisationSummary)
    before_total = before.data.total_tasks

    created = await tools.create_task("PRJ-001", "Utilisation probe", assignee="Jamie Lee")
    assert created.success

    after_create = await tools.get_task_utilisation()
    assert after_create.success
    assert isinstance(after_create.data, UtilisationSummary)
    assert after_create.data.total_tasks == before_total + 1

    task_id = created.data.task.task_id
    deleted = await tools.delete_task(task_id)
    assert deleted.success

    after_delete = await tools.get_task_utilisation()
    assert after_delete.success
    assert isinstance(after_delete.data, UtilisationSummary)
    assert after_delete.data.total_tasks == before_total


@pytest.mark.asyncio
async def test_repeated_utilisation_queries_stable_after_reset(tools: ZohoTools) -> None:
    set_current_user("mock-jamie")
    store = tools._mock

    store.create_task("PRJ-004", "Extra QA item", user_id="mock-sam", assignee="Sam Patel")
    store.reset()

    for _ in range(3):
        result = await tools.get_task_utilisation()
        assert result.success
        summary = result.data
        assert isinstance(summary, UtilisationSummary)
        assert {row.assignee: row.task_count for row in summary.by_assignee} == _BASELINE_COUNTS
