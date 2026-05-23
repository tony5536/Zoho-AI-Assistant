import re
from typing import Any, Literal

from app.agents.base import BaseAgent
from app.graph.state import GraphState
from app.utils.utilisation_intent import is_utilisation_query

Route = Literal["query", "action"]

_ACTION_VERB_PATTERNS: tuple[str, ...] = (
    r"\bcreate\b",
    r"\badd\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bremove\b",
    r"\bmodify\b",
    r"\bchange\b",
    r"\bmark\b",
    r"\bassign\b",
    r"\bset\s+due\b",
    r"\bset\s+priority\b",
    r"\bset\s+status\b",
)

_TASK_OBJECT_CUE_PATTERNS: tuple[str, ...] = (
    r"\btask\b",
    r"\bTSK-\d+\b",
    r"\bstatus\b",
    r"\bpriority\b",
    r"\bdue\s+date\b",
    r"\bassignee\b",
    r"\bassign\s+it\b",
    r"\b(?:this|that|the|current)\s+task\b",
)

_READ_EXCLUSIONS: tuple[str, ...] = (
    r"\bshow\s+changed\b",
    r"\bchanged\s+tasks\b",
    r"\bmarking\s+trends\b",
    r"\bset\s+of\s+tasks\b",
    r"\bchange\s+in\s+utili[sz]ation\b",
    r"\blist\s+tasks\b",
    r"\bshow\s+tasks\b",
)


def is_write_operation_message(message: str) -> bool:
    """True when the message is a task write: requires an action verb and a task/object cue."""
    lower = message.lower()
    if is_utilisation_query(message):
        return False
    if any(re.search(pattern, lower) for pattern in _READ_EXCLUSIONS):
        return False
    if re.search(r"\bset\s+of\b", lower):
        return False
    has_verb = any(re.search(pattern, lower) for pattern in _ACTION_VERB_PATTERNS)
    has_cue = any(re.search(pattern, message, re.IGNORECASE) for pattern in _TASK_OBJECT_CUE_PATTERNS)
    return has_verb and has_cue


class SupervisorAgent(BaseAgent):
    """Router node: query vs action, including confirmation follow-ups."""

    name = "supervisor"

    async def run(self, state: GraphState) -> dict[str, Any]:
        message = state["user_message"].lower()
        route: Route = self._classify(message, state)
        return {"route": route}

    def _classify(self, message: str, state: GraphState) -> Route:
        if state.get("confirm"):
            return "action"

        stripped = message.strip().lower()
        if stripped in (
            "yes",
            "confirm",
            "confirmed",
            "approve",
            "approved",
            "proceed",
            "ok",
            "okay",
        ):
            return "action"

        if is_utilisation_query(message):
            return "query"

        if is_write_operation_message(message):
            return "action"
        return "query"
