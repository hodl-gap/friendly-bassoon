# Macro Research Intelligence Platform

Research module for a macro-data oriented hedge fund. Traders query the system with macro events, positioning data, or indicator readings (e.g., "GS Prime Book shows record shorting — what are the historical precedents?"), and the system produces structured research output that traders use to generate trade ideas.

## What This System Produces

- **Logic chains**: Causal mechanisms extracted from research (e.g., record short positioning → forced covering → squeeze)
- **Historical precedents**: Event studies with quantified outcomes (e.g., "3/4 prior extreme readings led to rally within 1 month")
- **Directional assessments**: Confidence-scored views with risk factors
- **Gap-filled context**: Web search, data fetching, and image analysis to fill missing information
- **Proactive monitoring**: Theme-organized chain tracking, variable frequency analysis, and daily regime briefings

## Pipeline

```
Trader query
    → Database Retriever (RAG: query expansion → vector search → synthesis → gap detection/filling → persist learning)
    → Variable Mapper (logic chains → structured data queries)
    → Data Collection (fetch market data from FRED/Yahoo/CoinGecko to validate claims)
    → Risk Intelligence (theme-based chain loading → multi-asset directional assessment with macro regime context)
    → Structured output for trader consumption

Daily monitoring (cron)
    → Theme Refresh (per-theme anchor variable monitoring → active chain detection → regime assessment)
    → Morning Briefing (template-based summary of all theme states)
```

## Subprojects

| Subproject | Purpose |
|------------|---------|
| `database_manager` | Ingests macro research from Telegram, extracts logic chains, stores in Pinecone |
| `database_retriever` | Agentic RAG pipeline with gap detection, filling, and web chain persistence (L1 learning) |
| `variable_mapper` | Translates logic chains into structured data queries |
| `data_collection` | Fetches market data to validate research claims |
| `risk_intelligence` | Theme-based chain loading → multi-asset directional assessment with macro regime context |

## Shared Module (`shared/`)

| File | Purpose |
|------|---------|
| `schemas.py` | Canonical types: `LogicChainStep`, `LogicChain`, `ConfidenceMetadata` |
| `model_config.py` | Central model selection for all subprojects |
| `run_logger.py` | Pipeline run logger with LLM cost tracking |
| `snapshot.py` | State capture for debugging |
| `variable_resolver.py` | Variable → data source lookup (anchor variables → discovered IDs → Yahoo fallback) |
| `theme_config.py` | 6 macro themes with anchor variables and query templates |
| `theme_index.py` | Theme-organized chain index (assigns chains to themes via variable intersection) |
| `variable_frequency.py` | Tracks variable appearance frequency across chains; promotion/demotion candidates |
| `data/anchor_variables.json` | 25 curated anchor variables with verified data source mappings |

## Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `daily_regime_scan.py` | Daily monitoring: refreshes all themes, generates morning briefing |
| `backfill_theme_index.py` | One-time: indexes existing chains into theme structure |
| `backfill_variable_frequency.py` | One-time: builds variable frequency data from existing chains |

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
