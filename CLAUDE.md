# Macro Research Intelligence Platform

Research module for a macro-data oriented hedge fund. Traders query the system with macro events, positioning data, or indicator readings (e.g., "GS Prime Book shows record shorting — what are the historical precedents?"), and the system produces structured research output that traders use to generate trade ideas.

## What This System Produces

- **Logic chains**: Causal mechanisms extracted from research (e.g., record short positioning → forced covering → squeeze)
- **Historical precedents**: Event studies with quantified outcomes (e.g., "3/4 prior extreme readings led to rally within 1 month")
- **Directional assessments**: Confidence-scored views with risk factors
- **Gap-filled context**: Web search, data fetching, and image analysis to fill missing information

## Pipeline

```
Trader query
    → Database Retriever (RAG: query expansion → vector search → synthesis → gap detection/filling)
    → Variable Mapper (logic chains → structured data queries)
    → Data Collection (fetch market data from FRED/Yahoo/CoinGecko to validate claims)
    → Risk Intelligence (multi-asset directional assessment with confidence)
    → Structured output for trader consumption
```

## Subprojects

| Subproject | Purpose |
|------------|---------|
| `database_manager` | Ingests macro research from Telegram, extracts logic chains, stores in Pinecone |
| `database_retriever` | Agentic RAG pipeline with gap detection and filling |
| `variable_mapper` | Translates logic chains into structured data queries |
| `data_collection` | Fetches market data to validate research claims |
| `risk_intelligence` | Consumes enriched context → directional assessment (multi-asset: BTC, equity) |

## Tech Stack

Python, LangGraph, Pinecone, Claude/OpenAI APIs, Yahoo Finance, FRED API, Tavily

## Archive Folder

The `archive/` folder contains resolved evaluation documents and historical analysis files.

**DO NOT read files from the archive folder unless specifically requested by the user.**

Contents include:
- `EVALUATION_RESPONSE.md` - Original issue tracking document (resolved)
- `EVALUATION_SUBPROJECT1_DATABASE_MANAGER.md` - Database Manager evaluation (all issues fixed)
- `EVALUATION_SUBPROJECT2_DATABASE_RETRIEVER.md` - Database Retriever evaluation (high priority issues fixed)
- `EVALUATION_SUBPROJECT3_VARIABLE_MAPPER.md` - Variable Mapper evaluation (high priority issues fixed)
- `PLAN_*.md` - Historical implementation plans (completed)
- `STATUS_*.md` - Archived session histories from each subproject
- `README_database_manager.md` - Archived Database Manager README (content in CLAUDE.md)
