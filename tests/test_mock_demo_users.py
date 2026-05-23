"""Canonical mock demo users must always see seeded projects (not live Zoho)."""

import tempfile
from pathlib import Path

import pytest

from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.tools.mock_data import MockDataStore, get_shared_mock_store
from app.tools.zoho_tools import create_zoho_tools, set_current_user
from app.utils.config import get_settings


@pytest.mark.asyncio
async def test_mock_jamie_sees_seed_projects_when_not_zoho_use_mock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "mock_demo.db"
        settings = get_settings().model_copy(
            update={"memory_db_path": db, "zoho_use_mock": False}
        )
        store = get_shared_mock_store(reset=True)
        token_store = TokenStore(settings)
        await token_store.initialize()
        auth = ZohoAuthService(settings)
        tools = create_zoho_tools(settings, token_store, auth, store)

        await token_store.save_tokens(
            "mock-jamie",
            access_token="zoho-real-looking-access-token",
            refresh_token="zoho-real-looking-refresh",
            expires_in=3600,
        )

        set_current_user("mock-jamie")
        result = await tools.list_projects()
        assert result.success is True
        assert result.data is not None
        assert result.data.count == 2
        names = {p.name for p in result.data.projects}
        assert "Website Redesign" in names
        assert "Internal IT Rollout" in names


@pytest.mark.asyncio
async def test_random_user_id_sees_no_seed_projects() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "anon.db"
        settings = get_settings().model_copy(
            update={"memory_db_path": db, "zoho_use_mock": False}
        )
        store = MockDataStore()
        token_store = TokenStore(settings)
        await token_store.initialize()
        auth = ZohoAuthService(settings)
        tools = create_zoho_tools(settings, token_store, auth, store)

        set_current_user("random-anonymous-uuid")
        result = await tools.list_projects()
        assert result.success is True
        assert result.data is not None
        assert result.data.count == 0
