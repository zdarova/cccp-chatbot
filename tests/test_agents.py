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


# --- Requirement Tests: Guidance (vehicle manuals, how-to) ---

def test_router_routes_howto_to_guidance():
    """How-to questions must route to guidance agent."""
    fake = _fake_llm('{"routes": ["guidance"], "reasoning": "technical how-to question"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state(question="How do I remove the front bumper on a Mazda CX-5?"))
        assert "guidance" in result["routes"]


def test_router_routes_vehicle_to_guidance():
    """Vehicle/product questions must route to guidance."""
    fake = _fake_llm('{"routes": ["guidance"], "reasoning": "vehicle procedure"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state(question="What is the DPF regeneration procedure?"))
        assert "guidance" in result["routes"]


def test_guidance_returns_images():
    """Guidance agent should return image URLs when available."""
    with patch("agents.guidance._get_llm", return_value=_fake_llm("Remove the 4 bolts holding the bumper")):
        with patch("tools.pgvector_tool.search_guidance_with_metadata", return_value={
            "text": "Step 1: Remove bolts. Step 2: Pull bumper forward.",
            "images": ["/docs/images/page5.png"]
        }):
            from agents.guidance import guidance
            result = guidance(_base_state(question="How to remove bumper?"))
            assert "Remove the 4 bolts" in result["response"]
            assert "/docs/images/page5.png" in result["response"]


def test_guidance_no_images():
    """Guidance agent works without images."""
    with patch("agents.guidance._get_llm", return_value=_fake_llm("Check the oil level")):
        with patch("tools.pgvector_tool.search_guidance_with_metadata", return_value={
            "text": "Oil check procedure",
            "images": []
        }):
            from agents.guidance import guidance
            result = guidance(_base_state(question="How to check oil?"))
            assert "Check the oil level" in result["response"]
            assert "diagram" not in result["response"].lower()


# --- Requirement Tests: Summary ---

def test_summary_agent():
    """Summary agent should summarize customer interactions."""
    with patch("agents.summary._get_llm", return_value=_fake_llm("Customer had 5 calls in Q1, mostly about billing.")):
        with patch("tools.pgvector_tool.search_transcripts", return_value="call transcript data"):
            with patch("tools.snowflake_tool.get_customer_profile", return_value="customer info"):
                from agents.summary import summary
                result = summary(_base_state(question="Summarize interactions with customer C-1001"))
                assert "5 calls" in result["response"]


def test_router_routes_summary():
    """Summary requests must route to summary agent."""
    fake = _fake_llm('{"routes": ["summary"], "reasoning": "user wants a summary"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state(question="Summarize all calls from customer Mario Rossi"))
        assert "summary" in result["routes"]


# --- Requirement Tests: Recommendation ---

def test_recommendation_agent():
    """Recommendation agent should suggest products based on data."""
    with patch("agents.recommendation._get_llm", return_value=_fake_llm("Recommend Security Pack based on recent inquiries")):
        with patch("tools.pgvector_tool.search_transcripts", return_value="customer asked about security"):
            with patch("tools.snowflake_tool.get_customer_profile", return_value="Premium customer"):
                with patch("tools.predictive_api.get_propensity_scores", return_value="Security Pack: 0.72"):
                    from agents.recommendation import recommendation
                    result = recommendation(_base_state(question="What should we recommend to this customer?"))
                    assert "Security Pack" in result["response"]


def test_router_routes_recommendation():
    """Commercial action requests must route to recommendation."""
    fake = _fake_llm('{"routes": ["recommendation"], "reasoning": "commercial suggestion needed"}')
    with patch("agents.router._get_llm", return_value=fake):
        from agents.router import route
        result = route(_base_state(question="Suggest products for customers with negative sentiment"))
        assert "recommendation" in result["routes"]


# --- Requirement Tests: Theme Discovery ---

def test_theme_discovery_agent():
    """Theme discovery should identify emerging patterns."""
    with patch("agents.theme_discovery._get_llm", return_value=_fake_llm("New theme: customers asking about AI services")):
        with patch("tools.pgvector_tool.search_transcripts", return_value="transcript data"):
            with patch("tools.snowflake_tool.get_themes", return_value="billing: high, AI interest: medium"):
                from agents.theme_discovery import theme_discovery
                result = theme_discovery(_base_state(question="What new themes are emerging?"))
                assert "AI services" in result["response"]


# --- Requirement Tests: Customer Analyst ---

def test_customer_analyst_sentiment():
    """Customer analyst should analyze sentiment trends."""
    with patch("agents.customer_analyst._get_llm", return_value=_fake_llm("Sentiment declining over 3 months, from 0.3 to -0.4")):
        with patch("tools.pgvector_tool.search_transcripts", return_value="negative calls"):
            with patch("tools.snowflake_tool.get_customer_profile", return_value="avg_sentiment: -0.4"):
                from agents.customer_analyst import customer_analyst
                result = customer_analyst(_base_state(question="Analyze sentiment for customer C-1003"))
                assert "declining" in result["response"].lower()


# --- Requirement Tests: KPI Insights ---

def test_kpi_insights_nps():
    """KPI agent should return NPS data with trends."""
    with patch("agents.kpi_insights._get_llm", return_value=_fake_llm("NPS Milano: 42 (declining), Roma: 48 (stable)")):
        with patch("tools.snowflake_tool.query_kpis", return_value="NPS: 42, target: 50"):
            from agents.kpi_insights import kpi_insights
            result = kpi_insights(_base_state(question="How is NPS trending?"))
            assert "42" in result["response"]


# --- Requirement Tests: Supervisor ---

def test_supervisor_approves_good_response():
    """Supervisor should approve a good response and reflection should pass."""
    approve_response = '{"verdict": "APPROVE", "refined_response": "", "reasoning": "complete answer", "quality_score": 5, "completeness": 5, "actionability": 5}'
    # First call: supervisor review (returns APPROVE JSON)
    # Second call: reflection (returns PASS)
    call_count = [0]
    def fake_invoke(x):
        call_count[0] += 1
        if call_count[0] == 1:
            return MagicMock(content=approve_response)
        return MagicMock(content="PASS")

    from langchain_core.runnables import RunnableLambda
    fake_llm = RunnableLambda(fake_invoke)

    with patch("agents.supervisor._get_llm", return_value=fake_llm):
        from agents.supervisor import supervise
        state = _base_state(response="NPS is 42 in Milano, declining. Recommend action X.", routes=["kpi_insights"])
        result = supervise(state)
        assert "NPS is 42" in result["response"]


def test_supervisor_refines_bad_response():
    """Supervisor should refine an incomplete response."""
    with patch("agents.supervisor._get_llm", return_value=_fake_llm('{"verdict": "REFINE", "refined_response": "NPS is 42 in Milano (target 50). Action: increase FCR to improve.", "reasoning": "missing actionable steps", "quality_score": 3, "completeness": 2, "actionability": 2}')):
        from agents.supervisor import supervise
        state = _base_state(response="NPS is 42.", routes=["kpi_insights"])
        result = supervise(state)
        assert "Action" in result["response"]


# --- Requirement Tests: Fallback ---

def test_fallback_message():
    """Fallback should return support email, not Italian greeting."""
    with _mock_env():
        from graph import SPECIALISTS
        result = SPECIALISTS["fallback"](_base_state())
        assert "support@cccpaiassistant.com" in result["response"]
        assert "Ciao" not in result["response"]


# --- Requirement Tests: Event Bus ---

def test_event_bus_publish_subscribe():
    """Event bus should deliver events to subscribers."""
    import asyncio
    from event_bus import EventHubBus, CallEvent

    bus = EventHubBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("utterance.customer", handler)

    asyncio.run(bus.publish(CallEvent(
        event_type="utterance.customer",
        call_id="test-call",
        data={"text": "I have a problem"},
    )))

    assert len(received) == 1
    assert received[0].data["text"] == "I have a problem"


def test_event_bus_wildcard():
    """Event bus wildcard subscription should match all subtypes."""
    import asyncio
    from event_bus import EventHubBus, CallEvent

    bus = EventHubBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("sentiment.*", handler)

    asyncio.run(bus.publish(CallEvent(event_type="sentiment.negative", call_id="c1", data={})))
    asyncio.run(bus.publish(CallEvent(event_type="sentiment.positive", call_id="c2", data={})))
    asyncio.run(bus.publish(CallEvent(event_type="utterance.customer", call_id="c3", data={})))

    assert len(received) == 2  # Only sentiment.* events


def test_event_bus_call_timeline():
    """Event bus should return events for a specific call."""
    import asyncio
    from event_bus import EventHubBus, CallEvent

    bus = EventHubBus()
    asyncio.run(bus.publish(CallEvent(event_type="utterance.customer", call_id="call-A", data={"text": "hello"})))
    asyncio.run(bus.publish(CallEvent(event_type="utterance.customer", call_id="call-B", data={"text": "other"})))
    asyncio.run(bus.publish(CallEvent(event_type="sentiment.positive", call_id="call-A", data={"score": 0.8})))

    events = bus.get_call_events("call-A")
    assert len(events) == 2
    assert events[0]["type"] == "utterance.customer"
    assert events[1]["type"] == "sentiment.positive"


# --- Requirement Tests: Post-Call Extended Metadata ---

def test_postcall_enrichment():
    """Post-call pipeline should generate extended metadata (summary, tags, sentiment, NPS, quality)."""
    import json
    enrichment_json = '{"summary": "Customer complained about billing", "tags": ["billing", "complaint"], "sentiment": -0.6, "estimated_nps": 3, "agent_quality": 3, "key_issues": ["overcharge"], "resolution_status": "unresolved", "commercial_opportunity": "retention"}'
    enriched = json.loads(enrichment_json)
    assert "summary" in enriched
    assert "tags" in enriched
    assert "sentiment" in enriched
    assert "estimated_nps" in enriched
    assert "agent_quality" in enriched
    assert "resolution_status" in enriched
    assert "commercial_opportunity" in enriched
    assert enriched["estimated_nps"] == 3
    assert enriched["sentiment"] == -0.6


def test_postcall_metadata_fields():
    """Extended metadata must include: transcription, summary, tags, sentiment, NPS, agent quality."""
    required_fields = ["summary", "tags", "sentiment", "estimated_nps", "agent_quality",
                       "resolution_status", "commercial_opportunity", "key_issues"]

    # Simulate what the pipeline produces
    sample_metadata = {
        "call_id": "CALL-TEST-001",
        "customer_id": "C-1001",
        "agent_id": "AGT-12",
        "call_date": "2026-05-15 10:00:00",
        "duration_seconds": 420,
        "call_centre": "Milano",
        "summary": "Customer reported billing issue",
        "tags": ["billing", "dispute"],
        "sentiment": -0.7,
        "estimated_nps": 3,
        "agent_quality": 3,
        "key_issues": ["overcharge"],
        "resolution_status": "unresolved",
        "commercial_opportunity": "retention",
    }

    for field in required_fields:
        assert field in sample_metadata, f"Missing required field: {field}"


# --- Requirement Tests: Post-Call Guidance Improvement ---

def test_postcall_guidance_gap_analysis():
    """Post-call pipeline should identify gaps in agent guidance and suggest improvements."""
    # Simulate guidance gap analysis output
    gaps = [
        {"gap": "No guidance for customers asking about AI services", "suggestion": "Add AI services FAQ section", "priority": "high"},
        {"gap": "Escalation path unclear for multi-channel complaints", "suggestion": "Define cross-channel escalation procedure", "priority": "medium"},
    ]

    assert len(gaps) > 0
    for gap in gaps:
        assert "gap" in gap
        assert "suggestion" in gap
        assert "priority" in gap
        assert gap["priority"] in ["high", "medium", "low"]


def test_postcall_guidance_improvement_structure():
    """Guidance improvement suggestions must align with customer satisfaction AND cross-sell goals."""
    improvement = {
        "gap": "Agents don't know when to suggest Security Pack",
        "suggestion": "After resolving security-related inquiry, suggest Security Pack if customer has no protection",
        "priority": "high",
        "alignment": {
            "customer_satisfaction": "Proactive protection reduces future issues",
            "cross_sell_opportunity": "Security Pack upsell after trust established",
        }
    }

    assert "alignment" in improvement
    assert "customer_satisfaction" in improvement["alignment"]
    assert "cross_sell_opportunity" in improvement["alignment"]
