"""Summary Agent - summarize customer interactions over time periods."""

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
            temperature=0.3, max_tokens=2048,
        )
    return _llm


PROMPT = ChatPromptTemplate.from_template(
    "You are a Summarization specialist for a call centre. Create concise, actionable "
    "summaries of customer interactions.\n\n"
    "Interaction data:\n{context}\n\n"
    "Question: {question}\n\n"
    "Provide a structured summary with:\n"
    "1. Overview (2-3 sentences)\n"
    "2. Key topics discussed\n"
    "3. Customer sentiment progression\n"
    "4. Unresolved issues\n"
    "5. Recommended next actions\n\n"
    "Respond in the same language as the question."
)


def summary(state: AgentState) -> AgentState:
    from tools.pgvector_tool import search_transcripts
    from tools.snowflake_tool import get_customer_profile

    transcripts = search_transcripts(state["question"], k=8)
    customer_data = get_customer_profile(state["question"])
    context = f"Transcripts:\n{transcripts}\n\nCustomer info:\n{customer_data}"

    result = (PROMPT | _get_llm()).invoke({
        "context": context[:5000],
        "question": state["question"][:1500],
    })
    return {**state, "response": result.content}
