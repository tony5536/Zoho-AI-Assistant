from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.models.tool_models import ProjectContext
from app.services.oauth_users import (
    OAUTH_DISPLAY_NAME,
    resolve_oauth_user_id,
)

router = APIRouter()


def _oauth_login_redirect_params(
    settings,
    *,
    user_id: str,
    session_id: str,
    auth: str,
) -> str:
    params = urlencode(
        {
            "user_id": user_id,
            "session_id": session_id,
            "auth": auth,
        }
    )
    return f"{settings.frontend_url}?{params}"


class AuthUrlResponse(BaseModel):
    authorization_url: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user_id: str


class LogoutResponse(BaseModel):
    success: bool
    message: str


class MockLoginRequest(BaseModel):
    username: str
    password: str


class MockLoginResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    welcome_message: str | None = None
    last_active_project: ProjectContext | None = None
    frequent_project: ProjectContext | None = None
    recent_queries: list[str] = Field(default_factory=list)


@router.post("/mock-login", response_model=MockLoginResponse)
async def mock_login(request: Request, body: MockLoginRequest) -> MockLoginResponse:
    """Demo sign-in with username/password (does not replace Zoho OAuth)."""
    mock_users = request.app.state.mock_user_store
    user = await mock_users.verify_credentials(body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    token_store = request.app.state.token_store
    await token_store.save_tokens(
        user_id=user["user_id"],
        access_token="mock-demo-access",
        refresh_token="mock-demo-refresh",
        expires_in=86400,
    )

    memory = request.app.state.memory
    snapshot = await memory.restore_user_memory_on_login(
        user["user_id"],
        display_name=user["display_name"],
    )
    return MockLoginResponse(
        **user,
        welcome_message=snapshot.welcome_message,
        last_active_project=snapshot.last_active_project,
        frequent_project=snapshot.frequent_project,
        recent_queries=snapshot.recent_queries,
    )


@router.get("/login", response_model=AuthUrlResponse)
async def login(
    request: Request,
    user_id: str = Query(..., min_length=1, description="Stable user identifier"),
) -> AuthUrlResponse:
    """Start Zoho OAuth (spec: GET /auth/login)."""
    return await _authorization_url(request, resolve_oauth_user_id(user_id))


@router.get("/zoho", include_in_schema=False)
async def zoho_login(
    request: Request,
    state: str = Query(default="default", description="User id passed as OAuth state"),
) -> RedirectResponse:
    """Browser entry point: redirect to Zoho OAuth (or frontend when mock)."""
    return await _redirect_to_zoho_auth(request, state)


async def _authorization_url(request: Request, user_id: str) -> AuthUrlResponse:
    settings = request.app.state.settings
    if not settings.zoho_client_id:
        raise HTTPException(
            status_code=503,
            detail="Zoho OAuth is not configured. Set ZOHO_CLIENT_ID in environment.",
        )
    auth_service = request.app.state.zoho_auth
    return AuthUrlResponse(authorization_url=auth_service.get_authorization_url(user_id))


async def _redirect_to_zoho_auth(request: Request, user_id: str) -> RedirectResponse:
    settings = request.app.state.settings

    if settings.zoho_use_mock:
        oauth_user_id = resolve_oauth_user_id(user_id)
        token_store = request.app.state.token_store
        await token_store.save_tokens(
            user_id=oauth_user_id,
            access_token="mock-access",
            refresh_token="mock-refresh",
            expires_in=86400,
        )
        memory = request.app.state.memory
        await memory.restore_user_memory_on_login(
            oauth_user_id,
            display_name=OAUTH_DISPLAY_NAME,
        )
        session_id = await memory.begin_login_session(oauth_user_id)
        return RedirectResponse(
            url=_oauth_login_redirect_params(
                settings,
                user_id=oauth_user_id,
                session_id=session_id,
                auth="success",
            )
        )

    if not settings.zoho_client_id:
        params = urlencode({"auth": "error", "user_id": user_id})
        return RedirectResponse(url=f"{settings.frontend_url}/login?{params}")

    oauth_user_id = resolve_oauth_user_id(user_id)
    auth_service = request.app.state.zoho_auth
    authorization_url = auth_service.get_authorization_url(oauth_user_id)
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(None),
    state: str = Query(default="default", description="User id from login step"),
    accounts_server: str | None = Query(
        None,
        alias="accounts-server",
        description="Regional Zoho accounts URL from OAuth redirect",
    ),
    error: str | None = Query(None),
):
    """OAuth callback — persist tokens and redirect to the chat UI."""
    settings = request.app.state.settings

    oauth_user_id = resolve_oauth_user_id(state)

    if error or not code:
        params = urlencode({"auth": "error", "user_id": oauth_user_id})
        return RedirectResponse(url=f"{settings.frontend_url}?{params}")

    auth_service = request.app.state.zoho_auth
    token_store = request.app.state.token_store

    try:
        tokens = await auth_service.exchange_code(
            code, accounts_url=accounts_server
        )
    except Exception:
        params = urlencode({"auth": "error", "user_id": oauth_user_id})
        return RedirectResponse(url=f"{settings.frontend_url}?{params}")

    accounts_url = accounts_server or settings.zoho_accounts_url
    new_refresh = tokens.get("refresh_token") or ""
    await token_store.save_tokens(
        user_id=oauth_user_id,
        access_token=tokens["access_token"],
        refresh_token=new_refresh,
        expires_in=int(tokens.get("expires_in", 3600)),
        api_domain=tokens.get("api_domain"),
        accounts_url=accounts_url,
    )
    if not new_refresh:
        await token_store.clear_refresh_token(oauth_user_id)

    memory = request.app.state.memory
    await memory.restore_user_memory_on_login(
        oauth_user_id,
        display_name=OAUTH_DISPLAY_NAME,
    )
    session_id = await memory.begin_login_session(oauth_user_id)

    return RedirectResponse(
        url=_oauth_login_redirect_params(
            settings,
            user_id=oauth_user_id,
            session_id=session_id,
            auth="success",
        )
    )


@router.get("/zoho/callback", include_in_schema=False)
async def zoho_callback_legacy(
    request: Request,
    code: str = Query(...),
    state: str = Query(default="default"),
):
    return await callback(request, code=code, state=state)


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    request: Request,
    user_id: str = Query(..., min_length=1),
) -> AuthStatusResponse:
    settings = request.app.state.settings
    token_store = request.app.state.token_store
    authenticated = await token_store.has_valid_token(user_id)
    return AuthStatusResponse(authenticated=authenticated, user_id=user_id)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    user_id: str = Query(..., min_length=1, description="User id to sign out"),
) -> LogoutResponse:
    """Remove stored OAuth tokens for the user."""
    await request.app.state.token_store.delete_tokens(user_id)
    return LogoutResponse(success=True, message="Signed out.")
