"""HITL cancel must not mutate tasks and must clear pending actions."""

import pytest

from app.models.requests import ChatRequest
from app.tools.mock_data import MockDataStore


@pytest.mark.asyncio
async def test_cancel_does_not_modify_task(service) -> None:
    sid = "hitl-cancel-noop"
    uid = "mock-jamie"
    store: MockDataStore = service._tools._mock
    before = store.get_task("TSK-101", user_id=uid)
    assert before is not None
    before_status = before.status

    staged = await service.chat(
        ChatRequest(
            message="Update TSK-101 status to completed",
            session_id=sid,
            user_id=uid,
        )
    )
    assert staged.status == "confirmation_required"
    action_id = staged.pending_action.action_id

    cancelled = await service.chat(
        ChatRequest(
            message="cancel",
            session_id=sid,
            user_id=uid,
            cancel=True,
            action_id=action_id,
        )
    )
    assert cancelled.status == "ok"
    assert cancelled.pending_action is None
    assert "discarded" in cancelled.reply.lower()

    after = store.get_task("TSK-101", user_id=uid)
    assert after is not None
    assert after.status == before_status


@pytest.mark.asyncio
async def test_repeated_cancel_safe(service) -> None:
    sid = "hitl-cancel-repeat"
    uid = "mock-jamie"

    staged = await service.chat(
        ChatRequest(
            message="delete task TSK-102",
            session_id=sid,
            user_id=uid,
        )
    )
    action_id = staged.pending_action.action_id

    first = await service.chat(
        ChatRequest(
            message="cancel",
            session_id=sid,
            user_id=uid,
            cancel=True,
            action_id=action_id,
        )
    )
    assert first.status == "ok"

    second = await service.chat(
        ChatRequest(
            message="cancel",
            session_id=sid,
            user_id=uid,
            cancel=True,
            action_id=action_id,
        )
    )
    assert second.status == "ok"
    assert second.pending_action is None


@pytest.mark.asyncio
async def test_confirm_after_cancel_fails_cleanly(service) -> None:
    sid = "hitl-cancel-then-confirm"
    uid = "mock-jamie"

    staged = await service.chat(
        ChatRequest(
            message="Update TSK-101 status to on_hold",
            session_id=sid,
            user_id=uid,
        )
    )
    action_id = staged.pending_action.action_id

    await service.chat(
        ChatRequest(
            message="cancel",
            session_id=sid,
            user_id=uid,
            cancel=True,
            action_id=action_id,
        )
    )

    confirm = await service.chat(
        ChatRequest(
            message="confirm",
            session_id=sid,
            user_id=uid,
            confirm=True,
            action_id=action_id,
        )
    )
    assert confirm.status == "error"
    assert (
        "expired" in confirm.reply.lower()
        or "could not find" in confirm.reply.lower()
        or "already" in confirm.reply.lower()
    )
