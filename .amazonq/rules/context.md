# CCCP Chatbot - Project Rules

## Project Context
This repo implements the **multi-agent interactive chatbot** for call centre agents and supervisors. Integrated with Microsoft Teams, it answers queries about customers, themes, KPIs, and provides actionable recommendations.

## Architecture
```
MS Teams → Azure Bot Service → FastAPI (Container Apps) → LangGraph Multi-Agent:
    ├─ Router (classifies intent, selects 1-3 agents)
    ├─ Customer Analyst Agent (sentiment trends, interaction history)
    ├─ Theme Discovery Agent (emerging patterns, topic analysis)
    ├─ Recommendation Agent (products/services via predictive microservices)
    ├─ KPI Insights Agent (NPS, quality metrics, benchmarks from Snowflake)
    ├─ Guidance Agent (RAG over PDF guidance from pgvector)
    ├─ Summary Agent (customer interaction summaries)
    └─ Quality Checker (validates response quality)
```

## Key Design Decisions
- **LangGraph** for multi-agent orchestration (same pattern as proven Ricoh AI project)
- **Send() fan-out** for parallel agent execution on multi-intent queries
- **pgvector (PostgreSQL)** for RAG over call transcripts and guidance documents
- **Snowflake** for structured queries (KPIs, customer data, call metadata)
- **Predictive microservices** (Databricks-served) for product recommendations
- **Cosmos DB** for conversation memory and session state
- **Azure Bot Service** for Teams channel integration
- **FastAPI + SSE** for streaming responses

## Agent Details

### Router
- Classifies user intent into 1-3 agents
- Uses GPT-4o with few-shot examples
- Routes: customer_analyst, theme_discovery, recommendation, kpi_insights, guidance, summary, fallback

### Customer Analyst Agent
- Tools: query pgvector (call transcripts), query Snowflake (customer profile)
- Capabilities: sentiment trends over time, interaction history, customer health score
- Example: "Riassumi le interazioni con cliente X nell'ultimo anno"

### Theme Discovery Agent
- Tools: query pgvector (recent call embeddings), clustering results from post-call pipeline
- Capabilities: emerging themes, topic frequency, novel patterns
- Example: "Quali nuovi temi emergono dalle chiamate di questa settimana?"

### Recommendation Agent
- Tools: Snowflake (customer data), predictive microservices (cross-sell/upsell models)
- Capabilities: product suggestions based on history + propensity scores
- Generates natural language explanations for recommendations
- Example: "Suggerisci prodotti per clienti con sentiment negativo ricorrente"

### KPI Insights Agent
- Tools: Snowflake (aggregated metrics), time-series queries
- Capabilities: NPS evolution, quality scores, call centre benchmarks, trend analysis
- Example: "Come è evoluto l'NPS medio mensile nei call centre?"

### Guidance Agent
- Tools: pgvector RAG (PDF guidance documents indexed from SharePoint)
- Capabilities: best practice retrieval, action recommendations
- Example: "Cosa fare se un cliente lamenta costi elevati del servizio?"

### Summary Agent
- Tools: pgvector (transcripts), Snowflake (metadata)
- Capabilities: multi-call summaries, period-based overviews
- Example: "Riassumi tutte le chiamate del cliente Y nel Q1"

## Tech Stack
- Python 3.12, FastAPI, LangGraph, LangChain
- Azure OpenAI GPT-4o (LLM) + text-embedding-3-small (embeddings)
- pgvector (PostgreSQL Flexible B1ms) for RAG
- Snowflake connector for structured data queries
- Cosmos DB (serverless) for conversation memory
- Azure Bot Service + Bot Framework SDK for Teams
- Deployed on Azure Container Apps (consumption, scale to zero)

## Multi-Agent Patterns
- Router sees raw user question (not enriched) for accurate classification
- Agents execute in parallel via Send() fan-out when multi-intent detected
- Each agent has access to specific tools (not all tools)
- Responses merged and quality-checked before returning to user
- Conversation memory persisted per user for context continuity

## Example Multi-Agent Queries
- "Analizza il sentiment del cliente X e suggerisci azioni" → customer_analyst + recommendation
- "Come sta andando l'NPS e quali temi emergono?" → kpi_insights + theme_discovery
- "Cosa dice la guida su clienti insoddisfatti e riassumi le loro chiamate" → guidance + summary
