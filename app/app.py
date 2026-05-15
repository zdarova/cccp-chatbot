"""CCCP Chatbot - FastAPI with SSE streaming via LangGraph."""

import os
import json
import uuid
import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from graph import build_graph
from tracking import log_query

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CCCP Chatbot", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


class ChatRequest(BaseModel):
    query: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_name: str = "Agent"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest):
    def stream():
        msg_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        routes_used = []
        quality_scores = {}
        response_text = ""

        initial_state = {
            "question": req.query,
            "raw_question": req.query,
            "context": "",
            "routes": ["fallback"],
            "route": "fallback",
            "reasoning": "",
            "agent_responses": [],
            "response": "",
            "quality": None,
            "session_id": req.session_id,
            "user_name": req.user_name,
        }

        try:
            for event in _get_graph().stream(initial_state):
                for node_name, node_output in event.items():
                    if node_name == "router":
                        routes = node_output.get("routes", ["fallback"])
                        routes_used = routes
                        yield _sse("routing", {
                            "agents": routes,
                            "reasoning": node_output.get("reasoning", ""),
                            "message_id": msg_id,
                        })
                    elif node_name == "specialist":
                        for ar in node_output.get("agent_responses", []):
                            yield _sse("agent_response", {
                                "agent": ar["agent"],
                                "text": ar["text"],
                            })
                    elif node_name == "merge":
                        response_text = node_output.get("response", "")
                        yield _sse("response", {"text": response_text})
                    elif node_name == "quality_check":
                        quality_scores = node_output.get("quality", {})
                        yield _sse("quality", {"quality": quality_scores})

            yield _sse("done", {"session_id": req.session_id, "message_id": msg_id})

            # Log to MLflow (async-safe, non-blocking)
            latency_ms = (time.perf_counter() - start_time) * 1000
            try:
                import threading
                threading.Thread(target=log_query, args=(
                    req.query, routes_used, len(response_text),
                    quality_scores, latency_ms, req.user_name
                ), daemon=True).start()
            except Exception:
                pass

        except Exception as e:
            logging.error(f"Error: {e}")
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cccp-chatbot"}


@app.get("/api/events/{call_id}")
def get_call_events(call_id: str):
    """Get event timeline for a call (event sourcing read side)."""
    from event_bus import get_event_bus
    bus = get_event_bus()
    return {"call_id": call_id, "events": bus.get_call_events(call_id)}


class SentimentRequest(BaseModel):
    text: str
    call_id: str = "live"


@app.post("/api/sentiment")
async def analyse_sentiment(req: SentimentRequest):
    """Real-time sentiment analysis - Azure AI Language (fast) with GPT fallback."""
    from event_bus import get_event_bus, CallEvent

    bus = get_event_bus()

    # Publish utterance event (triggers reactive agents)
    await bus.publish(CallEvent(
        event_type="utterance.customer",
        call_id=req.call_id,
        data={"text": req.text},
        source_agent="live_mic",
    ))

    # Primary: Azure AI Language (50-100ms)
    result = await _sentiment_azure_language(req.text)
    if result:
        return result

    # Fallback: GPT (1-3s, more nuanced)
    result = await _sentiment_gpt(req.text)
    if result:
        return result

    # Last resort: keyword-based
    return _sentiment_keywords(req.text)


