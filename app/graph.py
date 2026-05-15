"""LangGraph multi-agent graph with Send fan-out."""

from langgraph.graph import StateGraph, END, START
from langgraph.types import Send
from agents import AgentState
from agents.router import route
from agents.customer_analyst import customer_analyst
from agents.theme_discovery import theme_discovery
from agents.recommendation import recommendation
from agents.kpi_insights import kpi_insights
from agents.guidance import guidance
from agents.summary import summary
from agents.quality_checker import quality_check

SPECIALISTS = {
    "customer_analyst": customer_analyst,
    "theme_discovery": theme_discovery,
    "recommendation": recommendation,
    "kpi_insights": kpi_insights,
    "guidance": guidance,
    "summary": summary,
    "fallback": lambda state: {**state, "response": "Ciao! Sono l'assistente AI del call centre. Come posso aiutarti?"},
}


def after_router(state: AgentState) -> str:
    return "fan_out"


def fan_out_node(state: AgentState):
    routes = state.get("routes", ["fallback"])
    return [Send("specialist", {**state, "route": r, "agent_responses": []}) for r in routes]


def specialist_node(state: AgentState) -> AgentState:
    agent_fn = SPECIALISTS.get(state["route"], SPECIALISTS["fallback"])
    result = agent_fn(state)
    return {
        "agent_responses": [{
            "agent": state["route"],
            "text": result["response"],
        }],
    }


def merge_node(state: AgentState) -> AgentState:
    parts = [ar["text"] for ar in state.get("agent_responses", [])]
    return {"response": "\n\n---\n\n".join(parts)}


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", route)
    g.add_node("fan_out", lambda state: {})
    g.add_node("specialist", specialist_node)
    g.add_node("merge", merge_node)
    g.add_node("quality_check", quality_check)

    g.add_edge(START, "router")
    g.add_edge("router", "fan_out")
    g.add_conditional_edges("fan_out", fan_out_node)
    g.add_edge("specialist", "merge")
    g.add_edge("merge", "quality_check")
    g.add_edge("quality_check", END)

    return g.compile()
