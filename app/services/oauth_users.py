"""Canonical OAuth demo identity (isolated from mock username/password users)."""

OAUTH_USER_ID = "tony-reno"
OAUTH_DISPLAY_NAME = "Tony Reno"

OAUTH_USER_IDS: frozenset[str] = frozenset({OAUTH_USER_ID})


def is_oauth_user_id(user_id: str | None) -> bool:
    if not user_id:
        return False
    return user_id.strip() in OAUTH_USER_IDS


def resolve_oauth_user_id(user_id: str | None = None) -> str:
    """Map any OAuth state / legacy id to the canonical demo OAuth user."""
    _ = user_id
    return OAUTH_USER_ID
