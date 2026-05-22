import time
import logging
import aiosqlite

from app.utils.config import Settings
from app.utils.sqlite import configure_connection

logger = logging.getLogger(__name__)


class TokenStore:
    """Per-user OAuth tokens with automatic refresh."""

    @staticmethod
    def is_demo_access_token(access_token: str | None) -> bool:
        """True for mock-login / demo OAuth placeholders (not real Zoho tokens)."""
        return bool(access_token and access_token.startswith("mock-"))

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.memory_db_path
        self._reauth_required: set[str] = set()

    async def initialize(self) -> None:
        logger.info("Initializing TokenStore database at: %s", self._db_path)
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
                logger.info("Migrating oauth_tokens: adding accounts_url column")
                await db.execute(
                    "ALTER TABLE oauth_tokens ADD COLUMN accounts_url TEXT"
                )
            await db.commit()
            await configure_connection(db)

    async def clear_refresh_token(self, user_id: str) -> None:
        """Remove a stale refresh token after OAuth re-login without a new refresh."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE oauth_tokens SET refresh_token = '' WHERE user_id = ?",
                (user_id,),
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
        logger.info(
            "Saving tokens for user %s: has_refresh_token=%s, expires_in=%s",
            user_id,
            bool(refresh_token),
            expires_in,
        )
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO oauth_tokens (
                    user_id, access_token, refresh_token, expires_at, api_domain, accounts_url
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = CASE
                        WHEN excluded.refresh_token IS NOT NULL AND excluded.refresh_token != '' THEN excluded.refresh_token
                        ELSE oauth_tokens.refresh_token
                    END,
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
            logger.info("Successfully saved/updated tokens in database for user_id=%s", user_id)
        self._reauth_required.discard(user_id)

    async def is_demo_user(self, user_id: str) -> bool:
        record = await self._get_record(user_id)
        if record is None:
            return False
        return self.is_demo_access_token(record.get("access_token"))

    async def has_valid_token(self, user_id: str) -> bool:
        record = await self._get_record(user_id)
        if record is None:
            return False
        if self.is_demo_access_token(record.get("access_token")):
            return True
        # Valid token is present and not expired
        return not self.is_token_expired(record)

    def is_token_expired(self, record: dict) -> bool:
        expired = record["expires_at"] <= time.time()
        if expired:
            logger.info("Token for user is expired (expired_at=%s, now=%s)", record["expires_at"], time.time())
        return expired

    async def ensure_valid_access_token(self, user_id: str, auth_service) -> str | None:
        """Return a usable access token, refreshing silently when expired."""
        if user_id in self._reauth_required:
            logger.info("Skipping token refresh for user_id=%s (reauth required)", user_id)
            return None
        record = await self._get_record(user_id)
        if record is None:
            logger.warning("No tokens record found in database for user_id=%s", user_id)
            return None
        if self.is_demo_access_token(record.get("access_token")):
            return record["access_token"]
        if not self.is_token_expired(record):
            return record["access_token"]
        logger.info("Token expired for user_id=%s, attempting silent refresh", user_id)
        return await self._refresh_access_token(user_id, auth_service, record)

    async def refresh_access_token(self, user_id: str, auth_service) -> str | None:
        """Force refresh using the stored refresh token."""
        logger.info("Forced refresh requested for user_id=%s", user_id)
        record = await self._get_record(user_id)
        if record is None:
            logger.warning("Force refresh failed: no tokens record found for user_id=%s", user_id)
            return None
        return await self._refresh_access_token(user_id, auth_service, record)

    async def get_access_token(self, user_id: str, auth_service) -> str | None:
        return await self.ensure_valid_access_token(user_id, auth_service)

    async def get_api_domain(self, user_id: str) -> str | None:
        record = await self._get_record(user_id)
        return record.get("api_domain") if record else None

    async def delete_tokens(self, user_id: str) -> None:
        logger.warning("Deleting Zoho tokens from database for user_id=%s", user_id)
        self._reauth_required.add(user_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM oauth_tokens WHERE user_id = ?", (user_id,))
            await db.commit()
            logger.info("Successfully deleted tokens from database for user_id=%s", user_id)

    async def _refresh_access_token(
        self, user_id: str, auth_service, record: dict
    ) -> str | None:
        logger.info("Executing silent access token refresh for user_id=%s", user_id)
        if self.is_demo_access_token(record.get("access_token")):
            return record["access_token"]
        refresh_value = record.get("refresh_token") or ""
        if refresh_value.startswith("mock-"):
            return record["access_token"]
        if not refresh_value:
            logger.error("No refresh token found for user_id=%s. Stored refresh token is empty.", user_id)
            await self.delete_tokens(user_id)
            raise RuntimeError(
                f"Cannot refresh access token for user {user_id}: refresh token is empty or missing. Please login again."
            )
        try:
            refreshed = await auth_service.refresh_token(
                record["refresh_token"],
                accounts_url=record.get("accounts_url"),
            )
        except Exception as exc:
            logger.error(
                "Silent token refresh failed for user_id=%s: %s. Clearing invalid tokens.",
                user_id,
                exc,
                exc_info=True,
            )
            await self.delete_tokens(user_id)
            raise RuntimeError(
                f"Zoho token refresh failed for user {user_id} ({str(exc)}). Please login again."
            ) from exc

        await self.save_tokens(
            user_id=user_id,
            access_token=refreshed["access_token"],
            refresh_token=refreshed.get("refresh_token", record["refresh_token"]),
            expires_in=int(refreshed.get("expires_in", 3600)),
            api_domain=refreshed.get("api_domain", record.get("api_domain")),
            accounts_url=record.get("accounts_url"),
        )
        logger.info("Successfully refreshed access token for user_id=%s", user_id)
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

