from fastapi import HTTPException, Request

from app.models.requests import ChatRequest
from app.services.mock_users import resolve_canonical_mock_user_id
from app.services.oauth_users import is_oauth_user_id, resolve_oauth_user_id


def _resolve_chat_user_id(raw_user_id: str | None) -> str:
    if raw_user_id and is_oauth_user_id(raw_user_id):
        return resolve_oauth_user_id(raw_user_id)
    return resolve_canonical_mock_user_id(raw_user_id) or raw_user_id or "anonymous"


async def require_chat_user(request: Request, body: ChatRequest) -> str:
    """Ensure chat requests include an authenticated user (unless mock mode)."""
    settings = request.app.state.settings
    user_id = _resolve_chat_user_id(body.user_id)

    if settings.zoho_use_mock:
        return user_id

    if not body.user_id:
        raise HTTPException(
            status_code=401,
            detail="user_id is required. Sign in with Zoho first.",
        )

    token_store = request.app.state.token_store
    if await token_store.is_demo_user(body.user_id):
        return body.user_id

    auth_service = request.app.state.zoho_auth
    try:
        token = await token_store.ensure_valid_access_token(body.user_id, auth_service)
        if not token:
            raise RuntimeError(
                f"Cannot refresh access token for user {body.user_id}: "
                "no valid Zoho tokens. Please login again."
            )
    except RuntimeError:
        raise
    return body.user_id
