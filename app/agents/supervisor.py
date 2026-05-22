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

        action_keywords = (
            "create",
            "add",
            "update",
            "delete",
            "remove",
            "modify",
            "change",
        )
        if any(word in message for word in action_keywords):
            return "action"
        return "query"
