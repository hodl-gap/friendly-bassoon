# Project Evolution Log

Historical record of how this project evolved from a Telegram scraper to an autonomous macro research platform. Every change came from running the system, finding something broken or missing, and fixing it.

---

## Phase 1: Telegram Ingestion (2025-11-30 to 2025-12-09)

### Initial Goal
Process Telegram messages from Korean IB research channels, categorize them (event, opinion, interview), extract structured metrics, embed them in Pinecone for search.

### What Existed
```
subproject_database_manager/
  telegram_fetcher.py
  message_categorization.py
  data_opinion_extraction.py, interview_meeting_extraction.py
  metrics_mapping_utils.py          # flat metric dictionaries
  embedding_generation.py
  pinecone_uploader.py
  process_messages_v3.py            # orchestrator
models.py                           # GPT-5 calls
```

The extraction produced flat "metric relationships" — e.g., `{metric: "RDE", value: "rising", interpretation: "liquidity tightening"}`. No causal structure.

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2025-12-03 | `a536a73` | Duplicate entries in processed CSV — dedup logic missing |
| 2025-12-07 | `a94603f` | **Metric dictionaries can't represent causality.** Replaced with logic chains (cause → effect → mechanism). Switched from GPT-5 to GPT-5 Mini. Also added `subproject_database_retriever/` — first RAG pipeline |
| 2025-12-09 | `da32655` | Extraction prompt refinements |

### Key Insight
> Flat metrics don't capture *why* something matters. "RDE rising" means nothing without "RDE rising → liquidity tightening → risk-off." Logic chains are the right primitive.

---

## Phase 2: Retriever + Variable Mapper (2025-12-29 to 2026-01-23)

### What Changed
Added two new subprojects. The retriever searches Pinecone and synthesizes answers. The variable mapper extracts specific data variables (FRED series, Yahoo tickers) from logic chains so they can be validated against real data.

### New Modules
```
subproject_database_retriever/       # RAG pipeline
  vector_search.py                   # Pinecone search
  answer_generation.py               # 3-stage chain extraction + synthesis
  query_processing.py                # query expansion
  retrieval_orchestrator.py

subproject_variable_mapper/          # chain → data source mapping
  variable_extraction.py
  data_id_discovery.py               # LLM-assisted data source lookup
  data_id_validation.py
  normalization.py
```

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2025-12-29 | `654cc0b` | Massive refactor: added retriever and variable mapper subprojects (41 files, 35K lines) |
| 2026-01-14 | `e2cce8b` | Variable mapper needed data ID discovery — FRED uses `UNRATE`, Yahoo uses `GLD`, different formats everywhere. Added LLM-based ID discovery + validation |
| 2026-01-15 | `7e0bb48` | Telegram channel names broke file paths — switched to channel IDs |
| 2026-01-22 | `a37c35c` | **Retriever had no temporal awareness.** Query about 2035 returned 2026-specific data ($1.26T QE). Added temporal extraction from queries, temporal guidance in synthesis prompt, LLM re-ranking for causal relevance, original query protection (top-5 preserved from dilution by expanded queries) |
| 2026-01-22 | `6c6e264` | Variable mapper pipeline broken: SDK import errors, wrong model selection, temporal threshold bugs |
| 2026-01-23 | `49125ab` | LLM efficiency: replaced LLM query classification with pattern matching (saves 1 Haiku call/query), simplified contradiction detection, added conditional resynthesis |
| 2026-01-23 | `752a442` | Database manager LLM efficiency: prompt caching for data_opinion batches |

### Key Insight
> Data source naming is chaotic — "US 10Y yield" maps to `FRED:DGS10` or `yahoofinance:^TNX` depending on context. Need a resolver layer.

---

## Phase 3: First Case Study + Cross-Subproject Integration (2026-01-26 to 2026-02-04)

### Context
JPY intervention case study was the first real test. Revealed that subprojects didn't talk to each other properly.

