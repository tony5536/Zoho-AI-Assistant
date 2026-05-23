import json
import uuid
from collections.abc import Callable
from pathlib import Path

import aiosqlite

from app.models.tool_models import PendingAction, ProjectContext, RecentProject, TaskContext
from app.utils.sqlite import configure_connection
from app.models.user_memory import StoredMessage, UserMemorySnapshot

_RECENT_QUERIES_LIMIT = 10
_RECENT_MESSAGES_LIMIT = 10
_PROJECT_ACCESS_LIMIT = 20
_RESTORE_HISTORY_LIMIT = 50
_RECENT_SESSIONS_LIMIT = 20
_SESSION_TITLE_MAX_LEN = 72
_RESTORE_CONTINUATION_MESSAGE = (
    "Welcome back — continuing your previous session."
)
_ACTIVE_SESSION_PREF = "active_session_id"


class MemoryManager:
    """SQLite-backed session and per-user long-term memory."""

    def __init__(
        self,
        db_path: Path,
        *,
        can_access_project: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._db_path = db_path
        self._can_access_project = can_access_project

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
                CREATE TABLE IF NOT EXISTS session_task_context (
                    session_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
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
                CREATE INDEX IF NOT EXISTS idx_messages_user
                ON messages (user_id, id DESC)
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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    last_active_project_json TEXT,
                    recent_messages_json TEXT NOT NULL DEFAULT '[]',
                    project_access_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.commit()
            await configure_connection(db)

    async def get_active_session_id(self, user_id: str) -> str | None:
        """Return the user's linked active session id (set on login / new session)."""
        raw = await self.get_user_preference(user_id, _ACTIVE_SESSION_PREF)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    async def set_active_session_id(self, user_id: str, session_id: str) -> None:
        await self.set_user_preference(user_id, _ACTIVE_SESSION_PREF, session_id)

    async def begin_login_session(self, user_id: str) -> str:
        """
        Start a new empty chat session on login without deleting prior sessions.
        Stores the new id as the user's active linked session.
        """
        session_id = str(uuid.uuid4())
        await self.set_active_session_id(user_id, session_id)
        return session_id

    async def get_latest_session_id_for_user(self, user_id: str) -> str | None:
        """Return the session_id of the user's most recent chat message."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT session_id FROM messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return row["session_id"]

    async def user_owns_session(self, user_id: str, session_id: str) -> bool:
        """True when the user has at least one message in the session."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM messages
                WHERE user_id = ? AND session_id = ?
                LIMIT 1
                """,
                (user_id, session_id),
            )
            return await cursor.fetchone() is not None

    async def get_recent_sessions(
        self,
        user_id: str,
        *,
        limit: int = _RECENT_SESSIONS_LIMIT,
    ) -> list[dict[str, str]]:
        """
        List recent chat sessions for a user (latest activity first).
        Title is the first user message, or the latest user message if none at start.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    m.session_id,
                    MAX(m.created_at) AS updated_at,
                    (
                        SELECT content FROM messages m1
                        WHERE m1.session_id = m.session_id
                          AND m1.user_id = ?
                          AND m1.role = 'user'
                        ORDER BY m1.id ASC
                        LIMIT 1
                    ) AS first_user,
                    (
                        SELECT content FROM messages m2
                        WHERE m2.session_id = m.session_id
                          AND m2.user_id = ?
                          AND m2.role = 'user'
                        ORDER BY m2.id DESC
                        LIMIT 1
                    ) AS latest_user
                FROM messages m
                WHERE m.user_id = ?
                GROUP BY m.session_id
                ORDER BY MAX(m.id) DESC
                LIMIT ?
                """,
                (user_id, user_id, user_id, limit),
            )
            rows = await cursor.fetchall()

        sessions: list[dict[str, str]] = []
        for row in rows:
            raw_title = row["first_user"] or row["latest_user"] or row["session_id"]
            sessions.append(
                {
                    "session_id": row["session_id"],
                    "title": self._session_title(str(raw_title)),
                    "updated_at": row["updated_at"] or "",
                }
            )
        return sessions

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """Remove all stored data for a chat session owned by the user."""
        if not await self.user_owns_session(user_id, session_id):
            return False
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            )
            await db.execute(
                "DELETE FROM session_context WHERE session_id = ?",
                (session_id,),
            )
            await db.execute(
                "DELETE FROM recent_projects WHERE session_id = ?",
                (session_id,),
            )
            await db.execute(
                "DELETE FROM pending_actions WHERE session_id = ?",
                (session_id,),
            )
            await db.commit()
        return True

    async def delete_message(self, user_id: str, message_id: int) -> bool:
        """Delete a single chat message when it belongs to the user."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM messages WHERE id = ? AND user_id = ?",
                (message_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _session_title(content: str) -> str:
        text = " ".join(content.split())
        if len(text) <= _SESSION_TITLE_MAX_LEN:
            return text
        return text[: _SESSION_TITLE_MAX_LEN - 1].rstrip() + "…"

    async def restore_user_session(
        self,
        user_id: str,
        *,
        session_id: str | None = None,
        history_limit: int = _RESTORE_HISTORY_LIMIT,
    ) -> dict[str, object] | None:
        """
        Restore a session for a user: chat history, project context,
        and recent projects. Pending actions are cancelled (never auto-resumed).
        When session_id is omitted, restores the latest session.
        """
        if session_id is None:
            session_id = await self.get_active_session_id(user_id)
            if session_id is None:
                session_id = await self.get_latest_session_id_for_user(user_id)
        elif not await self.user_owns_session(user_id, session_id):
            return None

        if session_id is None:
            return None

        await self.dismiss_pending_action(session_id)

        history = await self.get_history(session_id, limit=history_limit)
        if not history:
            return None
        project_context = await self.get_project_context(session_id)
        if project_context is None:
            project_context = await self.apply_user_memory_to_session(
                user_id, session_id
            )
        recent_projects = await self.get_recent_projects(session_id)
        snapshot = await self.restore_user_memory_on_login(user_id)

        return {
            "session_id": session_id,
            "messages": history,
            "project_context": project_context,
            "recent_projects": recent_projects,
            "snapshot": snapshot,
            "restore_message": _RESTORE_CONTINUATION_MESSAGE,
        }

    async def get_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                }
                for row in rows
            ]

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

    async def get_task_context(self, session_id: str) -> TaskContext | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT task_id, task_name
                FROM session_task_context
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return TaskContext(task_id=row["task_id"], task_name=row["task_name"])

    async def set_task_context(
        self,
        session_id: str,
        task_id: str,
        task_name: str,
    ) -> TaskContext:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO session_task_context (session_id, task_id, task_name)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    task_id = excluded.task_id,
                    task_name = excluded.task_name,
                    updated_at = datetime('now')
                """,
                (session_id, task_id, task_name),
            )
            await db.commit()
        return TaskContext(task_id=task_id, task_name=task_name)

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
            return [self._parse_recent_project(item) for item in raw]

    @staticmethod
    def _parse_recent_project(item: dict) -> RecentProject:
        """Accept legacy ``index`` field from older stored project lists."""
        data = dict(item)
        if "position" not in data and "index" in data:
            data["position"] = data["index"]
        return RecentProject(**data)

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
        """Restore active project from per-user memory when session has no context."""
        return await self.apply_user_memory_to_session(user_id, session_id)

    async def save_default_project(self, user_id: str, context: ProjectContext) -> None:
        validated = self._validate_project_context(user_id, context)
        if validated is None:
            return
        await self.set_user_preference(
            user_id,
            "default_project",
            {
                "project_id": validated.project_id,
                "project_name": validated.project_name,
            },
        )
        await self._save_last_active_project(user_id, validated)
        await self._record_project_access(user_id, validated)

    async def load_user_memory(self, user_id: str) -> UserMemorySnapshot:
        """Load persisted long-term memory for a user."""
        row = await self._fetch_user_memory_row(user_id)
        if row is None:
            legacy = await self._legacy_default_project(user_id)
            legacy = self._validate_project_context(user_id, legacy)
            return UserMemorySnapshot(
                user_id=user_id,
                last_active_project=legacy,
                frequent_project=None,
                recent_queries=await self.get_recent_user_queries(user_id),
            )

        last_active = self._parse_project_json(row["last_active_project_json"])
        if last_active is None:
            last_active = await self._legacy_default_project(user_id)

        access = self._parse_project_access(row["project_access_json"])
        last_active, access = self._sanitize_user_projects(user_id, last_active, access)
        frequent = self._top_frequent_project(access)
        recent_queries = self._recent_queries_from_messages(row["recent_messages_json"])

        await self._repair_stored_projects(user_id, last_active, access)

        return UserMemorySnapshot(
            user_id=user_id,
            display_name=row["display_name"],
            last_active_project=last_active,
            frequent_project=frequent,
            recent_queries=recent_queries,
            welcome_message=self.build_welcome_message(
                display_name=row["display_name"],
                last_active_project=last_active,
                frequent_project=frequent,
            ),
        )

    async def save_user_memory(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        last_active_project: ProjectContext | None = None,
        user_message: str | None = None,
        assistant_reply: str | None = None,
        project_context: ProjectContext | None = None,
    ) -> None:
        """Persist long-term memory fields for a user."""
        row = await self._fetch_user_memory_row(user_id)
        current_name = row["display_name"] if row else None
        current_last = (
            self._parse_project_json(row["last_active_project_json"]) if row else None
        )
        current_messages = (
            self._parse_messages_json(row["recent_messages_json"]) if row else []
        )
        current_access = (
            self._parse_project_access(row["project_access_json"]) if row else {}
        )

        name = display_name or current_name
        last = last_active_project or project_context or current_last
        messages = list(current_messages)
        if user_message:
            messages.append(StoredMessage(role="user", content=user_message))
        if assistant_reply:
            messages.append(StoredMessage(role="assistant", content=assistant_reply))
        messages = messages[-_RECENT_MESSAGES_LIMIT :]

        access = dict(current_access)
        ctx = self._validate_project_context(
            user_id, project_context or last_active_project
        )
        last = ctx or (self._validate_project_context(user_id, last) if last else None)
        if ctx:
            access = self._filter_project_access(user_id, access)
            access = self._bump_access(access, ctx)
        else:
            access = self._filter_project_access(user_id, access)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO user_memory (
                    user_id,
                    display_name,
                    last_active_project_json,
                    recent_messages_json,
                    project_access_json
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, user_memory.display_name),
                    last_active_project_json = COALESCE(
                        excluded.last_active_project_json,
                        user_memory.last_active_project_json
                    ),
                    recent_messages_json = excluded.recent_messages_json,
                    project_access_json = excluded.project_access_json,
                    updated_at = datetime('now')
                """,
                (
                    user_id,
                    name,
                    json.dumps(last.model_dump()) if last else None,
                    json.dumps([m.model_dump() for m in messages]),
                    json.dumps(access),
                ),
            )
            await db.commit()

    async def restore_user_memory_on_login(
        self,
        user_id: str,
        display_name: str | None = None,
    ) -> UserMemorySnapshot:
        """Load user memory on login and refresh display name when known."""
        if display_name:
            await self._ensure_user_memory_row(user_id, display_name)
        snapshot = await self.load_user_memory(user_id)
        if display_name and not snapshot.display_name:
            snapshot = snapshot.model_copy(update={"display_name": display_name})
        snapshot = snapshot.model_copy(
            update={
                "welcome_message": self.build_welcome_message(
                    display_name=snapshot.display_name,
                    last_active_project=snapshot.last_active_project,
                    frequent_project=snapshot.frequent_project,
                )
            }
        )
        return snapshot

    async def apply_user_memory_to_session(
        self,
        user_id: str,
        session_id: str,
    ) -> ProjectContext | None:
        """Preload last active project into session context when the session is new."""
        existing = await self.get_project_context(session_id)
        if existing:
            return existing

        snapshot = await self.load_user_memory(user_id)
        if snapshot.last_active_project:
            return await self.set_project_context(
                session_id,
                snapshot.last_active_project.project_id,
                snapshot.last_active_project.project_name,
            )
        return None

    async def sync_user_memory_on_chat(
        self,
        user_id: str,
        session_id: str,
        *,
        user_message: str | None = None,
        assistant_reply: str | None = None,
        project_context: ProjectContext | None = None,
    ) -> None:
        """Apply memory to the session before chat and persist updates after."""
        await self.apply_user_memory_to_session(user_id, session_id)
        if user_message or assistant_reply or project_context:
            await self.save_user_memory(
                user_id,
                user_message=user_message,
                assistant_reply=assistant_reply,
                project_context=project_context,
            )

    @staticmethod
    def build_welcome_message(
        *,
        display_name: str | None,
        last_active_project: ProjectContext | None,
        frequent_project: ProjectContext | None,
    ) -> str | None:
        parts: list[str] = []
        if display_name:
            parts.append(f"Welcome back {display_name}.")
        if last_active_project:
            parts.append(
                f"Last time you worked on {last_active_project.project_name}."
            )
        if frequent_project and (
            not last_active_project
            or frequent_project.project_id != last_active_project.project_id
        ):
            parts.append(f"You frequently access {frequent_project.project_id}.")
        if not parts:
            return None
        return " ".join(parts)

    async def _fetch_user_memory_row(self, user_id: str) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT display_name, last_active_project_json,
                       recent_messages_json, project_access_json
                FROM user_memory
                WHERE user_id = ?
                """,
                (user_id,),
            )
            return await cursor.fetchone()

    async def _ensure_user_memory_row(
        self, user_id: str, display_name: str | None = None
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            if display_name:
                await db.execute(
                    """
                    INSERT INTO user_memory (user_id, display_name)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        updated_at = datetime('now')
                    """,
                    (user_id, display_name),
                )
            else:
                await db.execute(
                    "INSERT OR IGNORE INTO user_memory (user_id) VALUES (?)",
                    (user_id,),
                )
            await db.commit()

    async def _save_last_active_project(
        self, user_id: str, context: ProjectContext
    ) -> None:
        await self._ensure_user_memory_row(user_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE user_memory
                SET last_active_project_json = ?,
                    updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (json.dumps(context.model_dump()), user_id),
            )
            await db.commit()

    async def _record_project_access(
        self, user_id: str, context: ProjectContext
    ) -> None:
        row = await self._fetch_user_memory_row(user_id)
        access = self._parse_project_access(row["project_access_json"]) if row else {}
        access = self._bump_access(access, context)
        await self._ensure_user_memory_row(user_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE user_memory
                SET project_access_json = ?,
                    updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (json.dumps(access), user_id),
            )
            await db.commit()

    async def _legacy_default_project(self, user_id: str) -> ProjectContext | None:
        default = await self.get_user_preference(user_id, "default_project")
        if isinstance(default, dict) and default.get("project_id"):
            return self._validate_project_context(
                user_id,
                ProjectContext(
                    project_id=default["project_id"],
                    project_name=default.get("project_name", default["project_id"]),
                ),
            )
        return None

    def _validate_project_context(
        self, user_id: str, context: ProjectContext | None
    ) -> ProjectContext | None:
        if context is None:
            return None
        if self._can_access_project is None:
            return context
        if self._can_access_project(user_id, context.project_id):
            return context
        return None

    def _filter_project_access(
        self, user_id: str, access: dict[str, dict]
    ) -> dict[str, dict]:
        if self._can_access_project is None:
            return access
        return {
            pid: entry
            for pid, entry in access.items()
            if self._can_access_project(user_id, pid)
        }

    def _sanitize_user_projects(
        self,
        user_id: str,
        last_active: ProjectContext | None,
        access: dict[str, dict],
    ) -> tuple[ProjectContext | None, dict[str, dict]]:
        access = self._filter_project_access(user_id, access)
        last_active = self._validate_project_context(user_id, last_active)
        if last_active is None:
            last_active = self._top_frequent_project(access)
        return last_active, access

    async def _repair_stored_projects(
        self,
        user_id: str,
        last_active: ProjectContext | None,
        access: dict[str, dict],
    ) -> None:
        """Persist sanitized project memory and drop invalid legacy defaults."""
        row = await self._fetch_user_memory_row(user_id)
        if row is None:
            return

        raw_last = self._parse_project_json(row["last_active_project_json"])
        raw_access = self._parse_project_access(row["project_access_json"])
        legacy = await self.get_user_preference(user_id, "default_project")

        needs_repair = raw_last != last_active or raw_access != access
        if isinstance(legacy, dict) and legacy.get("project_id"):
            legacy_ctx = ProjectContext(
                project_id=legacy["project_id"],
                project_name=legacy.get("project_name", legacy["project_id"]),
            )
            if self._validate_project_context(user_id, legacy_ctx) is None:
                needs_repair = True

        if not needs_repair:
            return

        await self._ensure_user_memory_row(user_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE user_memory
                SET last_active_project_json = ?,
                    project_access_json = ?,
                    updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (
                    json.dumps(last_active.model_dump()) if last_active else None,
                    json.dumps(access),
                    user_id,
                ),
            )
            await db.commit()

        if isinstance(legacy, dict) and legacy.get("project_id"):
            if self._validate_project_context(
                user_id,
                ProjectContext(
                    project_id=legacy["project_id"],
                    project_name=legacy.get("project_name", legacy["project_id"]),
                ),
            ) is None:
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute(
                        """
                        DELETE FROM user_preferences
                        WHERE user_id = ? AND pref_key = 'default_project'
                        """,
                        (user_id,),
                    )
                    await db.commit()
            elif last_active:
                await self.set_user_preference(
                    user_id,
                    "default_project",
                    {
                        "project_id": last_active.project_id,
                        "project_name": last_active.project_name,
                    },
                )

    @staticmethod
    def _parse_project_json(raw: str | None) -> ProjectContext | None:
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict) and data.get("project_id"):
            return ProjectContext(
                project_id=data["project_id"],
                project_name=data.get("project_name", data["project_id"]),
            )
        return None

    @staticmethod
    def _parse_messages_json(raw: str | None) -> list[StoredMessage]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [StoredMessage(**item) for item in data if isinstance(item, dict)]

    @staticmethod
    def _parse_project_access(raw: str | None) -> dict[str, dict]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _bump_access(
        access: dict[str, dict], context: ProjectContext
    ) -> dict[str, dict]:
        entry = access.get(context.project_id, {})
        count = int(entry.get("count", 0)) + 1
        access[context.project_id] = {
            "project_id": context.project_id,
            "project_name": context.project_name,
            "count": count,
        }
        if len(access) > _PROJECT_ACCESS_LIMIT:
            sorted_ids = sorted(
                access,
                key=lambda pid: int(access[pid].get("count", 0)),
            )
            for pid in sorted_ids[: len(access) - _PROJECT_ACCESS_LIMIT]:
                del access[pid]
        return access

    @staticmethod
    def _top_frequent_project(access: dict[str, dict]) -> ProjectContext | None:
        if not access:
            return None
        top_id = max(access, key=lambda pid: int(access[pid].get("count", 0)))
        top = access[top_id]
        return ProjectContext(
            project_id=top.get("project_id", top_id),
            project_name=top.get("project_name", top_id),
        )

    @staticmethod
    def _recent_queries_from_messages(raw: str | None) -> list[str]:
        messages = MemoryManager._parse_messages_json(raw)
        return [m.content for m in messages if m.role == "user"][-_RECENT_QUERIES_LIMIT:]

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
