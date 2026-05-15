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
