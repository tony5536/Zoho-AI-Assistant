"""Demo mock users for username/password sign-in (not for production)."""

import aiosqlite

from app.utils.config import Settings

_SEED_USERS: list[tuple[str, str, str, str]] = [
    ("mock-jamie", "jamie.lee", "jamie123", "Jamie Lee"),
    ("mock-alex", "alex.morgan", "alex123", "Alex Morgan"),
    ("mock-sam", "sam.patel", "sam123", "Sam Patel"),
]


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
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
            }
