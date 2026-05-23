"""Supervisor routes reads to QueryAgent and writes to ActionAgent."""

from app.agents.supervisor import SupervisorAgent, is_write_operation_message
from app.utils.utilisation_intent import is_utilisation_query


def test_read_prompts_stay_query() -> None:
    supervisor = SupervisorAgent()
    reads = (
        "list projects",
        "show tasks for PRJ-001",
        "open task TSK-101",
        "who has the most tasks this month?",
        "show changed tasks",
        "marking trends in the backlog",
        "set of tasks in the sprint",
        "change in utilisation this quarter",
        "task details for TSK-101",
    )
    for msg in reads:
        lower = msg.lower()
        assert supervisor._classify(lower, {}) == "query", msg
        assert not is_write_operation_message(lower), msg


def test_write_prompts_go_action() -> None:
    supervisor = SupervisorAgent()
    writes = (
        "update task TSK-101 status to completed",
        "assign TSK-101 to Alex Morgan",
        "change status of TSK-102 to open",
        "delete task TSK-103",
        "create task called Demo",
        "mark task completed",
        "update that task status to completed",
        "delete this task",
    )
    for msg in writes:
        lower = msg.lower()
        assert is_write_operation_message(lower), msg
        assert supervisor._classify(lower, {}) == "action", msg


def test_ambiguous_prompts_safe_query() -> None:
    supervisor = SupervisorAgent()
    ambiguous = (
        "change",
        "mark",
        "set",
        "what changed yesterday",
        "assigned reading list",
    )
    for msg in ambiguous:
        lower = msg.lower()
        assert supervisor._classify(lower, {}) == "query", msg


def test_utilisation_stays_query() -> None:
    msgs = (
        "show utilisation for PRJ-001",
        "who has the highest workload this month?",
        "task utilisation summary",
    )
    for msg in msgs:
        assert is_utilisation_query(msg)
        assert SupervisorAgent()._classify(msg.lower(), {}) == "query"
