"""Shared state for the CCCP multi-agent chatbot."""

import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    question: str
    raw_question: str
    context: str
    routes: list[str]
    route: str
    reasoning: str
    agent_responses: Annotated[list[dict], operator.add]
    response: str
    quality: Optional[dict]
    session_id: str
    user_name: str
