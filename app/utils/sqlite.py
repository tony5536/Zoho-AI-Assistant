"""Shared SQLite pragmas for concurrent FastAPI handlers."""

import aiosqlite


async def configure_connection(db: aiosqlite.Connection) -> None:
    """Reduce lock contention when chat and memory endpoints run in parallel."""
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
