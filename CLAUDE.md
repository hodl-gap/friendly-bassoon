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

```
Trader query
    → PHASE 1: RETRIEVAL AGENT (agentic, iterate until coverage adequate)
        Tools: search_pinecone, extract_web_chains, web_search, generate_synthesis, assess_coverage, finish_retrieval
    → PHASE 2: DATA GROUNDING AGENT (agentic, adaptive depth)
        Tools: extract_variables, fetch_variable_data, validate_claim, validate_patterns, compute_derived, finish_grounding
    → PHASE 3: HISTORICAL CONTEXT AGENT (agentic, adaptive analog count)
        Tools: detect_analogs, fetch_analog_data, aggregate_analogs, characterize_regime, load_theme_chains, fetch_additional_data, finish_historical
    → PHASE 4: SYNTHESIS (Opus generate + Sonnet self-check + optional patch)
    → Structured insight output for trader consumption

Daily monitoring (cron)
    → Theme Refresh (per-theme anchor variable monitoring → active chain detection → regime assessment)
    → Morning Briefing (template-based summary of all theme states)
```

**Iteration Limits** (`shared/feature_flags.py`):
| Setting | Default | Purpose |
|---------|---------|---------|
| `RETRIEVAL_MAX_ITER` | 5 | Max iterations for retrieval agent |
| `DATA_GROUNDING_MAX_ITER` | 4 | Max iterations for data grounding agent |
| `HISTORICAL_MAX_ITER` | 4 | Max iterations for historical context agent |

