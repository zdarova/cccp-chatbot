"""Theme Discovery Agent - emerging patterns and topic analysis in calls."""

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
    "You are a Theme Discovery analyst for a call centre. Identify emerging patterns "
    "and key topics from call data.\n\n"
    "Available data:\n{context}\n\n"
    "Question: {question}\n\n"
    "Provide:\n"
    "1. Top emerging themes (new topics not previously tracked)\n"
    "2. Theme frequency and trend (increasing/decreasing)\n"
    "3. Correlation with sentiment (which themes drive negative/positive sentiment)\n"
    "4. Recommendations for guidance updates based on new themes\n\n"
    "Respond in the same language as the question."
)


def theme_discovery(state: AgentState) -> AgentState:
    from tools.pgvector_tool import search_transcripts
    from tools.snowflake_tool import get_themes

    transcripts = search_transcripts(state["question"], k=8)
    themes = get_themes()
    context = f"Recent call transcripts:\n{transcripts}\n\nKnown themes:\n{themes}"

    result = (PROMPT | _get_llm()).invoke({
        "context": context[:4000],
        "question": state["question"][:1500],
    })
    return {**state, "response": result.content}
