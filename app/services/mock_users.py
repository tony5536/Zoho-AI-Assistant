"""Demo mock users for username/password sign-in (not for production)."""

import aiosqlite

from app.utils.config import Settings

_SEED_USERS: list[tuple[str, str, str, str]] = [
    ("mock-jamie", "jamie.lee", "jamie123", "Jamie Lee"),
    ("mock-alex", "alex.morgan", "alex123", "Alex Morgan"),
    ("mock-sam", "sam.patel", "sam123", "Sam Patel"),
]

MOCK_USER_IDS: frozenset[str] = frozenset(user_id for user_id, *_ in _SEED_USERS)

_USERNAME_TO_CANONICAL: dict[str, str] = {
    username: user_id for user_id, username, *_ in _SEED_USERS
}


def resolve_canonical_mock_user_id(
    user_id: str | None, username: str | None = None
) -> str | None:
    """Map demo usernames and legacy ids to mock-jamie / mock-alex / mock-sam."""
    if not user_id:
        return None
    uid = user_id.strip()
    if not uid:
        return None
    if uid in MOCK_USER_IDS:
        return uid
    if uid in _USERNAME_TO_CANONICAL:
        return _USERNAME_TO_CANONICAL[uid]
    if username:
        uname = username.strip()
        if uname in _USERNAME_TO_CANONICAL:
            return _USERNAME_TO_CANONICAL[uname]
    return uid


def is_canonical_mock_user_id(user_id: str | None) -> bool:
    """True for demo accounts that own the seeded mock project dataset."""
    resolved = resolve_canonical_mock_user_id(user_id)
    return bool(resolved and resolved in MOCK_USER_IDS)


class MockUserStore:
    """SQLite-backed mock user table for demo login."""

    def __init__(self, settings: Settings) -> None:
        self._db_path = settings.memory_db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS mock_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    display_name TEXT NOT NULL
                )
                """
            )
            for user_id, username, password, display_name in _SEED_USERS:
                await db.execute(
                    """
                    INSERT INTO mock_users (user_id, username, password, display_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        user_id = excluded.user_id,
                        password = excluded.password,
                        display_name = excluded.display_name
                    """,
                    (user_id, username, password, display_name),
                )
            await db.commit()

    async def verify_credentials(
        self, username: str, password: str
    ) -> dict[str, str] | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT user_id, username, display_name
                FROM mock_users
                WHERE username = ? AND password = ?
                """,
                (username.strip(), password),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            canonical_id = resolve_canonical_mock_user_id(
                row["user_id"], row["username"]
            )
            return {
                "user_id": canonical_id or row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
            }
