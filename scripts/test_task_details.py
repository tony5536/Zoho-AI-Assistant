"""Task details and project members query tests (run: py -3 scripts/test_task_details.py)."""
import asyncio
import tempfile
from pathlib import Path

from app.models.requests import ChatRequest
from scripts._helpers import build_test_service
from app.utils.intent import parse_intent
from app.utils.task_intent import is_get_task_details_message, is_list_project_members_message


def test_parse() -> None:
    detail_msgs = [
        "show details for TSK-101",
        "task details for TSK-101",
        "open task TSK-101",
    ]
    for msg in detail_msgs:
        assert is_get_task_details_message(msg), msg
        intent = parse_intent(msg)
        assert intent.operation == "get_task_details", msg
        assert intent.params["task_id"] == "TSK-101", msg

    member_msgs = [
        "show members for PRJ-001",
        "who is in this project?",
        "list project members",
    ]
    for msg in member_msgs:
        assert is_list_project_members_message(msg), msg
        assert parse_intent(msg).operation == "list_project_members", msg
    print("parse: ok")


async def test_flow() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_task_details_test.db"
    service = await build_test_service(db)
    sid = "details-flow"
    uid = "mock-jamie"

    r = await service.chat(
        ChatRequest(
            message="open task TSK-101",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r.status == "ok", r.reply
    assert "TSK-101" in r.reply
    assert "API Integration" in r.reply
    assert "Status:" in r.reply
    assert "Assignee:" in r.reply
    print("details:", r.reply.split("\n")[0])

    await service.chat(
        ChatRequest(message="list projects", session_id=sid, user_id=uid)
    )
    await service.chat(
        ChatRequest(
            message="Show tasks for the first one",
            session_id=sid,
            user_id=uid,
        )
    )
    r2 = await service.chat(
        ChatRequest(
            message="who is in this project?",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r2.status == "ok", r2.reply
    assert "Alex Morgan" in r2.reply or "Jamie Lee" in r2.reply
    print("members:", r2.reply.split("\n")[0])

    print("All task-details tests passed.")


if __name__ == "__main__":
    test_parse()
    asyncio.run(test_flow())