### What Was Built
```
subproject_btc_intelligence/         # first asset-specific module (BTC only)
  btc_impact_orchestrator.py
  variable_extraction.py
  current_data_fetcher.py            # CoinGecko, Yahoo Finance
  pattern_validator.py               # validate claims vs real data
  relationship_store.py              # persist chains locally
  impact_analysis.py

shared/                              # cross-subproject glue
  variable_resolver.py               # centralized variable → data source
  integration.py                     # wiring between subprojects
  data_id_utils.py                   # format standardization
```

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-01-26 | `c544414` | JPY intervention case study validation: chain-of-retrievals test |
| 2026-01-27 | `89fbfa7` | Telegram ingestion didn't track already-processed messages — re-processing everything each run |
| 2026-01-28 | `dcc66ef` | Added data collection subproject with institutional allocation scrapers |
| 2026-01-30 | `378f5a2` | Pipeline crashed mid-run with no recovery — added Step 1 checkpoint for resume |
| 2026-01-30 | `4975c6c` | Dedup tracker didn't count filtered messages (greetings, schedule posts) — counts were wrong |
| 2026-01-30 | `69342e1` | Missing data sources: added IB revenue and M&A tickers |
| 2026-02-02 | `8094e80` | **Added BTC intelligence subproject** — first end-to-end asset analysis (retrieve → extract variables → fetch data → validate → analyze impact) |
| 2026-02-02 | `1ed0800` | **8 architectural fixes**: data ID format chaos (FRED:X vs yahoofinance:Y), no cross-subproject wiring, metadata-first chain expansion, structure-first variable extraction, regime state persistence |
| 2026-02-02 | `9a7f3d6` | Logic chain extraction path broken, monthly FRED series not handled |
| 2026-02-03 | `a28f6ff` | Retriever returned results but couldn't tell if query was actually answered — added topic coverage detection + extrapolation warning |
| 2026-02-04 | `85939be` | BTC intelligence had no historical context — added historical event gap detection and data fetching |
| 2026-02-04 | `09559cb` | Impact analysis output missing: sufficiency check, variable acknowledgment, diverging scenarios |

### Key Insight
> Four separate subprojects with incompatible data formats is a nightmare. Need shared schemas and a resolver.

---

## Phase 4: Knowledge Gap Filling (2026-02-05 to 2026-02-06)

### What Broke
Pinecone search alone misses things. If the Telegram corpus doesn't cover a topic, the system has no answer. Need web search as fallback.

### What Was Built
```
subproject_database_retriever/
  knowledge_gap_detector.py          # detect what's missing
  knowledge_gap_prompts.py

subproject_data_collection/
  web_search_adapter.py              # Tavily search backend

trusted_domains.py                   # 78 trusted sources (IBs, central banks, major news)
```

Gap categories: `topic_not_covered`, `historical_precedent_depth`, `quantified_relationships`, `monitoring_thresholds`, `event_calendar`, `mechanism_conditions`, `exit_criteria`.

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-02-05 | `4cfb631` | **Pinecone-only retrieval can't handle novel topics.** Added web search gap filling with iterative refinement (up to 2 attempts per gap) |
| 2026-02-05 | `74d4a7c` | Added Tavily backend, optimized query routing per gap type |
| 2026-02-06 | `b2720a8` | **Web search returns text, not causal chains.** Added on-the-fly logic chain extraction from trusted web sources with quote verification (prevents hallucination). Confidence weighting: DB=1.0, web=0.7 |
| 2026-02-06 | `2e28ced` | Chain completeness check: if extracted chain A→B exists but B→C is missing, trigger web extraction for B→C |

### Key Insight
> Gap detection asking "is the topic mentioned?" is wrong. It should ask "is the question answered?" A synthesis can mention tariffs without explaining their impact. Fixed in `1071c53`.

---

## Phase 5: Evaluation Framework + Architectural Move (2026-02-09)

