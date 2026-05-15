# CCCP Chatbot - Project Rules

## Project Context
Multi-agent chatbot for call centre agents and supervisors. Integrated with Microsoft Teams. Deployed on Azure Container Apps.

## Current Deployment
- **Endpoint**: `https://cccp-chatbot.agreeablecliff-8b7135c2.northeurope.azurecontainerapps.io`
- **Health**: `/api/health`
- **Chat**: `POST /api/chat` (SSE streaming)
- **LLM**: Azure OpenAI GPT-5.4 (GlobalStandard, westeurope)
- **Vector DB**: PostgreSQL pgvector (`pg-cccp-pibz5vm5tus3o`, database `cccp`, collection `call_transcripts` + `guidance_docs`)
- **Structured Data**: Same PostgreSQL (tables: `customer_profiles`, `kpi_metrics`, `call_metadata`, `discovered_themes`)
- **ACR Image**: `crcccppibz5vm5tus3o.azurecr.io/cccp-chatbot:latest`

## Architecture
```
MS Teams → Bot Service → FastAPI (Container Apps) → LangGraph:
    ├─ Router (GPT-5.4, classifies intent)
    ├─ Customer Analyst (pgvector transcripts + PG customer data)
    ├─ Theme Discovery (pgvector + PG themes table)
    ├─ Recommendation (PG customer data + mock predictive API)
    ├─ KPI Insights (PG kpi_metrics table)
    ├─ Guidance (pgvector guidance_docs collection)
    ├─ Summary (pgvector transcripts + PG customer data)
    └─ Quality Checker (validates response)
```

## Data Sources (all in PostgreSQL)
- `customer_profiles`: 5 sample customers (Premium/Standard/Enterprise segments)
- `kpi_metrics`: 13 records (NPS, AHT, FCR, CSAT, Call Volume — Milano + Roma)
- `call_metadata`: 7 sample calls with enriched metadata
- `discovered_themes`: 6 themes (billing, internet, AI interest, renewals, security, multi-channel)
- `call_transcripts` (pgvector): RAG collection for transcript chunks
- `guidance_docs` (pgvector): RAG collection for PDF guidance

## Key Design Decisions
- **LangGraph** with Send() fan-out for parallel multi-agent execution
- **PostgreSQL replaces Snowflake** for PoC (same SQL interface, easy swap)
- **Mock predictive API** replaces Databricks microservices (same API contract)
- **No conversation memory yet** (Cosmos DB ready but not wired)
- **Quality checker** uses raw_question (not enriched) for fair evaluation

## CI/CD
- `app/` changes → `deploy-app.yml` (build Docker in ACR → update Container App)
- `indexer/` changes → `index.yml` (run PDF indexing into pgvector)
- All pushes → `ci.yml` (pytest)
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`
- OIDC federated auth (no stored Azure credentials)

## Tech Stack
- Python 3.12, FastAPI, LangGraph, LangChain
- Azure OpenAI GPT-5.4 + text-embedding-3-small
- PostgreSQL Flexible B1ms (pgvector + structured tables)
- Azure Container Apps (consumption, scale to zero)
- GitHub Actions (path-based triggers)
