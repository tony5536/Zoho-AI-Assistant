"""Silent OAuth token refresh before live API calls."""

import time
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.tools.zoho_tools import create_zoho_tools, set_current_user
from app.utils.config import get_settings


@pytest.mark.asyncio
async def test_ensure_valid_access_token_refreshes_when_expired(tmp_path) -> None:
    settings = get_settings().model_copy(
        update={"memory_db_path": tmp_path / "tokens.db", "zoho_use_mock": False}
    )
    store = TokenStore(settings)
    await store.initialize()
    auth = ZohoAuthService(settings)
    auth.refresh_token = AsyncMock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "refresh-xyz",
            "expires_in": 3600,
        }
    )

    await store.save_tokens(
        user_id="user-1",
        access_token="old-access",
        refresh_token="refresh-xyz",
        expires_in=1,
    )
    record = await store._get_record("user-1")
    assert record is not None
    record["expires_at"] = time.time() - 10
    async with aiosqlite.connect(settings.memory_db_path) as db:
        await db.execute(
            "UPDATE oauth_tokens SET expires_at = ? WHERE user_id = ?",
            (record["expires_at"], "user-1"),
        )
        await db.commit()

    token = await store.ensure_valid_access_token("user-1", auth)
    assert token == "new-access"
    auth.refresh_token.assert_awaited_once()

    updated = await store._get_record("user-1")
    assert updated["access_token"] == "new-access"
    assert updated["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_mock_mode_skips_live_refresh(tmp_path) -> None:
    settings = get_settings().model_copy(
        update={"memory_db_path": tmp_path / "mock.db", "zoho_use_mock": True}
    )
    store = TokenStore(settings)
    await store.initialize()
    tools = create_zoho_tools(settings, store, ZohoAuthService(settings))
    set_current_user("mock-jamie")
    result = await tools.list_projects()
    assert result.success
    assert result.data and result.data.count >= 1


@pytest.mark.asyncio
async def test_save_tokens_does_not_overwrite_refresh_token_with_empty(tmp_path) -> None:
    settings = get_settings().model_copy(
        update={"memory_db_path": tmp_path / "tokens.db", "zoho_use_mock": False}
    )
    store = TokenStore(settings)
    await store.initialize()

    # Save first time with a valid refresh token
    await store.save_tokens(
        user_id="user-1",
        access_token="access-1",
        refresh_token="refresh-val-1",
        expires_in=3600,
    )
    record = await store._get_record("user-1")
    assert record["refresh_token"] == "refresh-val-1"

    # Save second time with empty refresh token (e.g. re-login without prompt=consent)
    await store.save_tokens(
        user_id="user-1",
        access_token="access-2",
        refresh_token="",
        expires_in=3600,
    )
    record = await store._get_record("user-1")
    # Verify access token updated but refresh token was protected and retained
    assert record["access_token"] == "access-2"
    assert record["refresh_token"] == "refresh-val-1"


@pytest.mark.asyncio
async def test_refresh_failure_clears_tokens_and_raises_error(tmp_path) -> None:
    settings = get_settings().model_copy(
        update={"memory_db_path": tmp_path / "tokens.db", "zoho_use_mock": False}
    )
    store = TokenStore(settings)
    await store.initialize()
    auth = ZohoAuthService(settings)
    
    # Mock refresh_token to fail with RuntimeError (e.g. revoked refresh token)
    auth.refresh_token = AsyncMock(side_effect=RuntimeError("Zoho OAuth error (invalid_code)"))

    await store.save_tokens(
        user_id="user-1",
        access_token="access-1",
        refresh_token="refresh-revoked",
        expires_in=1,
    )
    
    # Verify record exists
    record = await store._get_record("user-1")
    assert record is not None

    # Force expiration
    record["expires_at"] = time.time() - 10
    async with aiosqlite.connect(settings.memory_db_path) as db:
        await db.execute(
            "UPDATE oauth_tokens SET expires_at = ? WHERE user_id = ?",
            (record["expires_at"], "user-1"),
        )
        await db.commit()

    # Try ensuring valid access token (which forces refresh because expires_in is expired)
    with pytest.raises(RuntimeError) as exc_info:
        await store.ensure_valid_access_token("user-1", auth)
    
    assert "Zoho token refresh failed" in str(exc_info.value)
    
    # Verify record was deleted from database
    deleted_record = await store._get_record("user-1")
    assert deleted_record is None


@pytest.mark.asyncio
async def test_chat_endpoint_triggers_reauth_on_refresh_failure(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.utils.config import get_settings
    
    # 1. Create custom settings pointing to our temporary database
    db_path = tmp_path / "test_chat_reauth.db"
    settings = get_settings().model_copy(
        update={
            "memory_db_path": db_path,
            "zoho_use_mock": False,
            "zoho_client_id": "test-client-id",
        }
    )
    
    # 2. Create the FastAPI app and override states
    app = create_app()
    store = TokenStore(settings)
    await store.initialize()
    
    from app.services.zoho_auth import ZohoAuthService
    auth = ZohoAuthService(settings)
    
    # Mock refresh_token to simulate invalid code/revocation
    auth.refresh_token = AsyncMock(side_effect=RuntimeError("Zoho OAuth error (invalid_code)"))
    
    # Populate database with an expired token record
    await store.save_tokens(
        user_id="mock-jamie",
        access_token="expired-access",
        refresh_token="stale-refresh",
        expires_in=1,
    )
    # Force expired state
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE oauth_tokens SET expires_at = ? WHERE user_id = ?",
            (time.time() - 100, "mock-jamie"),
        )
        await db.commit()
        
    app.state.settings = settings
    app.state.token_store = store
    app.state.zoho_auth = auth
    
    # We also need a dummy memory manager and assistant service so chat doesn't crash elsewhere
    from app.memory.manager import MemoryManager
    from app.tools.mock_data import MockDataStore
    from app.services.assistant_service import AssistantService
    from app.tools.zoho_tools import create_zoho_tools
    
    mock_store = MockDataStore()
    memory = MemoryManager(db_path, can_access_project=mock_store.user_can_access_project)
    await memory.initialize()
    app.state.memory = memory
    
    tools = create_zoho_tools(settings, store, auth, mock_store)
    app.state.assistant_service = AssistantService(memory=memory, tools=tools)
    
    # 3. Call the /chat endpoint using TestClient
    client = TestClient(app)
    response = client.post(
        "/chat",
        json={"message": "hello", "user_id": "mock-jamie", "session_id": "session-1"},
    )
    
    # 4. Verify the response status code and JSON content
    assert response.status_code == 401
    payload = response.json()
    assert payload.get("reauth_required") is True
    assert payload.get("login_url") == "/auth/login?user_id=mock-jamie"
    assert "Zoho token refresh failed" in payload.get("detail", "")
    
    # 5. Verify the token record has been deleted from the database
    record = await store._get_record("mock-jamie")
    assert record is None

