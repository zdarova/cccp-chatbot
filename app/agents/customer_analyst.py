"""Customer Analyst Agent - sentiment trends, interaction history, customer profile."""

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
    "You are a Customer Analyst for a call centre platform. Analyze customer sentiment "
    "trends and interaction history.\n\n"
    "Available data:\n{context}\n\n"
    "Question: {question}\n\n"
    "Provide:\n"
    "1. Sentiment trend analysis (improving/declining/stable)\n"
    "2. Key interaction patterns\n"
    "3. Risk indicators (churn signals, dissatisfaction patterns)\n"
    "4. Actionable insights for the agent/supervisor\n\n"
    "Respond in the same language as the question."
)


def customer_analyst(state: AgentState) -> AgentState:
    from tools.pgvector_tool import search_transcripts
    from tools.snowflake_tool import get_customer_profile

    # Retrieve relevant transcripts and customer data
    transcripts = search_transcripts(state["question"], k=5)
    customer_data = get_customer_profile(state["question"])

    context = f"Call transcripts:\n{transcripts}\n\nCustomer data:\n{customer_data}"

    result = (PROMPT | _get_llm()).invoke({
        "context": context[:4000],
        "question": state["question"][:1500],
    })
    return {**state, "response": result.content}
