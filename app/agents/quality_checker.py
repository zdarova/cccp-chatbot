"""Quality Checker - validates response quality before returning to user."""

import os
import json
import re
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
            temperature=0, max_tokens=200,
        )
    return _llm


JUDGE_PROMPT = ChatPromptTemplate.from_template(
    "Rate this AI response for a call centre platform (1-5 each):\n"
    "- relevance: addresses the question?\n"
    "- accuracy: factually correct?\n"
    "- actionability: provides clear next steps?\n"
    "- clarity: well-structured?\n\n"
    "Question: {question}\nResponse: {response}\n\n"
    'Reply ONLY JSON: {{"relevance":<1-5>,"accuracy":<1-5>,"actionability":<1-5>,"clarity":<1-5>,"overall":<1-5>}}'
)


def quality_check(state: AgentState) -> AgentState:
    result = (JUDGE_PROMPT | _get_llm()).invoke({
        "question": state.get("raw_question", state["question"])[:300],
        "response": state["response"][:800],
    })
    try:
        scores = json.loads(re.search(r'\{[^}]+\}', result.content).group())
    except Exception:
        scores = {"relevance": 3, "accuracy": 3, "actionability": 3, "clarity": 3, "overall": 3}
    return {**state, "quality": scores}
