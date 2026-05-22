"""Chat endpoint must return JSON even when the workflow raises."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.memory.manager import MemoryManager
from app.services.assistant_service import AssistantService
from app.tools.mock_data import MockDataStore
from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.tools.zoho_tools import create_zoho_tools
from app.utils.config import get_settings


@pytest.mark.asyncio
async def test_chat_returns_safe_json_when_workflow_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "chat_stability.db"
        settings = get_settings().model_copy(
            update={"memory_db_path": db, "zoho_use_mock": True}
        )
        mock_store = MockDataStore()
        memory = MemoryManager(
            db, can_access_project=mock_store.user_can_access_project
        )
        await memory.initialize()
        token_store = TokenStore(settings)
        await token_store.initialize()
        auth = ZohoAuthService(settings)
        tools = create_zoho_tools(settings, token_store, auth, mock_store)
        service = AssistantService(memory=memory, tools=tools)
        service._workflow.invoke = AsyncMock(side_effect=RuntimeError("boom"))

        app = create_app()
        app.state.settings = settings
        app.state.memory = memory
        app.state.assistant_service = service

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "message": "hello",
                "user_id": "mock-jamie",
                "session_id": "sess-test-1",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert "Something went wrong" in payload["reply"]
