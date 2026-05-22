"""Verify per-user long-term memory persistence."""

import asyncio
import tempfile
from pathlib import Path

from app.memory.manager import MemoryManager
from app.models.tool_models import ProjectContext
from app.services.assistant_service import AssistantService
from scripts._helpers import build_test_service


async def test_memory_manager_helpers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "mem.db"
        memory = MemoryManager(db)
        await memory.initialize()

        user_id = "mock-jamie"
        project = ProjectContext(project_id="PRJ-001", project_name="Website Redesign")

        await memory.save_user_memory(
            user_id,
            display_name="Jamie Lee",
            last_active_project=project,
        )
        await memory._record_project_access(user_id, project)
        await memory._record_project_access(user_id, project)

        snapshot = await memory.load_user_memory(user_id)
        assert snapshot.display_name == "Jamie Lee"
        assert snapshot.last_active_project == project
        assert snapshot.frequent_project == project
        assert "Welcome back Jamie Lee" in (snapshot.welcome_message or "")
        assert "Website Redesign" in (snapshot.welcome_message or "")

        session_id = "sess-restore"
        restored = await memory.apply_user_memory_to_session(user_id, session_id)
        assert restored == project
        ctx = await memory.get_project_context(session_id)
        assert ctx == project

        login_snapshot = await memory.restore_user_memory_on_login(
            user_id, display_name="Jamie Lee"
        )
        assert login_snapshot.welcome_message is not None

        await memory.sync_user_memory_on_chat(
            user_id,
            session_id,
            user_message="List my tasks",
            assistant_reply="Here are your tasks.",
            project_context=project,
        )
        updated = await memory.load_user_memory(user_id)
        assert "List my tasks" in updated.recent_queries

        print("MemoryManager user_memory helpers: OK")


async def test_chat_persists_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "chat_mem.db"
        service = await build_test_service(db)
        memory = service._memory
        user_id = "user-a"
        session_id = "sess-a"

        await memory.save_user_memory(
            user_id,
            display_name="Alex",
            last_active_project=ProjectContext(
                project_id="PRJ-002", project_name="Mobile App"
            ),
        )

        from app.models.requests import ChatRequest

        await service.chat(
            ChatRequest(
                message="What projects do I have?",
                session_id=session_id,
                user_id=user_id,
            )
        )

        snapshot = await memory.load_user_memory(user_id)
        assert snapshot.last_active_project is not None
        assert any("projects" in q.lower() for q in snapshot.recent_queries)
        print("AssistantService chat memory sync: OK")


async def main() -> None:
    await test_memory_manager_helpers()
    await test_chat_persists_memory()
    print("All user memory tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
