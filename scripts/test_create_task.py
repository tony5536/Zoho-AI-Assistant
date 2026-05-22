"""Natural-language task creation tests."""
import asyncio
import tempfile
from pathlib import Path

from app.models.requests import ChatRequest
from scripts._helpers import build_test_service
from app.utils.task_intent import extract_task_name, is_create_task_message


def test_parse() -> None:
    assert is_create_task_message("Create a task called API Integration")
    assert extract_task_name("Create a task called API Integration") == "API Integration"
    assert extract_task_name('create task "Sprint demo"') == "Sprint demo"
    assert extract_task_name("add a new task called Docs") == "Docs"
    print("parse: ok")


async def test_flow() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_create_task_test.db"
    service = await build_test_service(db)
    sid = "create-flow"

    await service.chat(ChatRequest(message="list projects", session_id=sid))
    await service.chat(
        ChatRequest(message="Show tasks for the first one", session_id=sid)
    )
    r = await service.chat(
        ChatRequest(
            message="Create a task called API Integration",
            session_id=sid,
        )
    )
    assert r.status == "confirmation_required", r.reply
    assert "API Integration" in r.reply
    assert "PRJ-001" in r.reply or "Website" in r.reply
    assert r.pending_action
    assert r.pending_action.payload["name"] == "API Integration"
    assert "task_id" not in r.pending_action.payload

    r2 = await service.chat(
        ChatRequest(
            message="confirm",
            session_id=sid,
            confirm=True,
            action_id=r.pending_action.action_id,
        )
    )
    assert r2.status == "ok"
    assert "API Integration" in r2.reply
    assert "TSK-" in r2.reply
    print("flow:", r2.reply)

    print("All create-task tests passed.")


if __name__ == "__main__":
    test_parse()
    asyncio.run(test_flow())
