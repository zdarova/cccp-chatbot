"""Recommendation Agent - product/service suggestions based on history + predictive models.

This is the primary deliverable for point 8 of the challenge:
- Analyse customer sentiment trends
- Identify key themes in communications
- Recommend products/services based on historical data and predictive microservices
- Generate natural language outputs explaining recommendations
"""

import os
import json
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
            temperature=0.3, max_tokens=4096,
        )
    return _llm


PROMPT = ChatPromptTemplate.from_template(
    "You are a Commercial Recommendation engine for a call centre platform.\n\n"
    "TASK: Based on customer history, sentiment analysis, identified themes, and "
    "predictive model scores, recommend products/services and explain WHY.\n\n"
    "Customer context:\n{customer_context}\n\n"
    "Sentiment analysis:\n{sentiment}\n\n"
    "Key themes from recent calls:\n{themes}\n\n"
    "Predictive model scores:\n{predictions}\n\n"
    "Question: {question}\n\n"
    "Provide:\n"
    "1. **Recommended actions** (ranked by priority)\n"
    "2. **Product/service suggestions** with propensity scores\n"
    "3. **Natural language explanation** of WHY each recommendation fits this customer\n"
    "4. **Timing recommendation** (immediate action vs. next contact)\n"
    "5. **Risk assessment** (probability of negative reaction)\n\n"
    "Respond in the same language as the question."
)


def recommendation(state: AgentState) -> AgentState:
    from tools.pgvector_tool import search_transcripts
    from tools.snowflake_tool import get_customer_profile
    from tools.predictive_api import get_propensity_scores

    # 1. Get customer interaction history from pgvector
    transcripts = search_transcripts(state["question"], k=5)

    # 2. Get customer profile from Snowflake
    customer_data = get_customer_profile(state["question"])

    # 3. Analyse sentiment from recent interactions
    sentiment = _analyse_sentiment(transcripts)

    # 4. Identify key themes
    themes = _extract_themes(transcripts)

    # 5. Get predictive model scores (cross-sell/upsell propensity)
    predictions = get_propensity_scores(state["question"])

    result = (PROMPT | _get_llm()).invoke({
        "customer_context": customer_data[:1500],
        "sentiment": sentiment[:500],
        "themes": themes[:500],
        "predictions": predictions[:500],
        "question": state["question"][:1500],
    })
    return {**state, "response": result.content}


def _analyse_sentiment(transcripts: str) -> str:
    """Quick sentiment extraction from transcript context."""
    if not transcripts:
        return "No sentiment data available"
    # Use LLM for nuanced sentiment
    prompt = ChatPromptTemplate.from_template(
        "Analyse the overall sentiment from these call transcripts. "
        "Return: overall_sentiment (positive/negative/neutral), trend, key drivers.\n\n"
        "Transcripts:\n{text}\n\n"
        "Reply as brief JSON: {{\"sentiment\": \"...\", \"trend\": \"...\", \"drivers\": [...]}}"
    )
    try:
        result = (prompt | _get_llm()).invoke({"text": transcripts[:2000]})
        return result.content
    except Exception:
        return "Sentiment analysis unavailable"


def _extract_themes(transcripts: str) -> str:
    """Extract key themes from transcripts."""
    if not transcripts:
        return "No themes available"
    prompt = ChatPromptTemplate.from_template(
        "Extract the top 5 key themes from these call transcripts.\n\n"
        "Transcripts:\n{text}\n\n"
        "Reply as JSON array: [{{\"theme\": \"...\", \"frequency\": \"high/medium/low\", \"sentiment_impact\": \"positive/negative/neutral\"}}]"
    )
    try:
        result = (prompt | _get_llm()).invoke({"text": transcripts[:2000]})
        return result.content
    except Exception:
        return "Theme extraction unavailable"
