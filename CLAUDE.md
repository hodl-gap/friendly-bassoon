# Macro Research Intelligence Platform

## Goal

Build an autonomous version of Bridgewater's research team. Bridgewater separates research from trading: the research team looks at data, patterns, news — everything — to develop **insights**. Traders then look at insights to develop **trade ideas**. This project focuses solely on the research team: producing insights, NOT trade ideas.

An insight is a multi-track causal understanding grounded in historical evidence. For example:
- Track A: War imminent (news) → 17 wars since 17th century show stock market up after war (historical pattern) → war bullish equities
- Track B: War imminent (news) → government prints money (macro intuition from research DB) → money printing hits market within 3 months (historical precedent timing) → liquidity long-term bullish for risk assets

The system should eventually be fully proactive (continuously monitoring and surfacing insights without human queries), asset-mapped (insights map to specific asset classes), and draw on deep historical precedents. The current implementation starts with query-driven research and overall risk asset coverage as stepping stones toward that goal.

## Data Source: Telegram as IB Research Proxy

The primary (and currently only) ingestion source is Telegram channels run by IB analysts who share gated analysis reports from investment banks (Goldman Sachs, BofA, Morgan Stanley, etc.). This is a practical workaround for not having direct access to IB research terminals. The content is institutional-grade macro research — the same reports that drive Wall Street analysis. The ingestion pipeline (`database_manager`) is source-agnostic: if direct IB report access becomes available, it only requires adding a new adapter.

## What This System Produces

Research module for a macro-data oriented hedge fund. Traders query the system with macro events, positioning data, or indicator readings (e.g., "GS Prime Book shows record shorting — what are the historical precedents?"), and the system produces structured research output that traders use to generate trade ideas.

## What This System Produces

- **Logic chains**: Causal mechanisms extracted from research (e.g., record short positioning → forced covering → squeeze)
- **Historical precedents**: Event studies with quantified outcomes (e.g., "3/4 prior extreme readings led to rally within 1 month")
- **Directional assessments**: Confidence-scored views with risk factors
- **Gap-filled context**: Web search, data fetching, and image analysis to fill missing information
- **Proactive monitoring**: Theme-organized chain tracking, variable frequency analysis, and daily regime briefings

## Pipeline

### Default (Sequential)
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

### Hybrid Agentic Pipeline (Tested 2026-02-24)

**Status: Tested on Cases 1, 2, 4. Consistent +3 rubric improvement over baseline (Case 1: 8→11/13, Case 2: 11→14/18, Case 4: 16→19/20). Three integration bugs found and fixed (commit b2151d1).**

When enabled via `--hybrid` flag or individual env vars, key phases become agentic (iterative ReAct loops via `shared/agent_loop.py`). The old sequential pipeline remains intact and is the default. All changes are feature-flagged.

```
Trader query
    → PHASE 1: RETRIEVAL AGENT (agentic, iterate until coverage adequate)
        Tools: search_pinecone, extract_web_chains, web_search, generate_synthesis, assess_coverage, finish_retrieval
        Flag: AGENT_RETRIEVAL=true
    → PHASE 2: DATA GROUNDING AGENT (agentic, adaptive depth)
        Tools: extract_variables, fetch_variable_data, validate_claim, validate_patterns, compute_derived, finish_grounding
        Flag: AGENT_DATA_GROUNDING=true
    → PHASE 3: HISTORICAL CONTEXT AGENT (agentic, adaptive analog count)
        Tools: detect_analogs, fetch_analog_data, aggregate_analogs, characterize_regime, load_theme_chains, fetch_additional_data, finish_historical
        Flag: AGENT_HISTORICAL=true
    → PHASE 4: SYNTHESIS (Opus generate + Sonnet self-check + optional patch)
        Flag: AGENT_SYNTHESIS_CHECK=true
    → Structured output for trader consumption
```

**Feature Flags** (`shared/feature_flags.py`):
| Flag | Default | Purpose |
|------|---------|---------|
| `USE_HYBRID_PIPELINE` | false | Master override — enables all agentic phases |
| `AGENT_RETRIEVAL` | false | Phase 1: agentic retrieval with coverage checker |
| `AGENT_DATA_GROUNDING` | false | Phase 2: agentic data grounding |
| `AGENT_HISTORICAL` | false | Phase 3: agentic historical context |
| `AGENT_SYNTHESIS_CHECK` | false | Phase 4: synthesis self-verification |
| `RETRIEVAL_MAX_ITER` | 5 | Max iterations for retrieval agent |
| `DATA_GROUNDING_MAX_ITER` | 4 | Max iterations for data grounding agent |
| `HISTORICAL_MAX_ITER` | 4 | Max iterations for historical context agent |

