"""KPI Insights Agent - NPS evolution, quality metrics, call centre benchmarks."""

import os
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agents import AgentState

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
            api_version="2024-06-01",
            temperature=0.2, max_tokens=2048,
        )
    return _llm


PROMPT = ChatPromptTemplate.from_template(
    "You are a KPI Analyst for a call centre platform. Provide data-driven insights "
    "on service metrics.\n\n"
    "Available metrics data:\n{context}\n\n"
    "Question: {question}\n\n"
    "Provide:\n"
    "1. Metric values and trends (with time periods)\n"
    "2. Comparison vs. benchmarks or targets\n"
    "3. Root cause analysis for significant changes\n"
    "4. Actionable recommendations to improve KPIs\n\n"
    "Respond in the same language as the question."
)


def kpi_insights(state: AgentState) -> AgentState:
    from tools.snowflake_tool import query_kpis

    metrics = query_kpis(state["question"])
    context = f"KPI data:\n{metrics}"

    result = (PROMPT | _get_llm()).invoke({
        "context": context[:4000],
        "question": state["question"][:1500],
    })
    return {**state, "response": result.content}
