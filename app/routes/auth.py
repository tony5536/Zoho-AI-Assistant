from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()


class AuthUrlResponse(BaseModel):
    authorization_url: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user_id: str


@router.get("/login", response_model=AuthUrlResponse)
async def login(
    request: Request,
    user_id: str = Query(..., min_length=1, description="Stable user identifier"),
) -> AuthUrlResponse:
    """Start Zoho OAuth (spec: GET /auth/login)."""
    return await _authorization_url(request, user_id)


@router.get("/zoho", response_model=AuthUrlResponse, include_in_schema=False)
async def zoho_login_legacy(
    request: Request,
    state: str = Query(default="default", description="User id passed as OAuth state"),
) -> AuthUrlResponse:
    return await _authorization_url(request, state)


async def _authorization_url(request: Request, user_id: str) -> AuthUrlResponse:
    settings = request.app.state.settings
    if not settings.zoho_client_id:
        raise HTTPException(
            status_code=503,
            detail="Zoho OAuth is not configured. Set ZOHO_CLIENT_ID in environment.",
        )
    auth_service = request.app.state.zoho_auth
    return AuthUrlResponse(authorization_url=auth_service.get_authorization_url(user_id))


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

    if error or not code:
        params = urlencode({"auth": "error", "user_id": state})
        return RedirectResponse(url=f"{settings.frontend_url}?{params}")

    auth_service = request.app.state.zoho_auth
    token_store = request.app.state.token_store

    try:
        tokens = await auth_service.exchange_code(
            code, accounts_url=accounts_server
        )
    except Exception:
        params = urlencode({"auth": "error", "user_id": state})
        return RedirectResponse(url=f"{settings.frontend_url}?{params}")

    accounts_url = accounts_server or settings.zoho_accounts_url
    await token_store.save_tokens(
        user_id=state,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),
        expires_in=int(tokens.get("expires_in", 3600)),
        api_domain=tokens.get("api_domain"),
        accounts_url=accounts_url,
    )

    params = urlencode({"user_id": state, "auth": "success"})
    return RedirectResponse(url=f"{settings.frontend_url}?{params}")


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
    if settings.zoho_use_mock:
        return AuthStatusResponse(authenticated=True, user_id=user_id)
    token_store = request.app.state.token_store
    authenticated = await token_store.has_valid_token(user_id)
    return AuthStatusResponse(authenticated=authenticated, user_id=user_id)


@router.post("/logout")
async def logout(request: Request, user_id: str = Query(..., min_length=1)) -> dict:
    await request.app.state.token_store.delete_tokens(user_id)
    return {"message": "Signed out."}
