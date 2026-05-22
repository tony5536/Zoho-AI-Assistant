"""Update task intent and HITL flow tests (run: py -3 scripts/test_update_task.py)."""
import asyncio
import tempfile
from pathlib import Path

from app.models.requests import ChatRequest
from scripts._helpers import build_test_service
from app.utils.intent import parse_intent
from app.utils.task_intent import is_update_task_message, parse_update_task_params


def test_parse() -> None:
    cases = [
        ("mark TSK-101 as completed", {"task_id": "TSK-101", "status": "completed"}),
        ("assign TSK-101 to Jamie Lee", {"task_id": "TSK-101", "assignee": "Jamie Lee"}),
        (
            "change priority of TSK-101 to high",
            {"task_id": "TSK-101", "priority": "high"},
        ),
        (
            "set due date of TSK-101 to 2026-05-30",
            {"task_id": "TSK-101", "due_date": "2026-05-30"},
        ),
    ]
    for msg, expected in cases:
        assert is_update_task_message(msg), msg
        params = parse_update_task_params(msg)
        for key, value in expected.items():
            assert params.get(key) == value, (msg, key, params)
        assert parse_intent(msg).operation == "update_task", msg
    print("parse: ok")


async def test_flow() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_update_test.db"
    service = await build_test_service(db)
    sid = "update-flow"
    uid = "mock-jamie"

    r = await service.chat(
        ChatRequest(
            message="mark TSK-101 as completed",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r.status == "confirmation_required", r.reply
    assert r.pending_action
    assert r.pending_action.payload["task_id"] == "TSK-101"
    assert r.pending_action.payload["status"] == "completed"
    assert "TSK-101" in r.reply
    print("confirm prompt:", r.reply.split("\n")[0])

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
    assert "Updated" in r2.reply or "updated" in r2.reply.lower()
    print("success:", r2.reply)

    print("All update-task tests passed.")


if __name__ == "__main__":
    test_parse()
    asyncio.run(test_flow())
