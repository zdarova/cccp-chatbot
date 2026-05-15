"""Router - classifies user intent and selects agents."""

import os
import json
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agents import AgentState

_llm = None

VALID_ROUTES = {"customer_analyst", "theme_discovery", "recommendation", "kpi_insights", "guidance", "summary", "fallback"}


def _get_llm():
    global _llm
    if _llm is None:
        _llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
            api_version="2024-06-01",
            temperature=0, max_tokens=150,
        )
    return _llm


ROUTER_PROMPT = ChatPromptTemplate.from_template(
    "Classify this user question for a call centre AI platform. Select 1-3 agents.\n\n"
    "Available agents:\n"
    "- customer_analyst: sentiment trends, interaction history, customer profile\n"
    "- theme_discovery: emerging themes, topic patterns in calls\n"
    "- recommendation: product/service suggestions, cross-sell/upsell\n"
    "- kpi_insights: NPS evolution, quality metrics, call centre benchmarks\n"
    "- guidance: technical guidance, product manuals, how-to instructions, vehicle procedures, troubleshooting, best practices\n"
    "- summary: summarize customer interactions over time\n"
    "- fallback: ONLY for greetings like 'hello' or completely unrelated topics\n\n"
    "IMPORTANT: If the question asks 'how to' do something, mentions a product/vehicle, or asks about a procedure, ALWAYS route to 'guidance'.\n\n"
    "EXAMPLES:\n"
    "- 'How do I remove the front bumper on a Mazda CX-5?' -> [\"guidance\"]\n"
    "- 'What is the DPF regeneration procedure?' -> [\"guidance\"]\n"
    "- 'Summarize interactions with customer X' -> [\"summary\"]\n"
    "- 'How is the NPS trending?' -> [\"kpi_insights\"]\n"
    "- 'Analyze sentiment and suggest actions' -> [\"customer_analyst\", \"recommendation\"]\n"
    "- 'What new themes are emerging?' -> [\"theme_discovery\"]\n"
    "- 'Hello' -> [\"fallback\"]\n\n"
    "Question: {question}\n"
    'Reply ONLY with JSON: {{"routes": ["agent1"], "reasoning": "<one sentence>"}}'
)


def route(state: AgentState) -> AgentState:
    result = (ROUTER_PROMPT | _get_llm()).invoke({"question": state["question"][:500]})
    raw = result.content.strip()

    try:
        parsed = json.loads(raw)
        routes = parsed.get("routes", ["fallback"])
        reasoning = parsed.get("reasoning", "")
        if isinstance(routes, str):
            routes = [routes]
    except Exception:
        routes = ["fallback"]
        reasoning = ""

    routes = [r for r in routes if r in VALID_ROUTES][:3]
    if not routes:
        routes = ["fallback"]

    return {**state, "routes": routes, "route": routes[0], "reasoning": reasoning}
