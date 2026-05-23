"""Session task context for conversational follow-ups (that task, it, current task)."""

import pytest

from app.models.requests import ChatRequest
from app.tools.mock_data import MockDataStore


@pytest.mark.asyncio
async def test_open_task_then_update_that_task(service) -> None:
    sid = "task-ctx-update"
    uid = "mock-jamie"

    r1 = await service.chat(
        ChatRequest(message="open task TSK-101", session_id=sid, user_id=uid)
    )
    assert r1.status == "ok"

    r2 = await service.chat(
        ChatRequest(
            message="update that task status to completed",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r2.status == "confirmation_required"
    assert r2.pending_action
    assert r2.pending_action.payload["task_id"] == "TSK-101"
    assert r2.pending_action.payload["status"] == "completed"


@pytest.mark.asyncio
async def test_open_task_then_assign_it(service) -> None:
    sid = "task-ctx-assign"
    uid = "mock-jamie"

    await service.chat(
        ChatRequest(message="open task TSK-101", session_id=sid, user_id=uid)
    )
    r = await service.chat(
        ChatRequest(message="assign it to Alex Morgan", session_id=sid, user_id=uid)
    )
    assert r.status == "confirmation_required"
    assert r.pending_action
    assert r.pending_action.payload["task_id"] == "TSK-101"
    assert "Alex Morgan" in r.pending_action.payload["assignee"]


@pytest.mark.asyncio
async def test_missing_context_graceful_failure(service) -> None:
    r = await service.chat(
        ChatRequest(
            message="update that task status to completed",
            session_id="task-ctx-missing",
            user_id="mock-jamie",
        )
    )
    assert r.status == "error"
    assert "TSK-101" in r.reply or "task id" in r.reply.lower()


@pytest.mark.asyncio
async def test_task_context_overwritten_by_newer_task(service) -> None:
    sid = "task-ctx-overwrite"
    uid = "mock-jamie"

    await service.chat(
        ChatRequest(message="open task TSK-101", session_id=sid, user_id=uid)
    )
    await service.chat(
        ChatRequest(message="open task TSK-102", session_id=sid, user_id=uid)
    )
    r = await service.chat(
        ChatRequest(message="delete this task", session_id=sid, user_id=uid)
    )
    assert r.status == "confirmation_required"
    assert r.pending_action
    assert r.pending_action.payload["task_id"] == "TSK-102"


@pytest.mark.asyncio
async def test_delete_this_task(service) -> None:
    sid = "task-ctx-delete"
    uid = "mock-jamie"

    await service.chat(
        ChatRequest(message="open task TSK-101", session_id=sid, user_id=uid)
    )
    r = await service.chat(
        ChatRequest(message="delete this task", session_id=sid, user_id=uid)
    )
    assert r.status == "confirmation_required"
    assert r.pending_action.tool == "delete_task"
    assert r.pending_action.payload["task_id"] == "TSK-101"


@pytest.mark.asyncio
async def test_current_task_phrasing(service) -> None:
    sid = "task-ctx-current"
    uid = "mock-jamie"

    await service.chat(
        ChatRequest(message="open task TSK-101", session_id=sid, user_id=uid)
    )
    r = await service.chat(
        ChatRequest(
            message="update current task status to in progress",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r.status == "confirmation_required"
    assert r.pending_action.payload["task_id"] == "TSK-101"
    assert r.pending_action.payload["status"] == "in_progress"


@pytest.mark.asyncio
async def test_list_single_task_remembers_context(service, tmp_path) -> None:
    """When list_tasks returns exactly one task, store it as session context."""
    sid = "task-ctx-single-list"
    uid = "mock-jamie"
    store = service._tools._mock
    assert isinstance(store, MockDataStore)
    store._tasks = [t for t in store._tasks if t["project_id"] != "PRJ-001"]
    store._tasks.append(
        {
            "task_id": "TSK-900",
            "project_id": "PRJ-001",
            "name": "Only task",
            "status": "open",
            "assignee": "Jamie Lee",
            "hours_logged": 1.0,
            "hours_estimated": 2.0,
            "due_date": "2026-06-01",
            "description": "",
            "priority": "low",
        }
    )

    await service.chat(
        ChatRequest(
            message="list tasks for PRJ-001",
            session_id=sid,
            user_id=uid,
        )
    )
    r = await service.chat(
        ChatRequest(message="assign it to Sam Patel", session_id=sid, user_id=uid)
    )
    assert r.status == "confirmation_required"
    assert r.pending_action.payload["task_id"] == "TSK-900"
