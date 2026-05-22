import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.memory.manager import MemoryManager
from app.routes import create_api_router
from app.services.assistant_service import AssistantService
from app.services.mock_users import MockUserStore
from app.services.token_store import TokenStore
from app.services.zoho_auth import ZohoAuthService
from app.tools.mock_data import MockDataStore
from app.tools.zoho_tools import create_zoho_tools
from app.utils.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
BACKEND_URL = "http://localhost:8000"


class OriginLoggingMiddleware(BaseHTTPMiddleware):
    """Log Origin header on incoming requests for local CORS debugging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin")
        if origin:
            logger.info(
                "Incoming Origin: %s | %s %s",
                origin,
                request.method,
                request.url.path,
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    store = MockDataStore()

    memory = MemoryManager(
        settings.memory_db_path,
        can_access_project=store.user_can_access_project,
    )
    await memory.initialize()

    token_store = TokenStore(settings)
    await token_store.initialize()

    mock_user_store = MockUserStore(settings)
    await mock_user_store.initialize()

    zoho_auth = ZohoAuthService(settings)

    tools = create_zoho_tools(settings, token_store, zoho_auth, store)

    app.state.settings = settings
    app.state.memory = memory
    app.state.token_store = token_store
    app.state.mock_user_store = mock_user_store
    app.state.zoho_auth = zoho_auth
    app.state.mock_store = store
    app.state.assistant_service = AssistantService(memory=memory, tools=tools)

    logger.info("Zoho AI Assistant backend started")
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(OriginLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
    )

    logger.info(
        "CORS enabled: allow_credentials=True, allow_methods=*, allow_headers=*, allow_private_network=True"
    )
    logger.info("CORS allow_origins: %s", ALLOWED_ORIGINS)
    logger.info("Backend URL: %s", BACKEND_URL)

    # Register global exception handlers to prevent 500 crashes and return clean JSON errors
    from fastapi.responses import JSONResponse
    import httpx
    import re

    _AUTH_MARKERS = (
        "Zoho OAuth error",
        "Zoho API error",
        "Zoho token refresh failed",
        "refresh token is empty",
        "no valid Zoho tokens",
        "Please login again",
    )

    def _auth_runtime_response(err_msg: str) -> JSONResponse | None:
        if not any(marker in err_msg for marker in _AUTH_MARKERS):
            return None
        status_code = 401 if (
            "invalid_code" in err_msg
            or "refresh token is empty" in err_msg
            or "refresh failed" in err_msg
            or "no valid Zoho tokens" in err_msg
            or "Please login again" in err_msg
        ) else 400
        if status_code == 401:
            user_match = re.search(r"(?:user\s+([^\s\(\):]+))", err_msg)
            user_id = user_match.group(1) if user_match else "default"
            logger.warning("Re-authorization required for user_id=%s due to: %s", user_id, err_msg)
            return JSONResponse(
                status_code=401,
                content={
                    "reauth_required": True,
                    "login_url": f"/auth/login?user_id={user_id}",
                    "detail": "Your Zoho session expired. Please reconnect.",
                },
            )
        return JSONResponse(status_code=status_code, content={"detail": err_msg})

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError):
        logger.error("RuntimeError caught globally: %s", exc, exc_info=True)
        err_msg = str(exc)
        auth_response = _auth_runtime_response(err_msg)
        if auth_response is not None:
            return auth_response
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again."},
        )

    @app.exception_handler(httpx.HTTPStatusError)
    async def httpx_status_error_handler(request: Request, exc: httpx.HTTPStatusError):
        logger.error("httpx.HTTPStatusError caught globally: %s", exc, exc_info=True)
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text or str(exc)
        return JSONResponse(
            status_code=exc.response.status_code,
            content={"detail": f"Zoho Projects HTTP error: {detail}"},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Catch-all so handlers always return JSON (avoids proxy 'Failed to fetch')."""
        from fastapi import HTTPException as FastAPIHTTPException
        from fastapi.exceptions import RequestValidationError

        if isinstance(exc, (FastAPIHTTPException, RequestValidationError)):
            raise exc
        if isinstance(exc, RuntimeError):
            return await runtime_error_handler(request, exc)
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again."},
        )

    app.include_router(create_api_router())

    return app


app = create_app()
