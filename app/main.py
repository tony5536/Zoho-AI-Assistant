from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.memory.manager import MemoryManager
from app.routes import create_api_router
from app.services.assistant_service import AssistantService
from app.services.mock_users import MockUserStore
from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.tools.mock_data import MockDataStore
from app.tools.zoho_tools import create_zoho_tools
from app.utils.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    memory = MemoryManager(settings.memory_db_path)
    await memory.initialize()

    token_store = TokenStore(settings)
    await token_store.initialize()

    mock_user_store = MockUserStore(settings)
    await mock_user_store.initialize()

    zoho_auth = ZohoAuthService(settings)
    store = MockDataStore()
    tools = create_zoho_tools(settings, token_store, zoho_auth, store)

    app.state.settings = settings
    app.state.memory = memory
    app.state.token_store = token_store
    app.state.mock_user_store = mock_user_store
    app.state.zoho_auth = zoho_auth
    app.state.mock_store = store
    app.state.assistant_service = AssistantService(memory=memory, tools=tools)

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_api_router())
    return app


app = create_app()
