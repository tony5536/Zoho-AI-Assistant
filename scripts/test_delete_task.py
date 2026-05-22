"""Delete task intent tests (run: py -3 scripts/test_delete_task.py)."""
import asyncio
import tempfile
from pathlib import Path

from app.models.requests import ChatRequest
from scripts._helpers import build_test_service
from app.utils.intent import parse_intent
from app.utils.task_intent import extract_delete_task_id, is_delete_task_message


def test_parse() -> None:
    cases = [
        "delete task TSK-102",
        "Delete TSK-102",
        "Delete a task TSK-102",
        "remove task TSK-102",
        "remove TSK-102",
    ]
    for msg in cases:
        assert is_delete_task_message(msg), msg
        assert extract_delete_task_id(msg) == "TSK-102", msg
        assert parse_intent(msg).operation == "delete_task"
    print("parse: ok")


async def test_flow() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_delete_test.db"
    service = await build_test_service(db)
    sid = "delete-flow"

    r = await service.chat(
        ChatRequest(message="remove TSK-102", session_id=sid)
    )
    assert r.status == "confirmation_required", r.reply
    assert "Design homepage mockups" in r.reply or "TSK-102" in r.reply
    assert r.pending_action and r.pending_action.payload["task_id"] == "TSK-102"
    print("confirm prompt:", r.reply.split("\n")[0])

    r2 = await service.chat(
        ChatRequest(
            message="confirm",
            session_id=sid,
            confirm=True,
            action_id=r.pending_action.action_id,
        )
    )
    assert r2.status == "ok"
    assert "removed" in r2.reply.lower()
    print("success:", r2.reply)

    print("All delete-task tests passed.")


if __name__ == "__main__":
    test_parse()
    asyncio.run(test_flow())
