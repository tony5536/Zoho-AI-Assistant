"""Session restore on relogin (user_id only, HITL-safe)."""

import tempfile
from pathlib import Path

import pytest

from app.memory.manager import MemoryManager
from app.models.tool_models import ProjectContext


@pytest.mark.asyncio
async def test_restore_latest_session_by_user_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "restore.db"
        memory = MemoryManager(db)
        await memory.initialize()

        user_id = "mock-jamie"
        session_id = "sess-prior"
        project = ProjectContext(project_id="PRJ-001", project_name="Website Redesign")

        await memory.set_project_context(
            session_id, project.project_id, project.project_name
        )
        await memory.append(session_id, "user", "List my tasks", user_id=user_id)
        await memory.append(
            session_id, "assistant", "Here are your tasks.", user_id=user_id
        )
        await memory.save_user_memory(
            user_id,
            display_name="Jamie Lee",
            last_active_project=project,
        )

        action = await memory.create_pending_action(
            session_id,
            "delete_task",
            "Delete task TSK-101",
            {"task_id": "TSK-101"},
        )
        assert action.action_id

        restored = await memory.restore_user_session(user_id)
        assert restored is not None
        assert restored["session_id"] == session_id
        assert restored["restore_message"] == (
            "Welcome back — continuing your previous session."
        )
        assert restored["project_context"] == project
        messages = restored["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert await memory.get_latest_pending(session_id) is None


@pytest.mark.asyncio
async def test_get_recent_sessions_ordered_by_activity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "recents.db"
        memory = MemoryManager(db)
        await memory.initialize()

        user_id = "mock-jamie"
        older = "sess-older"
        newer = "sess-newer"

        await memory.append(older, "user", "Sprint planning", user_id=user_id)
        await memory.append(newer, "user", "API project tasks", user_id=user_id)
        await memory.append(
            newer, "assistant", "Here are the tasks.", user_id=user_id
        )

        recents = await memory.get_recent_sessions(user_id)
        assert len(recents) == 2
        assert recents[0]["session_id"] == newer
        assert recents[0]["title"] == "API project tasks"
        assert recents[1]["session_id"] == older
        assert recents[1]["title"] == "Sprint planning"


@pytest.mark.asyncio
async def test_restore_specific_session_clears_pending() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "specific.db"
        memory = MemoryManager(db)
        await memory.initialize()

        user_id = "mock-alex"
        session_a = "sess-a"
        session_b = "sess-b"

        await memory.append(session_a, "user", "Older chat", user_id=user_id)
        await memory.append(session_b, "user", "Bug fixes", user_id=user_id)
        await memory.create_pending_action(
            session_b, "delete_task", "Delete task", {"task_id": "TSK-1"}
        )

        restored = await memory.restore_user_session(
            user_id, session_id=session_b
        )
        assert restored is not None
        assert restored["session_id"] == session_b
        assert restored["messages"][0]["content"] == "Bug fixes"
        assert await memory.get_latest_pending(session_b) is None


@pytest.mark.asyncio
async def test_restore_unknown_session_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "unknown.db"
        memory = MemoryManager(db)
        await memory.initialize()

        user_id = "mock-alex"
        await memory.append("sess-a", "user", "Hi", user_id=user_id)
        assert (
            await memory.restore_user_session(user_id, session_id="other-user-sess")
            is None
        )


@pytest.mark.asyncio
async def test_restore_returns_none_without_prior_messages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "empty.db"
        memory = MemoryManager(db)
        await memory.initialize()

        assert await memory.restore_user_session("new-user") is None
