"""Quick local smoke test (run: py -3 scripts/smoke_test.py)."""
import asyncio
import tempfile
from pathlib import Path

from app.models.requests import ChatRequest
from scripts._helpers import build_test_service


async def main() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_assistant_smoke.db"
    service = await build_test_service(db)
    sid = "smoke-session"

    r1 = await service.chat(
        ChatRequest(message="What projects do I have?", session_id=sid)
    )
    assert r1.status == "ok" and r1.agent == "query" and r1.routed_to == "query"
    assert r1.data and r1.data["data"]["count"] == 3
    print("list_projects:", r1.reply.split("\n")[0])

    r2 = await service.chat(
        ChatRequest(message="Show tasks for the first one", session_id=sid)
    )
    assert r2.status == "ok" and r2.data["data"]["project_id"] == "PRJ-001"
    assert r2.project_context and r2.project_context.project_id == "PRJ-001"
    print("list_tasks (first one):", r2.project_context.project_name, r2.data["data"]["count"])

    r3 = await service.chat(
        ChatRequest(message="Who has the most tasks this month?", session_id=sid)
    )
    assert r3.status == "ok" and r3.agent == "query"
    assert r3.data and r3.data["tool"] == "get_task_utilisation"
    print("utilisation:", r3.reply.split("\n")[0])

    r4 = await service.chat(
        ChatRequest(
            message="Create a task called API Integration",
            session_id=sid,
        )
    )
    assert r4.agent == "action" and r4.routed_to == "action"
    assert "API Integration" in r4.reply
    assert r4.status == "confirmation_required" and r4.pending_action
    assert r4.pending_action.payload["project_id"] == "PRJ-001"
    print("pending:", r4.pending_action.tool, r4.pending_action.action_id)

    r5 = await service.chat(
        ChatRequest(
            message="confirm",
            session_id=sid,
            confirm=True,
            action_id=r4.pending_action.action_id,
        )
    )
    assert r5.status == "ok"
    print("confirmed:", r5.reply)

    r6 = await service.chat(
        ChatRequest(message="Delete task TSK-101", session_id=sid)
    )
    assert r6.agent == "action" and r6.status == "confirmation_required"
    assert r6.pending_action and r6.pending_action.payload["task_id"] == "TSK-101"
    print("delete prompt:", r6.reply.split("\n")[0])

    r7 = await service.chat(
        ChatRequest(
            message="confirm",
            session_id=sid,
            confirm=True,
            action_id=r6.pending_action.action_id,
        )
    )
    assert r7.status == "ok" and "removed" in r7.reply.lower()
    print("deleted:", r7.reply)

    print("All smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
