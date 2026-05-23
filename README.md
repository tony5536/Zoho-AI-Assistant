# Zoho Projects AI Assistant

An AI-powered conversational assistant for Zoho Projects built using **FastAPI**, **LangGraph**, and **Next.js**.
Users authenticate using their own Zoho OAuth credentials and interact with their projects using natural language through a browser-based chat interface.

---

# Features

## OAuth 2.0 Authentication

* Zoho Authorization Code Grant flow
* User-specific access and refresh tokens
* Silent token refresh
* Protected chat access after login only

## Multi-Agent Architecture

The system uses a LangGraph-based multi-agent workflow:

### Query Agent

Handles:

* Listing projects
* Listing tasks
* Task details
* Project members
* Task utilisation

### Action Agent

Handles:

* Create task
* Update task
* Delete task

All write operations require:

* Human-in-the-loop confirmation
* Explicit user approval before execution

### Supervisor Agent

Routes incoming user messages to the correct agent.

---

# Tech Stack

## Backend

* FastAPI
* LangGraph
* SQLite
* httpx
* Pydantic

## Frontend

* Next.js
* React
* TypeScript

## AI Architecture

* Supervisor Agent
* Query Agent
* Action Agent

---

# Project Architecture

```text
Frontend (Next.js)
        |
        v
FastAPI Backend
        |
        v
LangGraph Workflow
 ┌──────────────┐
 │ Supervisor   │
 └──────┬───────┘
        |
 ┌──────┴───────┐
 |              |
 v              v
Query Agent   Action Agent
```

---

# Assignment Requirements Coverage

| Requirement                    | Status |
| ------------------------------ | ------ |
| OAuth 2.0 Login                | ✅      |
| Multi-Agent Architecture       | ✅      |
| LangGraph Stateful Workflow    | ✅      |
| 8 Required Tools               | ✅      |
| Human-in-the-Loop Confirmation | ✅      |
| FastAPI Backend                | ✅      |
| Browser Chat UI                | ✅      |
| Short-Term Memory              | ✅      |
| Long-Term Memory               | ✅      |
| SQLite Persistence             | ✅      |

---

# Implemented Tools

| Tool                   | Description                           |
| ---------------------- | ------------------------------------- |
| `list_projects`        | Fetch projects for authenticated user |
| `list_tasks`           | List project tasks                    |
| `get_task_details`     | Retrieve detailed task info           |
| `create_task`          | Create a new task                     |
| `update_task`          | Update task fields                    |
| `delete_task`          | Delete a task                         |
| `list_project_members` | Show project members                  |
| `get_task_utilisation` | Task distribution summary             |

---

# Long-Term Memory

The assistant supports:

* Session restoration after relogin
* Persistent chat history
* Active project restoration
* Frequently accessed project context

Stored using:

* SQLite database
* Session memory tables
* User preference persistence

Example:

1. User logs in
2. Opens a project
3. Logs out
4. Logs back in
5. Previous session and context are restored

---

# Human-in-the-Loop (HITL)

All write actions require confirmation before execution.

Example:

```text
User:
Create a task called API Integration

Assistant:
I am about to create:

Task Name: API Integration
Project: Website Redesign

Confirm or Cancel?
```

No changes occur until the user confirms.

---

# Supported Conversation Flows

## Query Examples

```text
What projects do I have?
```

```text
Show tasks for the first one
```

```text
Open task TSK-101
```

```text
Who is in this project?
```

```text
Who has the most tasks this month?
```

---

## Action Examples

```text
Create a task called API Integration
```

```text
Mark TSK-101 as completed
```

```text
Assign TSK-101 to Alex Morgan
```

```text
Delete task #3
```

---

# OAuth Setup

## 1. Create Zoho OAuth App

Go to:

* Zoho API Console

Create a:

* Server-based application

Add redirect URI:

```text
http://localhost:8000/auth/callback
```

Copy:

* Client ID
* Client Secret

---

# Environment Variables

Create `.env`

```env
ZOHO_CLIENT_ID=
ZOHO_CLIENT_SECRET=
ZOHO_REDIRECT_URI=http://localhost:8000/auth/callback
ZOHO_ACCOUNTS_URL=https://accounts.zoho.com

DATABASE_URL=sqlite:///./zoho_assistant.db

FRONTEND_URL=http://localhost:3000

ZOHO_USE_MOCK=true
```

---

# Installation

## Backend Setup

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Start backend

```bash
uvicorn app.main:app --reload
```

Backend runs at:

```text
http://localhost:8000
```

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

```text
http://localhost:3000
```

---

# API Endpoints

| Endpoint          | Method | Description              |
| ----------------- | ------ | ------------------------ |
| `/chat`           | POST   | Main chat endpoint       |
| `/auth/login`     | GET    | Start OAuth flow         |
| `/auth/callback`  | GET    | OAuth callback           |
| `/auth/status`    | GET    | Authentication status    |
| `/auth/logout`    | POST   | Logout                   |
| `/memory/restore` | GET    | Restore previous session |

---

# Demo Flow

## Suggested Demo Sequence

### 1. Login

* Continue with Zoho OAuth

### 2. Query Flow

```text
What projects do I have?
```

### 3. Memory Flow

```text
Show tasks for the first one
```

### 4. Action Flow

```text
Create a task called API Integration
```

### 5. HITL Confirmation

* Click Confirm

### 6. Update Flow

```text
Mark TSK-101 as completed
```

### 7. Long-Term Memory

* Logout
* Login again
* Previous chat restored

---

# Testing

Run tests:

```bash
python -m pytest tests/ -v --tb=short
```

Run validation script:

```bash
python scripts/validate_phase2a.py
```

---

# Mock Development Mode

The project supports mock mode for local development.

Enable:

```env
ZOHO_USE_MOCK=true
```

Mock mode provides:

* Demo users
* Sample projects
* Sample tasks
* Offline testing without Zoho API

OAuth login remains the primary authentication method.

---

# Known Limitations

* Analytics/utilisation summaries are partially mock-backed
* SQLite is used for simplicity and local development
* No production deployment configuration included
* No rate limiting implemented
* Mock mode is intended only for development/demo use

---

# Repository Structure

```text
app/
 ├── agents/
 ├── graph/
 ├── memory/
 ├── models/
 ├── routes/
 ├── services/
 ├── tools/
 └── utils/

frontend/
 ├── components/
 ├── lib/
 └── pages/

tests/
scripts/
```

---

# Design Decisions

* LangGraph used for stateful agent orchestration
* SQLite chosen for lightweight persistence
* FastAPI used for async backend architecture
* Query and Action responsibilities strictly separated
* HITL implemented for all write operations
* Long-term memory implemented without external vector databases

---

# Future Improvements

* Better analytics aggregation
* Docker deployment
* Structured logging
* Production-grade database
* Retry middleware for API failures
* WebSocket streaming responses

---

# Author

Built as part of an AI engineering assessment focused on:

* Multi-agent systems
* OAuth integration
* LangGraph workflows
* Conversational interfaces
* Human-in-the-loop AI systems
