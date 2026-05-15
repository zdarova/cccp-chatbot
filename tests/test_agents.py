"""Tests for the CCCP multi-agent chatbot."""

import pytest
from unittest.mock import patch, MagicMock
from agents import AgentState
from agents.router import VALID_ROUTES


def _mock_env():
    return patch.dict("os.environ", {
        "AZURE_OPENAI_ENDPOINT": "https://test",
        "AZURE_OPENAI_KEY": "test",
        "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-4o",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
        "PG_CONNECTION_STRING": "host=localhost port=5432 dbname=test user=test password=test sslmode=require",
    })


def _base_state(**overrides) -> AgentState:
    return {
        "question": "test", "raw_question": "test", "context": "",
        "routes": ["fallback"], "route": "fallback", "reasoning": "",
        "agent_responses": [], "response": "", "quality": None,
        "session_id": "test-session", "user_name": "Test User",
        **overrides,
    }


def _fake_llm(content: str):
    from langchain_core.runnables import RunnableLambda
    return RunnableLambda(lambda x: MagicMock(content=content))


# --- State ---

def test_state_keys():
    expected = {"question", "raw_question", "context", "routes", "route",
                "reasoning", "agent_responses", "response", "quality",
                "session_id", "user_name"}
    assert set(_base_state().keys()) == expected


def test_valid_routes():
    assert VALID_ROUTES == {"customer_analyst", "theme_discovery", "recommendation",
                            "kpi_insights", "guidance", "summary", "fallback"}


# --- Router ---

@pytest.mark.parametrize("category", list(VALID_ROUTES))
def test_router_accepts_all_valid_routes(category):
    fake = _fake_llm('{"routes": ["' + category + '"], "reasoning": "test"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state())
        assert result["routes"] == [category]


def test_router_defaults_invalid_to_fallback():
    fake = _fake_llm('{"routes": ["garbage"], "reasoning": "x"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state())
        assert result["routes"] == ["fallback"]


def test_router_multi_route():
    fake = _fake_llm('{"routes": ["customer_analyst", "recommendation"], "reasoning": "needs both"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state())
        assert result["routes"] == ["customer_analyst", "recommendation"]


# --- Graph ---

def test_graph_builds():
    with _mock_env():
        from graph import build_graph
        assert build_graph() is not None


# --- Specialists ---

def test_customer_analyst():
    with patch("agents.customer_analyst._get_llm", return_value=_fake_llm("Sentiment declining")):
        with patch("tools.pgvector_tool.search_transcripts", return_value="transcript data"):
            with patch("tools.snowflake_tool.get_customer_profile", return_value="customer data"):
                from agents.customer_analyst import customer_analyst
                result = customer_analyst(_base_state(question="Analizza cliente X"))
                assert result["response"] == "Sentiment declining"


def test_guidance():
    with patch("agents.guidance._get_llm", return_value=_fake_llm("Follow step 3 of guidance")):
        with patch("tools.pgvector_tool.search_guidance_with_metadata", return_value={"text": "guidance text", "images": []}):
            from agents.guidance import guidance
            result = guidance(_base_state(question="Cosa fare se cliente lamenta?"))
            assert "Follow step 3 of guidance" in result["response"]


def test_kpi_insights():
    with patch("agents.kpi_insights._get_llm", return_value=_fake_llm("NPS is 42")):
        with patch("tools.snowflake_tool.query_kpis", return_value="NPS: 42"):
            from agents.kpi_insights import kpi_insights
            result = kpi_insights(_base_state(question="Come va l'NPS?"))
            assert result["response"] == "NPS is 42"


def test_quality_checker():
    fake = _fake_llm('{"relevance": 5, "accuracy": 4, "actionability": 4, "clarity": 5, "overall": 4}')
    with patch("agents.quality_checker._get_llm", return_value=fake):
        from agents.quality_checker import quality_check
        result = quality_check(_base_state(response="test response"))
        assert result["quality"]["overall"] == 4


# --- Merge ---

def test_merge_single():
    with _mock_env():
        from graph import merge_node
        state = _base_state(agent_responses=[{"agent": "guidance", "text": "Answer"}])
        result = merge_node(state)
        assert result["response"] == "Answer"


def test_merge_multiple():
    with _mock_env():
        from graph import merge_node
        state = _base_state(agent_responses=[
            {"agent": "customer_analyst", "text": "Analysis"},
            {"agent": "recommendation", "text": "Suggest product X"},
        ])
        result = merge_node(state)
        assert "Analysis" in result["response"]
        assert "Suggest product X" in result["response"]
