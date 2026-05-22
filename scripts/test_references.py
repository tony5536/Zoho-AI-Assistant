"""Reference resolution tests (run: py -3 scripts/test_references.py)."""
import asyncio
import tempfile
from pathlib import Path

from app.memory.manager import MemoryManager
from app.models.requests import ChatRequest
from app.models.tool_models import RecentProject
from scripts._helpers import build_test_service
from app.utils.references import extract_project_ref, resolve_project_id


def test_resolve_unit() -> None:
    recent = [
        RecentProject(project_id="PRJ-001", name="A", position=1),
        RecentProject(project_id="PRJ-002", name="B", position=2),
    ]
    assert extract_project_ref("show tasks for the first one") == "first"
    assert resolve_project_id(
        "show tasks for the first one",
        project_ref="first",
        recent_projects=recent,
    ) == "PRJ-001"
    assert resolve_project_id(
        "tasks for the second one",
        project_ref="second",
        recent_projects=recent,
    ) == "PRJ-002"
    assert extract_project_ref("show tasks from project two") == "second"
    assert resolve_project_id(
        "show tasks from project two",
        recent_projects=recent,
    ) == "PRJ-002"
    assert extract_project_ref("tasks for project 1") == "first"
    assert resolve_project_id(
        "list tasks for project three",
        recent_projects=[
            RecentProject(project_id="PRJ-001", name="A", position=1),
            RecentProject(project_id="PRJ-002", name="B", position=2),
            RecentProject(project_id="PRJ-003", name="C", position=3),
        ],
    ) == "PRJ-003"
    assert extract_project_ref("tasks for the last one") == "last"
    assert (
        resolve_project_id(
            "tasks for the last one",
            project_ref="last",
            recent_projects=recent,
        )
        == "PRJ-002"
    )
    print("unit: ok")


async def test_integration() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_ref_test.db"
    service = await build_test_service(db)
    sid = "ref-session"

    await service.chat(ChatRequest(message="list projects", session_id=sid))
    r = await service.chat(
        ChatRequest(message="Show tasks for the first one", session_id=sid)
    )
    assert r.status == "ok", r.reply
    assert r.data and r.data.get("data", {}).get("project_id") == "PRJ-001"
    print("integration first one:", r.data["data"]["project_id"])

    await service.chat(ChatRequest(message="use the second one", session_id=sid))
    r2 = await service.chat(ChatRequest(message="list tasks", session_id=sid))
    assert r2.status == "ok"
    assert r2.data and r2.data["data"]["project_id"] == "PRJ-002"
    print("integration second + list tasks:", r2.data["data"]["project_id"])

    r3 = await service.chat(
        ChatRequest(message="show tasks from project two", session_id=sid)
    )
    assert r3.status == "ok", r3.reply
    assert r3.data and r3.data["data"]["project_id"] == "PRJ-002"
    print("integration project two:", r3.data["data"]["project_id"])

    sid2 = "ref-session-overdue"
    await service.chat(
        ChatRequest(message="What projects do I have?", session_id=sid2)
    )
    r4 = await service.chat(
        ChatRequest(message="Show tasks for the first one", session_id=sid2)
    )
    assert r4.status == "ok", r4.reply
    r5 = await service.chat(
        ChatRequest(message="Show only overdue ones", session_id=sid2)
    )
    assert r5.status == "ok", r5.reply
    assert r5.project_context and r5.project_context.project_id == "PRJ-001"
    print("integration overdue filter:", r5.reply.split("\n")[0])

    print("All reference tests passed.")


if __name__ == "__main__":
    test_resolve_unit()
    asyncio.run(test_integration())
