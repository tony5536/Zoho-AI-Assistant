"""OAuth login starts a fresh session; prior sessions remain restorable."""

import tempfile
from pathlib import Path

import pytest

from app.memory.manager import MemoryManager
from app.services.oauth_users import OAUTH_DISPLAY_NAME, OAUTH_USER_ID, resolve_oauth_user_id
from app.tools.mock_data import MockDataStore
from app.tools.zoho_tools import create_zoho_tools, set_current_user
from app.utils.config import get_settings


@pytest.mark.asyncio
async def test_oauth_login_creates_new_active_session_without_deleting_old() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "oauth_sess.db"
        memory = MemoryManager(db)
        await memory.initialize()

        old_session = "sess-tony-old"
        await memory.append(
            old_session, "user", "Jamie crossover chat", user_id=OAUTH_USER_ID
        )

        new_session = await memory.begin_login_session(OAUTH_USER_ID)
        assert new_session != old_session
        assert await memory.get_active_session_id(OAUTH_USER_ID) == new_session

        restored_old = await memory.restore_user_session(
            OAUTH_USER_ID, session_id=old_session
        )
        assert restored_old is not None
        assert restored_old["session_id"] == old_session

        restored_active = await memory.restore_user_session(OAUTH_USER_ID)
        assert restored_active is None


@pytest.mark.asyncio
async def test_resolve_oauth_user_id_is_canonical() -> None:
    assert resolve_oauth_user_id("jamie.lee") == OAUTH_USER_ID
    assert resolve_oauth_user_id("random-uuid") == OAUTH_USER_ID


@pytest.mark.asyncio
async def test_tony_reno_mock_projects_isolated_from_jamie() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "oauth_proj.db"
        settings = get_settings().model_copy(
            update={"memory_db_path": db, "zoho_use_mock": True}
        )
        store = MockDataStore()
        from app.services.token_store import TokenStore
        from app.services.zoho_auth import ZohoAuthService

        token_store = TokenStore(settings)
        await token_store.initialize()
        auth = ZohoAuthService(settings)
        tools = create_zoho_tools(settings, token_store, auth, store)

        await token_store.save_tokens(
            OAUTH_USER_ID,
            access_token="mock-access",
            refresh_token="mock-refresh",
            expires_in=3600,
        )
        await MemoryManager(db).initialize()
        memory = MemoryManager(db)
        await memory.restore_user_memory_on_login(
            OAUTH_USER_ID, display_name=OAUTH_DISPLAY_NAME
        )

        set_current_user(OAUTH_USER_ID)
        tony_projects = await tools.list_projects()
        assert tony_projects.data is not None
        tony_names = {p.name for p in tony_projects.data.projects}
        assert "Customer Portal Revamp" in tony_names
        assert "Website Redesign" not in tony_names

        set_current_user("mock-jamie")
        jamie_projects = await tools.list_projects()
        assert jamie_projects.data is not None
        jamie_names = {p.name for p in jamie_projects.data.projects}
        assert "Website Redesign" in jamie_names
        assert "Customer Portal Revamp" not in jamie_names


@pytest.mark.asyncio
async def test_tony_reno_oauth_demo_seed_covers_members_tasks_and_utilisation() -> None:
    """OAuth demo user should match mock-user richness for members, tasks, and workload."""
    settings = get_settings().model_copy(update={"zoho_use_mock": True})
    store = MockDataStore()
    from app.services.token_store import TokenStore
    from app.services.zoho_auth import ZohoAuthService

    tools = create_zoho_tools(
        settings, TokenStore(settings), ZohoAuthService(settings), store
    )
    set_current_user(OAUTH_USER_ID)

    members = await tools.list_project_members("PRJ-101")
    assert members.success and members.data is not None
    assert members.data.count == 3
    member_names = {m.name for m in members.data.members}
    assert member_names == {"Tony Reno", "Alex Morgan", "Priya Shah"}

    tasks = await tools.list_tasks("PRJ-101")
    assert tasks.success and tasks.data is not None
    assert tasks.data.count >= 4
    assert len({t.assignee for t in tasks.data.tasks}) >= 2

    util = await tools.get_task_utilisation(view="most_tasks", project_id="PRJ-101")
    assert util.success and util.data is not None
    assert util.data.total_tasks >= 4
    assert util.data.by_assignee
    assert util.data.top_by_tasks

    field_tasks = await tools.list_tasks("PRJ-102")
    assert field_tasks.success and field_tasks.data is not None
    assert field_tasks.data.count >= 3


@pytest.mark.asyncio
async def test_tony_reno_most_tasks_uses_scoped_mock_pipeline_with_real_tokens() -> None:
    """OAuth demo user must not get empty live utilisation when Zoho tokens exist."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "oauth_util.db"
        settings = get_settings().model_copy(
            update={"memory_db_path": db, "zoho_use_mock": False}
        )
        store = MockDataStore()
        from app.services.token_store import TokenStore
        from app.services.zoho_auth import ZohoAuthService

        token_store = TokenStore(settings)
        await token_store.initialize()
        auth = ZohoAuthService(settings)
        tools = create_zoho_tools(settings, token_store, auth, store)

        await token_store.save_tokens(
            OAUTH_USER_ID,
            access_token="zoho-real-looking-access-token",
            refresh_token="zoho-real-looking-refresh",
            expires_in=3600,
        )

        set_current_user(OAUTH_USER_ID)
        util = await tools.get_task_utilisation(view="most_tasks")
        assert util.success and util.data is not None
        counts = {row.assignee: row.task_count for row in util.data.by_assignee}
        assert counts == {
            "Alex Morgan": 6,
            "Sam Patel": 3,
            "Jamie Lee": 2,
            "Tony Reno": 3,
            "Priya Shah": 3,
        }
        assert util.data.top_by_tasks == "Alex Morgan"
