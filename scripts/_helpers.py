from app.memory.manager import MemoryManager
from app.services.assistant_service import AssistantService
from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.tools.mock_data import MockDataStore
from app.tools.zoho_tools import create_zoho_tools
from app.utils.config import Settings, get_settings


async def build_test_service(db_path) -> AssistantService:
    settings = get_settings().model_copy(update={"zoho_use_mock": True, "memory_db_path": db_path})
    store = MockDataStore()
    memory = MemoryManager(
        settings.memory_db_path,
        can_access_project=store.user_can_access_project,
    )
    await memory.initialize()
    token_store = TokenStore(settings)
    await token_store.initialize()
    tools = create_zoho_tools(
        settings,
        token_store,
        ZohoAuthService(settings),
        store,
    )
    return AssistantService(memory=memory, tools=tools)
