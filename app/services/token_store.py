import time

import aiosqlite

from app.utils.config import Settings


class TokenStore:
    """Per-user OAuth tokens with automatic refresh."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.memory_db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    user_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    api_domain TEXT,
                    accounts_url TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            cursor = await db.execute("PRAGMA table_info(oauth_tokens)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "accounts_url" not in columns:
                await db.execute(
                    "ALTER TABLE oauth_tokens ADD COLUMN accounts_url TEXT"
                )
            await db.commit()

    async def save_tokens(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        api_domain: str | None = None,
        accounts_url: str | None = None,
    ) -> None:
        expires_at = time.time() + max(int(expires_in) - 60, 60)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO oauth_tokens (
                    user_id, access_token, refresh_token, expires_at, api_domain, accounts_url
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    api_domain = excluded.api_domain,
                    accounts_url = excluded.accounts_url,
                    updated_at = datetime('now')
                """,
                (
                    user_id,
                    access_token,
                    refresh_token,
                    expires_at,
                    api_domain,
                    accounts_url,
                ),
            )
            await db.commit()

    async def has_valid_token(self, user_id: str) -> bool:
        record = await self._get_record(user_id)
        return record is not None

    def is_token_expired(self, record: dict) -> bool:
        return record["expires_at"] <= time.time()

    async def ensure_valid_access_token(self, user_id: str, auth_service) -> str | None:
        """Return a usable access token, refreshing silently when expired."""
        record = await self._get_record(user_id)
        if record is None:
            return None
        if not self.is_token_expired(record):
            return record["access_token"]
        return await self._refresh_access_token(user_id, auth_service, record)

    async def refresh_access_token(self, user_id: str, auth_service) -> str | None:
        """Force refresh using the stored refresh token."""
        record = await self._get_record(user_id)
        if record is None:
            return None
        return await self._refresh_access_token(user_id, auth_service, record)

    async def get_access_token(self, user_id: str, auth_service) -> str | None:
        return await self.ensure_valid_access_token(user_id, auth_service)

    async def get_api_domain(self, user_id: str) -> str | None:
        record = await self._get_record(user_id)
        return record.get("api_domain") if record else None

    async def delete_tokens(self, user_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM oauth_tokens WHERE user_id = ?", (user_id,))
            await db.commit()

    async def _refresh_access_token(
        self, user_id: str, auth_service, record: dict
    ) -> str | None:
        refreshed = await auth_service.refresh_token(
            record["refresh_token"],
            accounts_url=record.get("accounts_url"),
        )
        await self.save_tokens(
            user_id=user_id,
            access_token=refreshed["access_token"],
            refresh_token=refreshed.get("refresh_token", record["refresh_token"]),
            expires_in=int(refreshed.get("expires_in", 3600)),
            api_domain=refreshed.get("api_domain", record.get("api_domain")),
            accounts_url=record.get("accounts_url"),
        )
        updated = await self._get_record(user_id)
        return updated["access_token"] if updated else None

    async def _get_record(self, user_id: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT access_token, refresh_token, expires_at, api_domain, accounts_url FROM oauth_tokens WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)
