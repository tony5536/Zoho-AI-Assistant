"""Task title extraction and list formatting tests."""
from app.models.tool_models import TaskSummary
from app.utils.task_format import format_task_block, format_task_list
from app.utils.task_intent import extract_task_name, is_confirmation_message


def test_title_extraction() -> None:
    assert extract_task_name("Create a task called API Integration") == "API Integration"
    assert extract_task_name("create task called API Integration") == "API Integration"
    assert extract_task_name("Create a task called API Integration in PRJ-001") == "API Integration"
    assert extract_task_name("Create a task called API Integration.") == "API Integration"
    assert extract_task_name("Create a task called API Integration") != "Create a task called API Integration"
    print("title extraction: ok")


def test_confirmation_phrases() -> None:
    assert is_confirmation_message("confirm")
    assert is_confirmation_message("Confirmed")
    assert not is_confirmation_message("delete task TSK-101")
    print("confirmation phrases: ok")


def test_task_format() -> None:
    task = TaskSummary(
        task_id="TSK-101",
        project_id="PRJ-001",
        name="API Integration",
        status="open",
        assignee="Jamie Lee",
        hours_logged=0.0,
        hours_estimated=8.0,
        due_date="2026-05-28",
        priority="high",
    )
    block = format_task_block(task)
    assert "TSK-101 — API Integration" in block
    assert "Status: Open" in block
    assert "Assignee: Jamie Lee" in block
    assert "Due Date: 2026-05-28" in block
    assert "Priority: High" in block
    listing = format_task_list([task], header="Tasks in Website Redesign")
    assert "Tasks in Website Redesign" in listing
    print("task format: ok")


if __name__ == "__main__":
    test_title_extraction()
    test_confirmation_phrases()
    test_task_format()
    print("All task format tests passed.")