**CLI Usage**:
```bash
python run_case_study.py --case 4 --run 1
python -m subproject_risk_intelligence --asset equity "What caused the SaaS meltdown?"
python -m subproject_risk_intelligence --asset btc,equity "Fed just cut rates 50bps"
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
| `feature_flags.py` | Agentic pipeline iteration limits (configurable via env vars) |

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
4. **Agentic pipeline** — ReAct loops via `shared/agent_loop.py` for retrieval, data grounding, historical context, and synthesis
   - *Accepted deviation*: `data_collection` and `variable_mapper` use LangGraph StateGraph. These are stable working pipelines where replacement is high-risk for no functional gain.
5. **Follow established patterns** — new subprojects mirror existing ones in structure and conventions
6. **Do not overcomplicate** — keep it minimal and focused

## Known Issues

### 1. Categorization Drops Institutional Research (FIXED 2026-02-20)

**Problem**: The `categorization_prompts.py` LLM categorizer misclassified forwarded institutional research (e.g., `[GS]` tagged analysis about hyperscaler CAPEX) as `event_announcement` instead of `data_opinion`. Since only `data_opinion` and `interview_meeting` get extracted and embedded, critical research content was silently dropped from the pipeline.

**Root cause**: The `event_announcement` description ("Company events, seminars, promotional content") was vague enough that the LLM stretched "promotional content" to include forwarded research notes with institutional tags.

**Fix applied**: Added clarifying notes to both `event_announcement` ("forwarded institutional research is NOT event_announcement") and `data_opinion` ("forwarded/summarized institutional research tagged [GS], [BofA], [JPM] etc. WITH interpretation is data_opinion").

**Impact**: The GS analysis about AI hyperscaler CAPEX revisions, FCF pressure, and Mag7 underperformance was lost. After fix, it's correctly categorized and extracted.

### 2. Hyperscaler CAPEX: Retrieval Agent Query Coverage Gap (OPEN)

**Problem**: The pipeline fails to build a "CAPEX overspending → value destruction" track for Case 1 SaaS meltdown, despite the bearish CAPEX interpretation existing in Pinecone.

**Root cause**: The retrieval agent's 5 Pinecone queries were all SaaS/software-focused. None targeted CAPEX overspending. The bearish CAPEX chunk (Telegram #18329, 하나/GS, 2026-02-01, vector ID `8dacc3908d3d239b_0`) contains the exact framing needed (FCF pressure, ROI concerns, Mag7 underperformance) but was never queried for. Coverage assessor rated `ADEQUATE` without identifying CAPEX as a gap.

**Previous misdiagnoses** (3 iterations): cross-language retrieval → Tavily query formulation → bearish interpretation absent from source material. All wrong — the chunk is ingested, correctly categorized (`data_opinion`), extracted with bearish logic chains, and embedded in Pinecone.

**Why**: CAPEX overspending is a second-order amplifier (AI disruption → SaaS selloff → CAPEX fear compounds it). Initial queries naturally target the trigger, but the agent should search for compounding factors after initial retrieval.

**Fix**: Retrieval agent prompt + coverage assessor. See `TODO_TEMPORAL_SENSITIVITY.md` §3 for full details.

## Feedback Loops (Self-Learning Status)

Running the pipeline repeatedly improves future analysis through these persistence mechanisms:

| Mechanism | File | Writes To | Read Back By | Compounds? |
|-----------|------|-----------|-------------|------------|
| **Web chain → Pinecone** | `database_retriever/web_chain_persistence.py` | Pinecone vector DB | Retriever (vector search) | **Yes — primary learning loop** |
| **Chain store → relationships.json** | `risk_intelligence/relationship_store.py` | `data/relationships.json` | `load_chains()`, `get_relevant_historical_chains()` | **Yes, weakly** (local only, not RAG-searchable) |
| **Variable frequency tracking** | `shared/variable_frequency.py` | `data/variable_frequency.json` | Daily theme scan, relationship_store | Marginal |
| **Regime state persistence** | `relationship_store.py` | `data/*_regime_state.json` | Next pipeline run (baseline context) | Marginal |
| **Auto-discover variable IDs** | `variable_mapper/data_id_discovery.py` | `mappings/discovered_data_ids.json` | Variable resolver | One-shot (not compounding) |

**Web chain persistence** is the only mechanism that expands the RAG retrieval corpus. When the retriever fills knowledge gaps via web search, extracted causal chains are embedded and upserted to Pinecone. Future queries on related topics benefit from these chains. Diverse queries compound — running the same query twice does not.

**Relationship store** accumulates chains locally with semantic dedup (Jaccard similarity). Similar chains get `validation_count += 1` and blended confidence. These feed into the "macro regime context" section of the insight prompt, but are not searchable via the RAG retriever.

## TODO

- [ ] Ingest wider date range from globaletfi (Jan 27 - Feb 10) for earnings season coverage
- [ ] Ingest additional Telegram channels for broader sell-side research coverage
- [ ] Evaluate whether extracted metadata (English) should be concatenated with raw text (Korean) before embedding — low priority, CAPEX gap is about missing bearish interpretation in source material, not retrieval (see Known Issue #2)
- [ ] **Implement true feedback loops** — The pipeline currently has weak self-learning (web chains to Pinecone, local chain accumulation). Need closed-loop mechanisms where pipeline outputs feed back to improve future pipeline inputs: scoring past predictions against actual outcomes, promoting validated local chains into the RAG corpus, and using downstream usage signals to improve upstream retrieval quality.
- [x] Add condensed summary output alongside the full insight report. Generated mechanically from structured track data in `format_insight()` — no extra LLM call. Appended after the full report.
- [x] Add chain completeness (Rule 8) and regime-shift consideration (Rule 9) to resynthesis prompt. Rewrite web chain angle #3 for alternative interpretations. Validated: Case 4 16→18/20, Case 6 12→14/16.
- [x] **TEST hybrid agentic pipeline** — Tested Cases 1, 2, 4 with `--hybrid`. Results: +3 across all cases. Three bugs fixed: dict key mismatch in web chain handler, agent prompt too weak (kept searching after ADEQUATE), synthesis patch overwriting good output with empty result. (Added 2026-02-23, tested 2026-02-24)

### Long-term: Data Collection Infrastructure

Currently all market data is fetched on-demand per query (FRED, Yahoo Finance). This works for now since we focus on precedents and reasoning rather than data freshness, and we only use a few months of public data. But it won't scale.

- [ ] **Persistent data collection** — Move from on-demand fetching to scheduled scraping/storage. Examples of data not available through current adapters:
  - CBOE equity put-call ratio (CPCE) — not on FRED or Yahoo. Free CBOE CSVs stop at Oct 2019. Would need CBOE daily page scraper. (Discovered via Case 5: pipeline used VIX as proxy instead of actual put-call ratio)
  - Sectoral ETF tracking (IGV, SMH, XLF, XLE, etc.) — available via Yahoo but not systematically tracked. Case 4 showed IGV -18.2% as a key signal but this was only discovered through web chains, not from our own data
  - Dark pool / institutional flow data — Case 5 rubric expected spot buying signals, pipeline had no access
- [ ] **Data source registry** — Centralize which variables are available from which source, what the update frequency is, and what gaps exist. Current `variable_resolver.py` maps variable names to FRED/Yahoo IDs but doesn't track coverage gaps or staleness.

### Long-term: Proactive Anomaly Detection Agent

Current system is static and reactive (query → research → insight). Future goal: a proactive agent that continuously monitors data and surfaces anomalies worth investigating.

- [ ] **Design proactive scan architecture** — The agent should scan daily-updated data to detect anomalies like:
  - Indicator extremes: put-call ratio at all-time high, VIX spike above 2σ, AAII bearish sentiment at 60%+
  - Sector divergences: IGV down 18% while SMH up 12% (cross-sector rotation signals)
  - Historical pattern matches: "this configuration was observed N times in last M years, and X% of the time Y happened within Z weeks"
  - Threshold breaches on chain-specific triggers (partially exists in `theme_refresh.py` but limited to simple % change checks)
- [ ] **Build anomaly → query bridge** — When the proactive agent detects an anomaly, it should auto-generate a research query and run it through the existing pipeline. Example: detect put-call ratio at 99th percentile → generate "CBOE equity put-call ratio at extreme levels, what are the historical precedents?" → run full pipeline → surface insight to trader
- [ ] **Use case studies as design input** — Cases 1-6 reveal what patterns the system should be watching for proactively. Each case study's trigger event (SaaS meltdown, snap election, record shorting, tariff ruling, put-call spike, labor equilibrium) is something the proactive agent should have detected from data before a human asked about it. Reverse-engineer the detection rules from existing case studies.

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
