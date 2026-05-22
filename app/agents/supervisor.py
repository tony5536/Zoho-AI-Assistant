import re
from typing import Any, Literal

from app.agents.base import BaseAgent
from app.graph.state import GraphState
from app.utils.utilisation_intent import is_utilisation_query

Route = Literal["query", "action"]


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

        if self._is_action_message(message):
            return "action"
        return "query"

    def _is_action_message(self, message: str) -> bool:
        """Word-boundary action cues so reads like 'assigned' stay on the query path."""
        patterns = (
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
            r"\bdue\s+date\b",
        )
        return any(re.search(pattern, message) for pattern in patterns)
