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
