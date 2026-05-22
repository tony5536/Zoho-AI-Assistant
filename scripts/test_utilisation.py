"""Utilisation query tests."""
import asyncio
import tempfile
from pathlib import Path

from app.models.requests import ChatRequest
from scripts._helpers import build_test_service
from app.utils.utilisation_intent import detect_utilisation_view, is_utilisation_query


def test_detection() -> None:
    assert is_utilisation_query("Who has the most tasks this month?")
    assert detect_utilisation_view("Who has the most tasks this month?") == "most_tasks"
    assert detect_utilisation_view("Which employee has the highest workload?") == "highest_workload"
    assert detect_utilisation_view("Task distribution summary") == "distribution"
    assert is_utilisation_query("Show task utilisation")
    print("detection: ok")


async def test_queries() -> None:
    db = Path(tempfile.gettempdir()) / "zoho_util_test.db"
    service = await build_test_service(db)
    sid = "util-session"
    uid = "mock-jamie"

    r1 = await service.chat(
        ChatRequest(
            message="Who has the most tasks this month?", session_id=sid, user_id=uid
        )
    )
    assert r1.status == "ok" and "most" in r1.reply.lower()
    assert r1.data and r1.data["tool"] == "get_task_utilisation"
    print("most_tasks:", r1.reply.split("\n")[0])

    r2 = await service.chat(
        ChatRequest(
            message="Which employee has the highest workload?",
            session_id=sid,
            user_id=uid,
        )
    )
    assert r2.status == "ok" and "workload" in r2.reply.lower()
    print("workload:", r2.reply.split("\n")[0])

    r3 = await service.chat(
        ChatRequest(message="Task distribution summary", session_id=sid)
    )
    assert r3.status == "ok" and "distribution" in r3.reply.lower()
    print("distribution:", r3.reply.split("\n")[0])

    r4 = await service.chat(
        ChatRequest(message="Show task utilisation", session_id=sid, user_id=uid)
    )
    assert r4.status == "ok" and "utilisation" in r4.reply.lower()
    print("summary:", r4.reply.split("\n")[0])

    print("All utilisation tests passed.")


if __name__ == "__main__":
    test_detection()
    asyncio.run(test_queries())