### What Happened
First real attempt at systematic evaluation. Created 3 test cases with concrete scoring rubrics. Also moved gap detection from BTC-specific to shared retrieval layer.

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-02-09 | `55d36eb` | Abstract rubrics don't work — replaced with concrete 13-point scoring (SaaS meltdown: trigger ID 3pts, CAPEX chain 4pts, contradiction 2pts, quantitative 3pts, example 1pt) |
| 2026-02-09 | `1bbe2e6` | **Gap detection was BTC-specific but the logic is universal.** Moved `knowledge_gap_detector.py` from btc_intelligence → database_retriever |
| 2026-02-09 | `1071c53` | **Gap detection prompt checked "topic mentioned" instead of "question answered."** Synthesis mentioning tariffs ≠ explaining tariff impact. Fixed prompt |
| 2026-02-09 | `03653e1` | Restructured diagnostic task into reusable test case framework |
| 2026-02-09 | `99e3af1` | Test case 02: Japan snap election (Takaichi) — carry trade impact |
| 2026-02-09 | `b337603` | Case 02 result: 11/18 PASS |
| 2026-02-09 | `78d8b7c` | Test case 03: Record shorting & short squeeze potential |

### Key Insight
> Evaluation must be concrete: "does the output contain X with Y evidence?" not "is the output good?"

---

## Phase 6: Multi-Asset Generalization (2026-02-10 to 2026-02-11)

### What Broke
BTC intelligence module was hardcoded everywhere — 15+ spots with "btc" strings. Couldn't analyze equities without duplicating the entire subproject.

### What Changed
```
subproject_btc_intelligence/  →  subproject_risk_intelligence/
  btc_impact_orchestrator.py  →  insight_orchestrator.py
  asset_configs.py                # NEW: registry for BTC, Equity configs
```

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-02-10 | `aa96c4f` | Added historical analog analysis — find similar past events, fetch outcome data |
| 2026-02-11 | `6ab2595` | **Renamed btc_intelligence → risk_intelligence.** Parameterized all BTC-hardcoded spots. Added asset_configs.py registry. ThreadPoolExecutor for parallel multi-asset analysis |
| 2026-02-11 | `b98d16d` | Cleanup remaining BTC-specific references |
| 2026-02-11 | `f73e861` | **Added shared infrastructure**: `schemas.py` (canonical types), `model_config.py` (central model selection), `run_logger.py` (cost tracking), `snapshot.py` (state capture). Replaced LLM query classification with pattern matching. Added few-shot examples to prompts |
| 2026-02-11 | `6d1c219` | Added `--image` CLI flag for vision-based indicator date extraction from chart screenshots |

### Key Insight
> Asset-agnostic retrieval + asset-specific impact analysis. The retrieval layer doesn't care about BTC vs equity — the analysis layer does.

---

## Phase 7: Proactive Monitoring + Insight Format (2026-02-13 to 2026-02-15)

### What Changed
System went from reactive (query → answer) to proactive (monitor themes → surface insights). Also introduced the multi-track insight output format.

### New Modules
```
shared/
  theme_config.py                    # 6 macro themes, 25 anchor variables
  theme_index.py                     # assign 141 chains to themes
  variable_frequency.py              # track variable promotion/demotion
  chain_graph.py                     # multi-hop DFS path-finding

subproject_risk_intelligence/
  web_chain_persistence.py           # L1 learning: web chains → Pinecone
  historical_aggregator.py           # N-analog parallel fetch + statistics

scripts/
  daily_regime_scan.py               # daily: refresh themes, generate briefing
  backfill_theme_index.py
  backfill_variable_frequency.py
```

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-02-13 | `264d5c9` | Extraction pipeline too slow — disabled QA, added image pre-filter, parallelized image extraction |
| 2026-02-14 | `9f5efe4` | **Added proactive research system**: 6 macro themes (liquidity, positioning, rates, risk_appetite, crypto_specific, event_calendar), 25 anchor variables, theme-organized chain index, variable frequency tracking, web chain persistence to Pinecone (L1 learning), daily monitoring script |
| 2026-02-15 | `dbf5364` | **Added insight output format** (multi-track causal reasoning), multi-hop chain graph with DFS path-finding, N-analog historical aggregation with parallel fetch. Dual-mode: insight (new) vs belief_space (legacy) |

### Key Insight
> Themes organize knowledge. Instead of searching "everything about BTC," search "what liquidity chains are active?" then "what positioning chains?" This is how Bridgewater's daily research works.

---

## Phase 8: Bug Marathon + Structural Gaps (2026-02-18 to 2026-02-21)

