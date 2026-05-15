"""Guidance Agent - RAG over agent guidance PDFs, best practice retrieval."""

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
    "You are a Guidance Assistant for call centre agents. Answer based on the official "
    "guidance documents provided.\n\n"
    "Guidance context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Provide:\n"
    "1. Recommended actions based on guidance\n"
    "2. Relevant guidance excerpts\n"
    "3. If guidance doesn't cover this scenario, flag it as a gap\n\n"
    "Respond in the same language as the question."
)


def guidance(state: AgentState) -> AgentState:
    from tools.pgvector_tool import search_guidance

    docs = search_guidance(state["question"], k=4)
    context = f"Guidance documents:\n{docs}"

    result = (PROMPT | _get_llm()).invoke({
        "context": context[:4000],
        "question": state["question"][:1500],
    })
    return {**state, "response": result.content}