**CLI Usage**:
```bash
# Enable all agentic phases
python run_case_study.py --case 4 --run 1 --hybrid
python -m subproject_risk_intelligence --hybrid "query"

# Enable individual phases
AGENT_RETRIEVAL=true python run_case_study.py --case 4 --run 1
AGENT_SYNTHESIS_CHECK=true python run_case_study.py --case 5 --run 1
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
| `agent_loop.py` | Generic ReAct loop runner for agentic phases (detect tool_use → execute handler → append result → loop) |
| `feature_flags.py` | Centralized feature flags for hybrid pipeline (env var functions, not constants) |

## Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `daily_regime_scan.py` | Daily monitoring: refreshes all themes, generates morning briefing |
| `backfill_theme_index.py` | One-time: indexes existing chains into theme structure |
| `backfill_variable_frequency.py` | One-time: builds variable frequency data from existing chains |

## Tech Stack

Python, LangGraph, Pinecone, Claude/OpenAI APIs, Yahoo Finance, FRED API, Tavily

## Code Design Standards

1. **Main file = orchestration only** — no business logic in orchestrator files; they wire components together
2. **Prompts in separate files** — all LLM prompts live in `*_prompts.py` files, not inline
3. **AI calls via parent's `models.py`** — centralized LLM call functions, not direct API calls in subprojects
4. **Simple sequential workflow** — plain Python with ThreadPoolExecutor for parallelism, not LangGraph
   - *Accepted deviation*: `database_retriever`, `data_collection`, and `variable_mapper` use LangGraph StateGraph. These are stable working pipelines where replacement is high-risk for no functional gain.
5. **Dual-mode output** — always maintain both insight and belief_space paths
6. **Follow established patterns** — new subprojects mirror existing ones in structure and conventions
7. **Do not overcomplicate** — keep it minimal and focused

## Known Issues

### 1. Categorization Drops Institutional Research (FIXED 2026-02-20)

**Problem**: The `categorization_prompts.py` LLM categorizer misclassified forwarded institutional research (e.g., `[GS]` tagged analysis about hyperscaler CAPEX) as `event_announcement` instead of `data_opinion`. Since only `data_opinion` and `interview_meeting` get extracted and embedded, critical research content was silently dropped from the pipeline.

**Root cause**: The `event_announcement` description ("Company events, seminars, promotional content") was vague enough that the LLM stretched "promotional content" to include forwarded research notes with institutional tags.

**Fix applied**: Added clarifying notes to both `event_announcement` ("forwarded institutional research is NOT event_announcement") and `data_opinion` ("forwarded/summarized institutional research tagged [GS], [BofA], [JPM] etc. WITH interpretation is data_opinion").

**Impact**: The GS analysis about AI hyperscaler CAPEX revisions, FCF pressure, and Mag7 underperformance was lost. After fix, it's correctly categorized and extracted.

### 2. Cross-Language Retrieval Gap (OPEN)

**Problem**: Korean-language chunks in Pinecone don't get retrieved by English-language queries even when semantically relevant. Example: a Korean GS research summary about "AI Hyperscaler 기업들의 Capex 추정치" (AI Hyperscaler CAPEX estimates) has low cosine similarity with English queries like "SaaS meltdown February 2026."

**Impact**: Even after fixing categorization and embedding the CAPEX chunk, the retriever didn't pull it because the connection (CAPEX concern → tech valuation pressure → SaaS selloff) requires multi-hop reasoning, not just embedding similarity.

**Potential fix**: TBD — chain tension detection was attempted but doesn't help here because the CAPEX overspending narrative is entirely absent from retrieved chains (tension detection requires both sides to already be present).

## TODO

- [ ] Ingest wider date range from globaletfi (Jan 27 - Feb 10) for earnings season coverage
- [ ] Ingest additional Telegram channels for broader sell-side research coverage
- [ ] Evaluate whether extracted metadata (English) should be concatenated with raw text (Korean) before embedding to improve cross-language retrieval
- [x] Add condensed summary output alongside the full insight report. Generated mechanically from structured track data in `format_insight()` — no extra LLM call. Appended after the full report.
- [x] Add chain completeness (Rule 8) and regime-shift consideration (Rule 9) to resynthesis prompt. Rewrite web chain angle #3 for alternative interpretations. Validated: Case 4 16→18/20, Case 6 12→14/16.
- [x] **TEST hybrid agentic pipeline** — Tested Cases 1, 2, 4 with `--hybrid`. Results: +3 across all cases. Three bugs fixed: dict key mismatch in web chain handler, agent prompt too weak (kept searching after ADEQUATE), synthesis patch overwriting good output with empty result. (Added 2026-02-23, tested 2026-02-24)

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
