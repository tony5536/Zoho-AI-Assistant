from typing import Any, Literal

from pydantic import BaseModel, Field

ToolName = Literal[
    "list_projects",
    "list_tasks",
    "get_task_details",
    "list_project_members",
    "create_task",
    "update_task",
    "delete_task",
    "get_task_utilisation",
]


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    status: str
    owner: str


class TaskSummary(BaseModel):
    task_id: str
    project_id: str
    name: str
    status: str
    assignee: str
    hours_logged: float
    hours_estimated: float
    due_date: str | None = None
    priority: str | None = None


class TaskDetails(TaskSummary):
    description: str = ""
    created_time: str | None = None


class ProjectMember(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    role: str | None = None


class ListProjectMembersResult(BaseModel):
    project_id: str
    members: list[ProjectMember]
    count: int


class TaskUtilisation(BaseModel):
    task_id: str
    project_id: str
    name: str
    hours_logged: float
    hours_estimated: float
    utilisation_percent: float


class AssigneeWorkload(BaseModel):
    assignee: str
    task_count: int
    hours_logged: float
    hours_estimated: float
    avg_utilisation_percent: float


class TaskUtilisationRow(BaseModel):
    task_id: str
    project_id: str
    name: str
    assignee: str
    hours_logged: float
    hours_estimated: float
    utilisation_percent: float


class UtilisationSummary(BaseModel):
    view: str
    scope: str
    project_id: str | None = None
    project_name: str | None = None
    period_label: str = "this month"
    total_tasks: int
    total_hours_logged: float
    total_hours_estimated: float
    by_assignee: list[AssigneeWorkload]
    top_by_tasks: str | None = None
    top_by_workload: str | None = None
    tasks: list[TaskUtilisationRow]


class ListProjectsResult(BaseModel):
    projects: list[ProjectSummary]
    count: int


class ListTasksResult(BaseModel):
    project_id: str
    tasks: list[TaskSummary]
    count: int


class TaskMutationResult(BaseModel):
    success: bool
    task: TaskSummary | None = None
    message: str


class DeleteTaskResult(BaseModel):
    success: bool
    task_id: str
    message: str


class ToolError(BaseModel):
    code: str
    message: str


class ToolResponse(BaseModel):
    tool: ToolName
    success: bool
    data: (
        ListProjectsResult
        | ListTasksResult
        | ListProjectMembersResult
        | TaskSummary
        | TaskDetails
        | TaskMutationResult
        | DeleteTaskResult
        | TaskUtilisation
        | UtilisationSummary
        | None
    ) = None
    error: ToolError | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.tool,
            "success": self.success,
        }
        if self.data is not None:
            payload["data"] = self.data.model_dump()
        if self.error is not None:
            payload["error"] = self.error.model_dump()
        return payload


class ProjectContext(BaseModel):
    project_id: str
    project_name: str


class RecentProject(BaseModel):
    """Project entry from the most recent list_projects result (ordered)."""

    project_id: str
    name: str
    position: int = Field(description="1-based index shown to the user")


class PendingAction(BaseModel):
    action_id: str
    tool: Literal["create_task", "update_task", "delete_task"]
    summary: str
    payload: dict[str, Any]
