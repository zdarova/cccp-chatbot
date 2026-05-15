"""CCCP Chatbot - FastAPI with SSE streaming via LangGraph."""

import os
import json
import uuid
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from graph import build_graph

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
                        yield _sse("response", {"text": node_output.get("response", "")})
                    elif node_name == "quality_check":
                        yield _sse("quality", {"quality": node_output.get("quality", {})})

            yield _sse("done", {"session_id": req.session_id, "message_id": msg_id})

        except Exception as e:
            logging.error(f"Error: {e}")
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cccp-chatbot"}


# Serve web UI (must be last - catches all unmatched routes)
web_dir = os.path.join(os.path.dirname(__file__), 'web')
if not os.path.exists(web_dir):
    web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
