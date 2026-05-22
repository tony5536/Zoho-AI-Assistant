from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.action_agent import ActionAgent
from app.agents.query_agent import QueryAgent
from app.agents.supervisor import SupervisorAgent
from app.graph.state import GraphState, Route
from app.memory.manager import MemoryManager
from app.tools.zoho_tools import ZohoTools


class AssistantWorkflow:
    """Compiles and runs the LangGraph supervisor → agent pipeline."""

    def __init__(
        self,
        tools: ZohoTools,
        memory: MemoryManager,
        supervisor: SupervisorAgent | None = None,
        query_agent: QueryAgent | None = None,
        action_agent: ActionAgent | None = None,
    ) -> None:
        self._supervisor = supervisor or SupervisorAgent()
        self._query_agent = query_agent or QueryAgent(tools, memory)
        self._action_agent = action_agent or ActionAgent(tools, memory)
        self._graph = build_workflow(
            self._supervisor,
            self._query_agent,
            self._action_agent,
        )

    async def invoke(self, state: GraphState) -> GraphState:
        result: dict[str, Any] = await self._graph.ainvoke(state)
        return result  # type: ignore[return-value]


def _route_after_supervisor(state: GraphState) -> Route:
    return state.get("route", "query")


def build_workflow(
    supervisor: SupervisorAgent,
    query_agent: QueryAgent,
    action_agent: ActionAgent,
):
    graph = StateGraph(GraphState)

    async def supervisor_node(state: GraphState) -> dict[str, Any]:
        return await supervisor.run(state)

    async def query_node(state: GraphState) -> dict[str, Any]:
        return await query_agent.run(state)

    async def action_node(state: GraphState) -> dict[str, Any]:
        return await action_agent.run(state)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("query", query_node)
    graph.add_node("action", action_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"query": "query", "action": "action"},
    )
    graph.add_edge("query", END)
    graph.add_edge("action", END)

    return graph.compile()
