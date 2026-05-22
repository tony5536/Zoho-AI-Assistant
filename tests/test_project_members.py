"""list_project_members routing, context resolution, and formatting."""

import pytest

from app.agents.supervisor import SupervisorAgent
from app.models.requests import ChatRequest
from app.utils.intent import parse_intent
from app.utils.task_intent import is_list_project_members_message


def test_members_intent() -> None:
    for msg in (
        "Who are the members of PRJ-001?",
        "List project members",
        "show team for the first project",
    ):
        assert is_list_project_members_message(msg), msg
        assert parse_intent(msg).operation == "list_project_members"
        route = SupervisorAgent()._classify(msg.lower(), {})
        assert route == "query"


@pytest.mark.asyncio
async def test_members_with_project_context(service) -> None:
    sid = "test-members"
    uid = "mock-jamie"

    await service.chat(
        ChatRequest(message="list projects", session_id=sid, user_id=uid)
    )
    await service.chat(
        ChatRequest(
            message="Show tasks for the first one",
            session_id=sid,
            user_id=uid,
        )
    )
    r = await service.chat(
        ChatRequest(
            message="Show team for the first project",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r.status == "ok"
    assert r.agent == "query"
    assert r.data and r.data["tool"] == "list_project_members"
    assert "Alex Morgan" in r.reply or "Jamie Lee" in r.reply


@pytest.mark.asyncio
async def test_members_explicit_project(service) -> None:
    r = await service.chat(
        ChatRequest(
            message="Who are the members of PRJ-001?",
            session_id="members-prj",
            user_id="mock-jamie",
        )
    )
    assert r.status == "ok"
    assert "PRJ-001" in r.reply
    assert "Jamie Lee" in r.reply or "Alex Morgan" in r.reply
