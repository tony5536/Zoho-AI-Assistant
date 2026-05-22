"""update_task intent, HITL confirmation, and field updates."""

import pytest

from app.agents.supervisor import SupervisorAgent
from app.models.requests import ChatRequest
from app.utils.intent import parse_intent
from app.utils.task_intent import is_update_task_message, parse_update_task_params


def test_update_intent_parsing() -> None:
    cases = [
        (
            "Update TSK-101 status to completed",
            {"task_id": "TSK-101", "status": "completed"},
        ),
        ("assign TSK-101 to Alex Morgan", {"task_id": "TSK-101", "assignee": "Alex Morgan"}),
        (
            "Change due date of TSK-101 to 2026-06-01",
            {"task_id": "TSK-101", "due_date": "2026-06-01"},
        ),
        (
            "Set priority of TSK-101 to high",
            {"task_id": "TSK-101", "priority": "high"},
        ),
        (
            "update TSK-101 as In progress",
            {"task_id": "TSK-101", "status": "in_progress"},
        ),
    ]
    for msg, expected in cases:
        assert is_update_task_message(msg), msg
        params = parse_update_task_params(msg)
        intent = parse_intent(msg)
        assert intent.operation == "update_task"
        for key, value in expected.items():
            assert params.get(key) == value or intent.params.get(key) == value, (msg, key)
        route = SupervisorAgent()._classify(msg.lower(), {})
        assert route == "action"


@pytest.mark.asyncio
async def test_update_hitl_and_confirm(service) -> None:
    sid = "test-update"
    uid = "mock-jamie"

    r = await service.chat(
        ChatRequest(
            message="Update TSK-101 status to completed",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r.status == "confirmation_required"
    assert r.pending_action
    assert r.pending_action.tool == "update_task"
    assert r.pending_action.payload["task_id"] == "TSK-101"
    assert r.pending_action.payload["status"] == "completed"
    assert "completed" in r.reply.lower() or "status" in r.reply.lower()

    r2 = await service.chat(
        ChatRequest(
            message="confirm",
            session_id=sid,
            user_id=uid,
            confirm=True,
            action_id=r.pending_action.action_id,
        )
    )
    assert r2.status == "ok"
    assert "Updated" in r2.reply
    assert r2.data and r2.data["tool"] == "update_task"