async def _sentiment_azure_language(text: str) -> dict | None:
    """Azure AI Language sentiment analysis (~50ms)."""
    try:
        from azure.ai.textanalytics import TextAnalyticsClient
        from azure.core.credentials import AzureKeyCredential
        import asyncio

        endpoint = os.environ.get("AZURE_LANGUAGE_ENDPOINT", os.environ.get("AZURE_OPENAI_ENDPOINT", ""))
        key = os.environ.get("AZURE_LANGUAGE_KEY", os.environ.get("AZURE_OPENAI_KEY", ""))

        # Use the Speech/Language cognitive services endpoint
        lang_endpoint = os.environ.get("AZURE_LANGUAGE_ENDPOINT", "")
        lang_key = os.environ.get("AZURE_LANGUAGE_KEY", "")

        if not lang_endpoint or not lang_key:
            return None

        client = TextAnalyticsClient(endpoint=lang_endpoint, credential=AzureKeyCredential(lang_key))

        response = await asyncio.to_thread(
            client.analyze_sentiment, [text], language="en"
        )

        doc = response[0]
        if doc.is_error:
            return None

        sentiment = doc.sentiment  # positive, negative, neutral, mixed
        scores = doc.confidence_scores
        score = scores.positive - scores.negative  # -1 to 1

        return {
            "sentiment": sentiment if sentiment != "mixed" else "neutral",
            "score": round(score, 2),
            "emotion": sentiment,
            "confidence": round(max(scores.positive, scores.negative, scores.neutral), 2),
            "source": "azure_language",
        }
    except ImportError:
        logging.debug("azure-ai-textanalytics not installed, skipping")
        return None
    except Exception as e:
        logging.warning(f"Azure Language sentiment failed: {e}")
        return None


async def _sentiment_gpt(text: str) -> dict | None:
    """GPT-based sentiment analysis (1-3s, more nuanced)."""
    try:
        from langchain_openai import AzureChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        import asyncio, re
        import json as _json

        llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
            api_version="2024-06-01",
            temperature=0, max_tokens=80,
        )
        prompt = ChatPromptTemplate.from_template(
            "Analyse sentiment of this call centre utterance.\n"
            "Utterance: {text}\n"
            'Reply ONLY JSON: {{"sentiment": "positive|negative|neutral", "score": <-1.0 to 1.0>, "emotion": "<primary emotion>"}}'
        )
        result = await asyncio.to_thread(
            lambda: (prompt | llm).invoke({"text": text})
        )
        match = re.search(r'\{[^}]+\}', result.content)
        if match:
            parsed = _json.loads(match.group())
            parsed["source"] = "gpt"
            return parsed
    except Exception as e:
        logging.warning(f"GPT sentiment failed: {e}")
    return None


def _sentiment_keywords(text: str) -> dict:
    """Fast keyword-based fallback."""
    text_lower = text.lower()
    neg_words = ["problem", "issue", "terrible", "cancel", "angry", "frustrated", "unacceptable", "worst", "horrible", "ridiculous"]
    pos_words = ["thank", "great", "perfect", "happy", "excellent", "satisfied", "wonderful", "amazing", "love"]
    neg = sum(1 for w in neg_words if w in text_lower)
    pos = sum(1 for w in pos_words if w in text_lower)
    score = (pos - neg) / max(pos + neg, 1)
    sentiment = "negative" if score < -0.2 else "positive" if score > 0.2 else "neutral"
    return {"sentiment": sentiment, "score": round(score, 2), "emotion": "unknown", "source": "keywords"}


@app.get("/api/events/metrics/summary")
def get_event_metrics():
    """Get aggregate event metrics."""
    from event_bus import get_event_bus
    bus = get_event_bus()
    return {"metrics": bus.get_metrics(), "total_events": len(bus._local_log)}


