from fastapi import HTTPException, Request

from app.models.requests import ChatRequest


async def require_chat_user(request: Request, body: ChatRequest) -> str:
    """Ensure chat requests include an authenticated user (unless mock mode)."""
    settings = request.app.state.settings
    user_id = body.user_id or "anonymous"

    if settings.zoho_use_mock:
        return user_id

    if not body.user_id:
        raise HTTPException(
            status_code=401,
            detail="user_id is required. Sign in with Zoho first.",
        )

    token_store = request.app.state.token_store
    auth_service = request.app.state.zoho_auth
    try:
        token = await token_store.ensure_valid_access_token(body.user_id, auth_service)
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated with Zoho. Visit /auth/login to connect.",
            )
    except RuntimeError:
        raise
    return body.user_id
