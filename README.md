# CCCP - Multi-Agent Chatbot

Interactive AI tool for call centre agents and supervisors, integrated with Microsoft Teams.

## What it does

```
User (Teams) → Azure Bot Service → Multi-Agent Orchestrator:
    ├─ Customer Analyst Agent (sentiment trends, interaction history)
    ├─ Theme Discovery Agent (key topics, emerging patterns)
    ├─ Recommendation Agent (products/services based on history + predictive models)
    ├─ KPI Insights Agent (NPS evolution, quality metrics, benchmarks)
    ├─ Guidance Agent (RAG over PDF guidance, best practices)
    └─ Summary Agent (customer interaction summaries)
```

## Agents

| Agent | Description |
|-------|-------------|
| Customer Analyst | Sentiment trends, interaction history, customer profile |
| Theme Discovery | Key themes in communications, emerging patterns |
| Recommendation | Product/service suggestions from historical data + predictive microservices |
| KPI Insights | NPS evolution, quality metrics, call centre benchmarks |
| Guidance | RAG over agent guidance PDFs, best practice retrieval |
| Summary | Summarize customer interactions over time periods |
| Router | Classifies intent, dispatches to appropriate agent(s) |

## Architecture

```
┌──────────┐     ┌───────────────┐     ┌─────────────────────────┐
│ MS Teams │────▶│ Bot Service   │────▶│ Container Apps          │
└──────────┘     └───────────────┘     │  (FastAPI + LangGraph)  │
                                        └────────────┬────────────┘
                                                     │
                    ┌────────────────────────────────┼────────────┐
                    │                                ▼            │
                    │  ┌─────────┐  ┌──────────┐  ┌──────────┐  │
                    │  │ AI      │  │ Snowflake│  │ Predictive│  │
                    │  │ Search  │  │ (customer│  │ Models    │  │
                    │  │ (RAG)   │  │  data)   │  │ (Databricks)│ │
                    │  └─────────┘  └──────────┘  └──────────┘  │
                    │         TOOL LAYER                          │
                    └────────────────────────────────────────────┘
```

## Example Queries

- "Riassumi le interazioni con il cliente X nell'ultimo anno"
- "Quali azioni intraprendere se un cliente lamenta costi elevati?"
- "Come è evoluto l'NPS medio mensile nei call centre?"
- "Quali nuovi temi emergono dalle chiamate di questa settimana?"
- "Suggerisci prodotti per clienti con sentiment negativo ricorrente"

## Run Locally

```bash
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_KEY="<key>"
export AZURE_AI_SEARCH_ENDPOINT="https://..."
export AZURE_AI_SEARCH_KEY="<key>"
export SNOWFLAKE_CONNECTION="<connection_string>"
export COSMOS_ENDPOINT="https://..."
export COSMOS_KEY="<key>"

pip install -r requirements.txt
uvicorn app:app --reload --port 8002
```

## Tests

```bash
python -m pytest tests/ -v
```

## Related Repos

- **cccp-platform-infra** — Bicep IaC for all Azure resources
- **cccp-realtime-agent** — Real-time call processing
- **cccp-post-call-analytics** — Batch pipeline for recordings
