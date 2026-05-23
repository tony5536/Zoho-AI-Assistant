# Zoho AI Assistant

A multi-agent assistant for **Zoho Projects** with OAuth sign-in, eight API tools, session and user memory, and human-in-the-loop (HITL) approval before any write to Zoho.

**Stack:** Next.js chat UI → FastAPI backend → LangGraph (supervisor + query/action agents) → Zoho Projects API (or mock data for local dev).

---

## Features

| Area | What you get |
|------|----------------|
| **Auth** | Per-user OAuth2 (Zoho), token refresh, regional accounts servers (US, India, EU, etc.) |
| **Agents** | Supervisor routes to read-only **QueryAgent** or write **ActionAgent** |
| **Tools (8)** | List/browse projects, tasks, members, utilisation; create/update/delete tasks (writes need approval) |
| **HITL** | Create/update/delete tasks return `confirmation_required`; UI shows Confirm / Cancel |
| **Memory** | Short-term: session chat, active project, **last task** (for “that task”, “current task”, “assign it”), pending actions. Long-term (`user_memory`): last active project, recent messages, frequent project — restored on login and chat |
| **Modes** | **Primary:** real Zoho OAuth and live API. **`ZOHO_USE_MOCK=true`** is for local development/demos only (no OAuth) |

---

## Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────────────────────────┐
│  Next.js UI     │ ────────────► │  FastAPI                             │
│  (port 3000)    │               │  /auth/*  /chat  /health  /memory    │
└─────────────────┘               └──────────────────┬───────────────────┘
                                                     │
                     ┌───────────────────────────────┼───────────────────────────────┐
                     ▼                               ▼                               ▼
            LangGraph supervisor              MemoryManager (SQLite)          TokenStore (SQLite)
                     │                   short-term: history, recent            OAuth per user_id
                     │                   projects, project context, HITL          + silent refresh
                     │                   long-term: user preferences
         ┌───────────┴───────────┐
         ▼                       ▼
   QueryAgent              ActionAgent
   list_*, get_task_*      create/update/delete
   list_project_members    (HITL before execute)
   get_task_utilisation
         │                       │
         └───────────┬───────────┘
                     ▼
              ZohoTools ──► ensure_valid_access_token() ──► ZohoClient (live)
                     │         or MockDataStore (ZOHO_USE_MOCK)
                     └─► 401 retry after refresh (live only)
```

**Routing:** The supervisor uses keyword/regex cues (action verb **and** task/object cue → ActionAgent; reads and utilisation → QueryAgent). Intent parsing in `app/utils/intent.py` and `task_intent.py` maps natural language to tool operations without an LLM.

**Task follow-ups:** After you open or update a task, you can say e.g. “update **that task** status to completed”, “delete **this task**”, “**assign it** to Alex”, or “**current task**” — the session remembers the last task id (see `app/utils/task_references.py`).

**HITL:** ActionAgent stages `pending_action` in SQLite; the client sends `confirm: true` and `action_id` to execute. Cancel dismisses without calling Zoho.

**Tokens:** Before each live API call, `TokenStore.ensure_valid_access_token()` checks expiry, refreshes with the stored refresh token, persists the new access token, and retries once on HTTP 401. Mock mode skips OAuth entirely.

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- A **Zoho Projects** account
- A **Server-based** OAuth client in the [Zoho API Console](https://api-console.zoho.com/) for your datacenter (see below)

---

## Quick start

### 1. Backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

Copy the environment template and fill in your Zoho credentials:

```bash
# Windows
copy .env.example .env

# macOS / Linux
# cp .env.example .env
```

Edit **`.env`** (never commit real secrets to `.env.example`). Then start the API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API base URL: http://localhost:8000 — confirm with `curl http://localhost:8000/health` (`{"status":"ok",...}`).

**Frontend cannot reach API?** Start the backend first, then `npm run dev` in `frontend/`. Ensure `frontend/.env.local` contains `NEXT_PUBLIC_API_URL=http://localhost:8000` (see `.env.local.example`). The UI retries `/health` before showing connection errors; check the browser console for `[api]` debug lines.

### 2. Frontend

```bash
cd frontend
copy .env.local.example .env.local   # Windows
# cp .env.local.example .env.local   # macOS / Linux
npm install
npm run dev
```

Open http://localhost:3000, click **Connect Zoho**, then chat.

### 3. Mock mode (development only)

For day-to-day evaluation, use **Connect Zoho** and the live API (steps 1–2 above). Mock mode is optional for offline work:

In `.env`:

```env
ZOHO_USE_MOCK=true
```

Restart the backend. The UI skips OAuth; chat uses in-memory mock project/task data (`PRJ-001`, `TSK-101`, etc.). Do not use mock mode for production or primary QA against real Zoho data.

---

## Configuration

| Variable | Description |
|----------|-------------|
| `ZOHO_CLIENT_ID` | OAuth client ID from API Console |
| `ZOHO_CLIENT_SECRET` | OAuth client secret |
| `ZOHO_REDIRECT_URI` | Must match console — default `http://localhost:8000/auth/callback` |
| `ZOHO_ACCOUNTS_URL` | Accounts host for your region (see table below) |
| `ZOHO_API_DOMAIN` | Projects API host for your region |
| `ZOHO_PORTAL_ID` | Portal identifier from Zoho Projects URL or settings |
| `ZOHO_USE_MOCK` | `true` = mock data, no OAuth required for `/chat` |
| `FRONTEND_URL` | Where `/auth/callback` redirects after login (default `http://localhost:3000`) |
| `MEMORY_DB_PATH` | SQLite path for sessions, memory, and tokens (default `./data/memory.db`) |
| `NEXT_PUBLIC_API_URL` | Frontend → backend URL (in `frontend/.env.local`) |

### Zoho datacenter URLs

Use the API Console and accounts URL for **the same region** as your Zoho account.

| Region | API Console | `ZOHO_ACCOUNTS_URL` | `ZOHO_API_DOMAIN` |
|--------|-------------|---------------------|-------------------|
| US | [api-console.zoho.com](https://api-console.zoho.com/) | `https://accounts.zoho.com` | `https://projectsapi.zoho.com` |
| India | [api-console.zoho.in](https://api-console.zoho.in/) | `https://accounts.zoho.in` | `https://projectsapi.zoho.in` |
| EU | [api-console.zoho.eu](https://api-console.zoho.eu/) | `https://accounts.zoho.eu` | `https://projectsapi.zoho.eu` |

If login redirects to `accounts.zoho.in` but `.env` still points at `.com`, token exchange will fail. The callback uses Zoho’s `accounts-server` query parameter when present; matching `.env` values avoids issues on login and refresh.

---

## Zoho OAuth setup

1. Create a **Server-based** application in the API Console for your region.
2. Set **Authorized Redirect URI** to exactly:
   ```
   http://localhost:8000/auth/callback
   ```
   (must match `ZOHO_REDIRECT_URI` in `.env`).
3. Add scopes:
   - `ZohoProjects.projects.ALL`
   - `ZohoProjects.tasks.ALL`
   - `ZohoProjects.users.READ`
4. Copy **Client ID** and **Client Secret** into `.env`.
5. Set `ZOHO_PORTAL_ID` to your portal id (from the Projects URL or portal settings).
6. Set `ZOHO_ACCOUNTS_URL` and `ZOHO_API_DOMAIN` for your datacenter (see table above).
7. Restart uvicorn after any `.env` change.
8. In the UI, click **Connect Zoho** — after approval you should land on `http://localhost:3000?auth=success`.

**Token refresh:** You do not need to re-login when the access token expires. The backend refreshes automatically on the next chat or API call. If refresh fails (revoked app or invalid refresh token), use **Connect Zoho** again.

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/auth/login?user_id=` | Start OAuth; returns `authorization_url` |
| GET | `/auth/callback` | OAuth callback (browser redirect from Zoho) |
| GET | `/auth/status?user_id=` | Whether the user has a valid token |
| POST | `/auth/logout?user_id=` | Remove stored tokens for a user |
| POST | `/chat` | Send a message (see body below) |

### `POST /chat` body

```json
{
  "message": "list projects",
  "session_id": "unique-session-id",
  "user_id": "stable-user-id",
  "confirm": false,
  "cancel": false,
  "action_id": null
}
```

- **`user_id`** — required in live mode (from browser local storage).
- **`confirm` + `action_id`** — execute a pending write after HITL.
- **`cancel`** — dismiss pending write without executing.

Responses may include `status: "confirmation_required"`, `pending_action`, and `project_context`.

---

## Tools

| Tool | Agent | Notes |
|------|-------|-------|
| `list_projects` | Query | |
| `list_tasks` | Query | Optional filters: `status`, `assignee`, `due_date` |
| `get_task_details` | Query | |
| `list_project_members` | Query | |
| `get_task_utilisation` | Query | Per-task or summary |
| `create_task` | Action | Requires user confirmation |
| `update_task` | Action | Requires user confirmation |
| `delete_task` | Action | Requires user confirmation |

---

## Memory

- **Short-term (session):** message history, active project context, recent project list from last `list_projects`, pending HITL actions.
- **Long-term (user):** default project preference and query history keyed by `user_id`.

---

## Example prompts

| Prompt | Expected behaviour |
|--------|-------------------|
| `list projects` | Lists projects; stores recent list for “first one” references |
| `use project PRJ-001` | Sets active project context |
| `show tasks for the first one` | Tasks for first project in recent list |
| `Who are the members of PRJ-001?` | QueryAgent → `list_project_members` |
| `Show team for the first project` | Members using session memory + recent projects |
| `task details TSK-101` / `open task TSK-101` | QueryAgent → `get_task_details` |
| `Update TSK-101 status to completed` | ActionAgent → HITL → confirm applies status |
| `Assign TSK-101 to Alex Morgan` | HITL update assignee |
| `Change due date of TSK-101 to 2026-06-01` | HITL update due date |
| `Set priority of TSK-101 to high` | HITL update priority |
| `Create a task called API Integration` | HITL card → Confirm runs create |
| `who has the most tasks this month?` | Utilisation-style summary (QueryAgent) |

---

## Demo checklist

Before presenting, verify:

- [ ] `.env` exists (copied from `.env.example`) with real credentials
- [ ] `ZOHO_ACCOUNTS_URL` / `ZOHO_API_DOMAIN` match your Zoho region
- [ ] Backend running: `uvicorn app.main:app --reload --port 8000`
- [ ] Frontend running: `npm run dev` in `frontend/`
- [ ] **Connect Zoho** completes without 500 on `/auth/callback`
- [ ] Chat loads after `?auth=success`
- [ ] `list projects` returns a reply
- [ ] A create-task flow shows **Confirm** / **Cancel** and succeeds on confirm

**Fallback:** set `ZOHO_USE_MOCK=true`, restart backend, demo without live Zoho.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `Zoho OAuth is not configured` | No `.env` or empty `ZOHO_CLIENT_ID` | Copy `.env.example` → `.env`, add credentials, restart backend |
| `KeyError: 'access_token'` or 500 on `/auth/callback` | Wrong accounts region (e.g. India account, US URLs) | Set `ZOHO_ACCOUNTS_URL` / `ZOHO_API_DOMAIN` to `.in` (or your region); reconnect |
| `uid is not a function` (frontend) | Fixed in `Chat.tsx` — pull latest | Refresh / restart `npm run dev` |
| `Cannot reach the API` / connection errors | Backend not running or wrong `NEXT_PUBLIC_API_URL` | Run uvicorn; copy `frontend/.env.local.example` → `.env.local`; restart `npm run dev` |
| 401 on `/chat` | Not signed in or expired token | Connect Zoho again |
| Empty or wrong projects | Wrong `ZOHO_PORTAL_ID` | Use portal id from Projects URL/settings |

---

## Tests

Install test dependencies (included in `requirements.txt`):

```bash
pip install -r requirements.txt
```

Run the assignment test suite (mock mode, no OAuth):

```bash
# Windows
.venv\Scripts\python.exe -m pytest tests/ -v

# macOS / Linux
# .venv/bin/python -m pytest tests/ -v
```

| Test file | Covers |
|-----------|--------|
| `tests/test_get_task_details.py` | Query routing, per-user access, formatted details |
| `tests/test_update_task.py` | Action routing, HITL payload, confirm flow |
| `tests/test_project_members.py` | Context resolution (“first project”), member list |
| `tests/test_token_refresh.py` | `ensure_valid_access_token`, mock mode unchanged |

Smoke test (end-to-end script):

```bash
.venv\Scripts\python.exe scripts\smoke_test.py
```

---

## Demo prompts (new capabilities)

- Show details for TSK-101
- Update TSK-101 status to completed → confirm
- Assign TSK-101 to Alex Morgan → confirm
- Who are the members of PRJ-001?
- Show team for the first project (after `list projects`)

## Project layout

```
zoho AI-Assistant/
├── app/                 # FastAPI + agents + graph + tools
│   ├── agents/          # Supervisor, QueryAgent, ActionAgent
│   ├── graph/           # LangGraph workflow
│   ├── memory/          # SQLite session & user memory
│   ├── routes/          # auth, chat, health
│   ├── services/        # OAuth, Zoho client, tokens, assistant
│   └── tools/           # ZohoTools, mock data
├── frontend/            # Next.js chat UI
├── tests/               # pytest: task details, update, members, token refresh
├── scripts/             # smoke_test.py, legacy script tests
├── data/                # SQLite DB (created at runtime)
├── .env.example         # Template only — use placeholders
└── requirements.txt
```

---

## Known limitations

- Intent routing uses **keywords and regex**, not an LLM (`OPENAI_API_KEY` is optional and unused for routing).
- Conversational phrasing outside the supported patterns may return `unknown` or a helpful error — extend `task_intent.py` / `intent.py` for new phrases.
- Live Zoho task/project IDs and field names differ from mock labels (`PRJ-001`, `TSK-101`); map portal-specific ids in `.env`.
- `get_task_utilisation` uses mock aggregation when live task detail is unavailable; org-wide analytics are unchanged by the new tools.
- Token refresh requires a valid **offline** refresh token; revoking the OAuth app forces manual reconnect.
- `ZOHO_USE_MOCK=true` bypasses OAuth and live API — for local development only, not production.

---

## Security

- Keep secrets in **`.env`** only (gitignored).
- Use **placeholders** in `.env.example`; do not commit real client secrets.
- Rotate credentials if they were ever committed or shared.
