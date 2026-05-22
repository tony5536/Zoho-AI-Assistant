import json
import uuid
from pathlib import Path

import aiosqlite

from app.models.tool_models import PendingAction, ProjectContext, RecentProject


class MemoryManager:
    """SQLite-backed session memory: chat history, project context, pending actions."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_context (
                    session_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_actions (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages (session_id)
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS recent_projects (
                    session_id TEXT PRIMARY KEY,
                    projects_json TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pending_session
                ON pending_actions (session_id, status)
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT NOT NULL,
                    pref_key TEXT NOT NULL,
                    pref_value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, pref_key)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_query_history_user
                ON user_query_history (user_id, created_at DESC)
                """
            )
            await db.commit()

    async def get_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO messages (session_id, user_id, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, user_id, role, content),
            )
            await db.commit()

    async def get_project_context(self, session_id: str) -> ProjectContext | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT project_id, project_name
                FROM session_context
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return ProjectContext(
                project_id=row["project_id"],
                project_name=row["project_name"],
            )

    async def set_project_context(
        self,
        session_id: str,
        project_id: str,
        project_name: str,
    ) -> ProjectContext:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO session_context (session_id, project_id, project_name)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    project_name = excluded.project_name,
                    updated_at = datetime('now')
                """,
                (session_id, project_id, project_name),
            )
            await db.commit()
        return ProjectContext(project_id=project_id, project_name=project_name)

    async def set_recent_projects(
        self,
        session_id: str,
        projects: list[RecentProject],
    ) -> None:
        payload = json.dumps([p.model_dump() for p in projects])
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO recent_projects (session_id, projects_json)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    projects_json = excluded.projects_json,
                    updated_at = datetime('now')
                """,
                (session_id, payload),
            )
            await db.commit()

    async def get_recent_projects(self, session_id: str) -> list[RecentProject]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT projects_json FROM recent_projects WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return []
            raw = json.loads(row["projects_json"])
            return [RecentProject(**item) for item in raw]

    async def create_pending_action(
        self,
        session_id: str,
        tool: str,
        summary: str,
        payload: dict,
    ) -> PendingAction:
        action_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO pending_actions (action_id, session_id, tool, summary, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_id, session_id, tool, summary, json.dumps(payload)),
            )
            await db.commit()
        return PendingAction(
            action_id=action_id,
            tool=tool,  # type: ignore[arg-type]
            summary=summary,
            payload=payload,
        )

    async def get_pending_action(
        self,
        session_id: str,
        action_id: str,
    ) -> PendingAction | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT action_id, tool, summary, payload
                FROM pending_actions
                WHERE session_id = ? AND action_id = ? AND status = 'pending'
                """,
                (session_id, action_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return PendingAction(
                action_id=row["action_id"],
                tool=row["tool"],  # type: ignore[arg-type]
                summary=row["summary"],
                payload=json.loads(row["payload"]),
            )

    async def get_latest_pending(self, session_id: str) -> PendingAction | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT action_id, tool, summary, payload
                FROM pending_actions
                WHERE session_id = ? AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return PendingAction(
                action_id=row["action_id"],
                tool=row["tool"],  # type: ignore[arg-type]
                summary=row["summary"],
                payload=json.loads(row["payload"]),
            )

    async def dismiss_pending_action(self, session_id: str, action_id: str | None = None) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            if action_id:
                cursor = await db.execute(
                    """
                    UPDATE pending_actions
                    SET status = 'cancelled'
                    WHERE session_id = ? AND action_id = ? AND status = 'pending'
                    """,
                    (session_id, action_id),
                )
            else:
                cursor = await db.execute(
                    """
                    UPDATE pending_actions
                    SET status = 'cancelled'
                    WHERE session_id = ? AND status = 'pending'
                    """,
                    (session_id,),
                )
            await db.commit()
            return cursor.rowcount > 0

    async def set_user_preference(self, user_id: str, key: str, value: dict | str) -> None:
        payload = value if isinstance(value, str) else json.dumps(value)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO user_preferences (user_id, pref_key, pref_value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, pref_key) DO UPDATE SET
                    pref_value = excluded.pref_value,
                    updated_at = datetime('now')
                """,
                (user_id, key, payload),
            )
            await db.commit()

    async def get_user_preference(self, user_id: str, key: str) -> dict | str | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT pref_value FROM user_preferences WHERE user_id = ? AND pref_key = ?",
                (user_id, key),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            raw = row["pref_value"]
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw

    async def record_user_query(self, user_id: str, query_text: str, *, limit: int = 50) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO user_query_history (user_id, query_text) VALUES (?, ?)",
                (user_id, query_text),
            )
            await db.execute(
                """
                DELETE FROM user_query_history
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM user_query_history
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (user_id, user_id, limit),
            )
            await db.commit()

    async def get_recent_user_queries(self, user_id: str, limit: int = 5) -> list[str]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT query_text FROM user_query_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [row["query_text"] for row in rows]

    async def apply_long_term_context(self, user_id: str, session_id: str) -> ProjectContext | None:
        """Restore default project from long-term memory when session has no context."""
        existing = await self.get_project_context(session_id)
        if existing:
            return existing
        default = await self.get_user_preference(user_id, "default_project")
        if isinstance(default, dict) and default.get("project_id"):
            return await self.set_project_context(
                session_id,
                default["project_id"],
                default.get("project_name", default["project_id"]),
            )
        return None

    async def save_default_project(self, user_id: str, context: ProjectContext) -> None:
        await self.set_user_preference(
            user_id,
            "default_project",
            {"project_id": context.project_id, "project_name": context.project_name},
        )

    async def resolve_pending_action(self, action_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE pending_actions
                SET status = 'completed'
                WHERE action_id = ?
                """,
                (action_id,),
            )
            await db.commit()

    async def clear_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM session_context WHERE session_id = ?", (session_id,))
            await db.execute(
                "DELETE FROM pending_actions WHERE session_id = ?",
                (session_id,),
            )
            await db.execute(
                "DELETE FROM recent_projects WHERE session_id = ?",
                (session_id,),
            )
            await db.commit()