@app.get("/api/architecture")
def architecture():
    return {"diagram": """flowchart TB
    subgraph External[External Systems]
        Genesys[Genesys Call Centre]
        SP[SharePoint - Guidance PDFs]
        Teams[Microsoft Teams]
    end

    subgraph RealTime[Real-Time Processing]
        STT[Azure AI Speech - Real-time STT]
        EH[Event Hubs - call-transcripts]
        RT[Real-Time Agent - Container App]
        WS[WebSocket Copilot]
    end

    subgraph PostCall[Post-Call Analytics]
        Blob[Blob Storage - Recordings]
        ADF[Azure Data Factory]
        Whisper[Azure OpenAI Whisper]
        Enrich[GPT-5.4 Enrichment]
        Cluster[Theme Discovery - HDBSCAN]
    end

    subgraph Chatbot[Multi-Agent Chatbot]
        Bot[Azure Bot Service]
        API[FastAPI - Container App]
        Router[Router Agent]
        CA[Customer Analyst]
        TD[Theme Discovery]
        REC[Recommendation]
        KPI[KPI Insights]
        GD[Guidance Agent]
        SUM[Summary Agent]
        QC[Quality Checker]
    end

    subgraph Data[Data Layer]
        PG[(PostgreSQL pgvector)]
        Cosmos[(Cosmos DB)]
    end

    subgraph AI[AI Services]
        GPT[Azure OpenAI GPT-5.4]
        EMB[text-embedding-3-small]
    end

    subgraph MLOps[LLMOps / Monitoring]
        MLflow[MLflow Tracking]
        Logs[Log Analytics]
    end

    Genesys -->|audio stream| STT
    STT --> EH
    EH --> RT
    RT -->|suggestions| WS
    RT --> GPT
    RT --> PG

    Genesys -->|recordings| Blob
    Blob --> ADF
    ADF --> Whisper
    Whisper --> Enrich
    Enrich --> Cluster
    Enrich --> PG
    Enrich --> GPT

    Teams --> Bot
    Bot --> API
    API --> Router
    Router --> CA
    Router --> TD
    Router --> REC
    Router --> KPI
    Router --> GD
    Router --> SUM
    CA --> QC
    TD --> QC
    REC --> QC
    KPI --> QC
    GD --> QC
    SUM --> QC

    CA --> PG
    TD --> PG
    GD --> PG
    SUM --> PG
    KPI --> PG
    REC --> GPT

    SP -->|indexed| PG
    API --> MLflow
    RT --> MLflow
    MLflow --> PG
"""}


@app.get("/api/recordings")
def list_recordings():
    """List sample recordings and their processing status."""
    try:
        import psycopg
        pg = os.environ.get("PG_CONNECTION_STRING", "")
        if not pg:
            return {"recordings": _sample_recordings()}
        parts = dict(p.split("=", 1) for p in pg.split() if "=" in p)
        conn = psycopg.connect(
            host=parts["host"], port=int(parts["port"]),
            dbname=parts["dbname"], user=parts["user"],
            password=parts["password"], sslmode=parts.get("sslmode", "require"),
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            SELECT call_id, customer_id, agent_id, call_date, duration_seconds,
                   call_centre, summary, tags, sentiment, estimated_nps,
                   agent_quality, resolution_status, commercial_opportunity
            FROM call_metadata ORDER BY call_date DESC
        """)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        recordings = []
        for row in rows:
            r = dict(zip(cols, row))
            r["call_date"] = str(r["call_date"])
            r["processed"] = True
            recordings.append(r)
        conn.close()
        # Add unprocessed sample files
        recordings.extend(_unprocessed_samples())
        return {"recordings": recordings}
    except Exception as e:
        logging.warning(f"Recordings query failed: {e}")
        return {"recordings": _sample_recordings()}


def _unprocessed_samples():
    return [
        {"call_id": "CALL-PENDING-001", "customer_id": "C-1006", "agent_id": "AGT-20",
         "call_date": "2026-05-15 15:30:00", "duration_seconds": 320, "call_centre": "Milano",
         "summary": None, "tags": None, "sentiment": None, "estimated_nps": None,
         "agent_quality": None, "resolution_status": None, "commercial_opportunity": None,
         "processed": False, "filename": "call-pending-001.wav"},
        {"call_id": "CALL-PENDING-002", "customer_id": "C-1007", "agent_id": "AGT-05",
         "call_date": "2026-05-15 16:00:00", "duration_seconds": 450, "call_centre": "Roma",
         "summary": None, "tags": None, "sentiment": None, "estimated_nps": None,
         "agent_quality": None, "resolution_status": None, "commercial_opportunity": None,
         "processed": False, "filename": "call-pending-002.wav"},
    ]


def _sample_recordings():
    return _unprocessed_samples()


# Serve web UI (must be last - catches all unmatched routes)
web_dir = os.path.join(os.path.dirname(__file__), 'web')
if not os.path.exists(web_dir):
    web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
