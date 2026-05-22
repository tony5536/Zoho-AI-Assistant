"""Conversational project/task context (ordinal follow-ups, history load)."""

import pytest

from app.memory.manager import MemoryManager
from app.models.requests import ChatRequest
from app.utils.config import get_settings
from app.utils.intent import parse_intent
from app.utils.references import is_contextual_task_filter, resolve_project_id
from app.models.tool_models import RecentProject


@pytest.mark.asyncio
async def test_history_load_includes_message_id(tmp_path) -> None:
    settings = get_settings().model_copy(update={"memory_db_path": tmp_path / "m.db"})
    memory = MemoryManager(settings.memory_db_path)
    await memory.initialize()
    sid = "hist-test"
    await memory.append(sid, "user", "What projects do I have?", user_id="u1")
    await memory.append(sid, "assistant", "You have 2 projects.", user_id="u1")
    history = await memory.get_history(sid)
    assert len(history) == 2
    assert history[0]["id"] is not None
    assert history[0]["role"] == "user"


def test_contextual_overdue_intent() -> None:
    assert is_contextual_task_filter("show only overdue ones")
    intent = parse_intent("Show only overdue ones")
    assert intent.operation == "list_tasks"
    assert intent.params.get("due_date") == "overdue"


def test_last_ordinal_resolution() -> None:
    recent = [
        RecentProject(project_id="PRJ-001", name="A", position=1),
        RecentProject(project_id="PRJ-002", name="B", position=2),
    ]
    assert resolve_project_id("tasks for the last one", project_ref="last", recent_projects=recent) == "PRJ-002"


@pytest.mark.asyncio
async def test_project_task_followup_flow(service) -> None:
    sid = "followup-flow"
    uid = "mock-jamie"
    r1 = await service.chat(
        ChatRequest(message="What projects do I have?", session_id=sid, user_id=uid)
    )
    assert r1.status == "ok"

    r2 = await service.chat(
        ChatRequest(
            message="Show tasks for the first one",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r2.status == "ok", r2.reply
    assert r2.project_context is not None
    assert r2.data and r2.data["data"]["project_id"] == "PRJ-001"

    r3 = await service.chat(
        ChatRequest(message="Show only overdue ones", session_id=sid, user_id=uid)
    )
    assert r3.status == "ok", r3.reply
    assert r3.project_context and r3.project_context.project_id == "PRJ-001"
