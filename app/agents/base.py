from abc import ABC, abstractmethod
from typing import Any

from app.graph.state import GraphState


class BaseAgent(ABC):
    """Shared contract for LangGraph agent nodes."""

    name: str

    @abstractmethod
    async def run(self, state: GraphState) -> dict[str, Any]:
        """Process state and return partial state updates."""