### What Happened
First real e2e test runs exposed 17 bugs, then a series of structural gaps. This phase was pure fix-and-improve.

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-02-18 | `864e879` | **17 bugs fixed**: image MIME detection hardcoded, ZeroDivisionError in stats, shallow copy in parallel runs, first-run regime initialization crash, extraction prompts missing polarity field, thread-safety lock for sys.modules |
| 2026-02-19 | `be26e59` | 3 pipeline gaps: historical analogs not grounded in real data, variable extraction was regex-only (added LLM), prediction tracking write-only |
| 2026-02-19 | `cb2d88e` | **CACHE_DIR import error blocked ALL web-search gap filling** — entire gap-fill feature was silently broken |
| 2026-02-19 | `b88b5ff` | 3 structural improvements: query-derived variables (don't wait for chains), analog macro conditions, query refinement |
| 2026-02-19 | `a89e658` | 3 more gaps: claim validation against real data, 8 derived metrics (real yields, credit spreads, term premium), chain-specific trigger thresholds (replace universal 5% heuristic) |
| 2026-02-19 | `695fedf` | 5 more gaps: convergence detection (multi-cause → same effect), sequential reasoning (temporal ordering), regime characterization ("then vs now"), expanded derived metrics, synthesis truncation at 4000 chars (bumped to 8000) |
| 2026-02-20 | `0644aa2` | **Validated 3 case studies**: Case 1 SaaS 9/13, Case 2 Japan 13/18, Case 3 Shorting 21/22. Fixed web chain extraction injection, added debug logging infrastructure |
| 2026-02-21 | `bad83e6` | **Categorization prompt dropped institutional research.** [GS]-tagged CAPEX analysis was classified as `event_announcement` (dropped) instead of `data_opinion` (extracted). Fixed prompt. Also added log viewer tool (948 lines) |

### Key Insight
> Silent failures are the worst kind. CACHE_DIR import error meant gap filling was doing nothing for weeks. The categorization bug meant Goldman Sachs research was being dropped. Need instrumentation everywhere.

---

## Phase 9: API Centralization + Hybrid Agentic Pipeline (2026-02-23 to 2026-02-24)

### What Changed
Centralized all LLM API calls through `models.py`, upgraded to Claude 4.6, then built the hybrid agentic pipeline as a feature-flagged alternative to the sequential flow.

### New Modules
```
shared/
  agent_loop.py                      # generic ReAct loop runner
  feature_flags.py                   # env-var feature toggles

subproject_database_retriever/
  retrieval_agent.py                 # Phase 1: agentic retrieval
  retrieval_agent_tools.py           # 6 tools
  retrieval_agent_prompts.py

subproject_risk_intelligence/
  data_grounding_agent.py            # Phase 2: agentic data grounding
  data_grounding_agent_tools.py      # 6 tools
  data_grounding_agent_prompts.py
  historical_context_agent.py        # Phase 3: agentic historical context
  historical_context_agent_tools.py  # 7 tools
  historical_context_agent_prompts.py
  synthesis_phase.py                 # Phase 4: synthesis self-check
  synthesis_prompts.py
```

### Patches
| Date | Commit | What Broke / What Was Missing |
|------|--------|-------------------------------|
| 2026-02-23 | `39edd94` | Historical precedent extraction from web search was poor — improved parsing |
| 2026-02-23 | `f784cf5` | `source_name` not passing through pipeline — web chains lost attribution. Added few-shot precedent extraction example |
| 2026-02-23 | `e62509b` | Resynthesis prompt missing chain completeness (Rule 8: verify full A→B→C) and regime-shift consideration (Rule 9: if credible opposing view exists, present as competing scenario) |
| 2026-02-23 | `0cc91bb` | 4 doc/code inaccuracies found during pipeline audit |
| 2026-02-23 | `19d2a14` | **Centralized all API calls.** Replaced 16 direct `anthropic.Anthropic()` calls across 10 files. Added `call_claude_with_tools()`. Upgraded to Claude 4.6. Moved 5 inline prompts to `*_prompts.py` files |
| 2026-02-23 | `6193fa1` | **Added hybrid agentic pipeline (NOT TESTED).** 4 phases with ReAct loops, all feature-flagged. Old sequential pipeline untouched |
| 2026-02-23 | `7aea30f` | First test attempt: 3 critical bugs + added structured debug logging |
| 2026-02-24 | `b2151d1` | **3 hybrid pipeline bugs**: (1) dict key `"web_chains"` vs `"extracted_chains"` silently dropped all web chains, (2) agent prompt too weak — kept searching after ADEQUATE instead of synthesizing, (3) synthesis patch overwrote good output with empty result when verification produced 0 tracks |
| 2026-02-24 | `0a77939` | Synthesis didn't separate causes from forward projections — added temporal discipline |
| 2026-02-24 | `afd1d41` | **Added saved web chain reuse**: retriever now checks Pinecone for previously persisted web chains before calling Tavily (cost reduction). Pinecone queries filter web chains from institutional research by default. Added test cases 4-6 |

### Hybrid Pipeline Test Results
| Case | Sequential | Hybrid | Improvement |
|------|-----------|--------|-------------|
| Case 1 (SaaS Meltdown) | 8/13 | 11/13 | +3 |
| Case 2 (Japan Election) | 11/18 | 14/18 | +3 |
| Case 4 (SCOTUS Tariff) | 16/20 | 19/20 | +3 |

### Key Insight
> Agentic loops are powerful but fragile. The dict key typo (`"web_chains"` vs `"extracted_chains"`) silently dropped all web chains with no error. Need strict schema validation at agent boundaries.

---

## Philosophical Shifts (in order)

1. **Flat metrics → Logic chains** (Dec 7): Causality requires structure, not key-value pairs
2. **Chains → Executable variables** (Dec 29): Reasoning must ground in real data sources
3. **Pinecone-only → Web gap filling** (Feb 5): No corpus is complete; web search is the fallback
4. **Topic-mentioned → Question-answered** (Feb 9): Coverage detection must check if the actual question is answered, not just that related words appear
5. **BTC-specific → Multi-asset** (Feb 11): Retrieval is asset-agnostic; analysis is asset-specific
6. **Reactive → Proactive** (Feb 14): Theme-anchored monitoring enables daily research without queries
7. **Sequential → Agentic** (Feb 23): Iterative loops with coverage feedback produce better results (+3 across all cases)

---

## Phase 10: Legacy Pipeline Sunset (2026-02-24)

### What Changed
Removed all legacy code paths now superseded by the agentic pipeline. The codebase went from dual-mode (sequential + agentic, feature-flagged) to agentic-only.

### Removed
- **Sequential pipeline** (retrieval): LangGraph StateGraph, `build_graph()`, `route_after_retrieval()` — replaced by `run_retrieval_agent()`
- **Sequential pipeline** (risk intelligence): Manual function chaining for data grounding, historical context, synthesis — replaced by agentic agents
- **belief_space output mode**: `_analyze_belief_space()`, `BELIEF_SPACE_SYSTEM_PROMPT`, `get_impact_analysis_prompt()`, `format_output()`, scenario/contradiction parsers, state fields (`scenarios`, `belief_space`, `decay_profile`, `output_mode`)
- **Feature flags**: `is_agentic_retrieval()`, `is_agentic_data_grounding()`, `is_agentic_historical()`, `is_synthesis_self_check()`, `USE_HYBRID_PIPELINE`, `--hybrid` CLI flag
- **Prediction tracker**: `prediction_tracker.py` (510 lines), `prediction_ledger.json` (314 KB), all references in config/relationship_store/theme_refresh — was write-only dead storage
- **Unused functions**: `enrich_with_historical_event()`, `_build_condition_variables()`, `_run_integrated_pipeline()`, `_calculate_changes()`

### Key Insight
> Feature flags are a migration tool, not a permanent architecture. Once the agentic pipeline proved +3 across all test cases, the sequential code became pure maintenance burden.

---

## Open Issues (as of 2026-02-24)

1. **Hyperscaler CAPEX retrieval gap**: Retrieval agent never queries for second-order amplifiers (CAPEX overspending compounds SaaS selloff). The chunk exists in Pinecone but was never searched for.
2. **Temporal contamination in retrospective analysis**: Relationship store chains from Feb 23 leak into late-Jan case studies. Would need `discovered_at` filtering.
3. **Web chain reuse threshold**: Current heuristic (>=3 saved chunks = skip Tavily) may be too aggressive for novel queries.
