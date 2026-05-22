"""get_task_details routing, access control, and formatted replies."""

import pytest

from app.agents.supervisor import SupervisorAgent
from app.models.requests import ChatRequest
from app.utils.intent import parse_intent
from app.utils.task_intent import is_get_task_details_message


def test_intent_routes_to_query_agent() -> None:
    for msg in (
        "Show details for TSK-101",
        "Open task TSK-101",
        "Task details TSK-101",
    ):
        assert is_get_task_details_message(msg), msg
        intent = parse_intent(msg)
        assert intent.operation == "get_task_details"
        assert intent.params["task_id"] == "TSK-101"
        route = SupervisorAgent()._classify(msg.lower(), {})
        assert route == "query"


@pytest.mark.asyncio
async def test_get_task_details_reply(service) -> None:
    sid = "test-details"
    uid = "mock-jamie"

    r = await service.chat(
        ChatRequest(message="open task TSK-101", session_id=sid, user_id=uid)
    )
    assert r.status == "ok"
    assert r.agent == "query"
    assert "TSK-101" in r.reply
    assert "API Integration" in r.reply
    assert "Status:" in r.reply
    assert r.data and r.data["tool"] == "get_task_details"
    data = r.data["data"]
    assert data["task_id"] == "TSK-101"
    assert data["project_id"] == "PRJ-001"
    assert data["description"]


@pytest.mark.asyncio
async def test_get_task_details_denied_for_other_user(service) -> None:
    sid = "test-details-deny"
    r = await service.chat(
        ChatRequest(message="open task TSK-201", session_id=sid, user_id="mock-jamie")
    )
    assert r.status == "error"
    assert "not found" in r.reply.lower() or "couldn't" in r.reply.lower()


@pytest.mark.asyncio
async def test_utilisation_unchanged(service) -> None:
    r = await service.chat(
        ChatRequest(
            message="Who has the most tasks this month?",
            session_id="util-unchanged",
            user_id="mock-jamie",
        )
    )
    assert r.status == "ok"
    assert r.agent == "query"
    assert r.data and r.data["tool"] == "get_task_utilisation"
