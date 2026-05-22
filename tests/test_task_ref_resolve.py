"""Task display-key resolution for Zoho tools."""

import pytest

from app.services.zoho_client import _task_ref_matches
from app.tools.zoho_tools import ZohoTools
from app.utils.config import Settings


def test_task_ref_matches_display_key() -> None:
    raw = {"id_string": "8844221100", "key": "TSK-501", "project_id": "PRJ-001"}
    assert _task_ref_matches(raw, "TSK-501", "TSK-501")
    assert _task_ref_matches(raw, "8844221100", "8844221100")


def test_task_ref_matches_prefix_number() -> None:
    raw = {"id": "99", "prefix": "TSK", "number": "501", "project_id": "PRJ-001"}
    assert _task_ref_matches(raw, "TSK-501", "TSK-501")


@pytest.mark.asyncio
async def test_resolve_task_ref_mock() -> None:
    from app.services.zoho_auth import ZohoAuthService
    from app.services.token_store import TokenStore
    from app.services.zoho_client import ZohoClient
    from app.tools.mock_data import MockDataStore

    settings = Settings()
    from app.tools.zoho_tools import set_current_user

    tools = ZohoTools(
        settings,
        TokenStore(settings),
        ZohoAuthService(settings),
        ZohoClient(settings),
        store=MockDataStore(),
    )
    set_current_user("mock-jamie")
    resolved = await tools._resolve_task_ref("TSK-101")
    assert resolved == ("TSK-101", "PRJ-001")

    missing = await tools._resolve_task_ref("TSK-999")
    assert missing is None
