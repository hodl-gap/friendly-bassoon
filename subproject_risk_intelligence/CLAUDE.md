# Risk Intelligence Subproject - Claude Context

## Project Overview
This subproject is the research engine of an autonomous Bridgewater-style research team. Given a macro event or data update, it retrieves relevant logic chains, builds multi-hop causal graphs, finds historical analogs with quantified outcomes, and produces **multi-track causal insights** grounded in historical evidence.

## Core Purpose

**Input**: A specific macro event or data update (current or hypothetical)
**Output**: Multi-track insight report with independent reasoning tracks, each containing causal mechanisms, historical evidence, asset implications, and monitoring variables

### What Risk Intelligence Does
- Takes a **specific event/data update** as input
- Retrieves logic chains explaining causal mechanisms (event → ... → asset impact)
- Builds a **multi-hop causal graph** from retrieved + historical chains, finds all paths from trigger to terminal effects
- Finds up to **5 historical analogs** and aggregates statistics (direction distribution, magnitude, timing)
- **Validates quantitative claims** from synthesis against actual data (correlation, p-value)
- Computes **derived macro metrics** (term premium, real yield, credit spreads, real fed funds, etc.) from raw data
- Detects **convergence points** where multiple independent causes feed the same effect (AND logic)
- **Characterizes the current macro regime** vs historical analogs ("then vs now" comparison via Haiku + tool_use)
- Produces **temporally sequenced reasoning tracks** — each with its own evidence, implications, monitoring variables, and optional phase ordering
- Supports **multi-asset analysis** (BTC, equity, or both)

### Valid Query Examples
```
"How does the February 2026 Japan snap election affect risk assets and yen carry trades?"
"TGA increased +10% this week, what's the impact on risk assets?"
"A new global contagion is spreading, what's the impact on BTC?"
"Fed just announced 50bps emergency rate cut, what's the impact?"
```

### Invalid Query Examples
```
"What happened in August 2024 yen crash?" -> Use Retriever
"Compare current market to March 2020" -> Too vague, no specific event
"Explain how TGA affects liquidity" -> Use Retriever
```

## Technology Stack
- **Input**: Specific event/data update -> macro impact question
- **Retrieval**: Uses `subproject_database_retriever` for logic chains
- **Chain Graph**: Multi-hop causal path-finding via `shared/chain_graph.py`
- **Historical Analogs**: Up to 5 analogs fetched in parallel, aggregated statistics
- **Analysis**: Claude Opus for insight analysis, Sonnet for synthesis self-check, Haiku for extraction
- **Output**: Multi-track insight reports
- **Framework**: Agentic ReAct loops via `shared/agent_loop.py`

## Architecture

### Code Organization
```
subproject_risk_intelligence/
|-- __init__.py                      # Package exports (run_impact_analysis, run_multi_asset_analysis)
|-- __main__.py                      # CLI entry point (--asset, --json, --skip-data)
|-- insight_orchestrator.py          # Main workflow orchestration
|-- states.py                        # RiskImpactState, InsightTrack type definitions
|-- config.py                        # Configuration (multi-analog, historical detection flags)
|-- impact_analysis.py               # LLM-based insight generation (Opus + output_insight tool)
|-- impact_analysis_prompts.py       # SYSTEM_PROMPT, get_insight_prompt, shared data sections
|-- asset_configs.py                 # Per-asset configuration (BTC, equity)
|-- variable_extraction.py           # Extract variables from chains (Phase 2)
|-- current_data_fetcher.py          # Fetch live data with period changes + derived metrics (Phase 2)
|-- pattern_validator.py             # Validate research patterns vs current data (Phase 2)
|-- relationship_store.py            # Logic chain persistence with theme index + validation reinforcement + trigger extraction
|-- historical_event_detector.py     # Historical event detection + multi-analog detection
|-- historical_event_prompts.py      # LLM prompts for historical detection + MULTI_ANALOG_TOOL
|-- historical_data_fetcher.py       # Fetch historical data + metrics
|-- historical_aggregator.py         # Multi-analog parallel fetch + aggregate statistics
|-- theme_refresh.py                 # Daily theme monitoring + chain-specific trigger evaluation
|-- regime_characterization.py       # Regime characterization (then vs now)
|
|-- # Agentic pipeline files:
|-- synthesis_phase.py               # Phase 4: Opus generate + Sonnet verify + optional patch
|-- synthesis_prompts.py             # Verification prompt for synthesis self-check
|-- data_grounding_agent.py          # Phase 2: Agentic data grounding orchestrator
|-- data_grounding_agent_tools.py    # Phase 2: Tool schemas + handlers (6 tools)
|-- data_grounding_agent_prompts.py  # Phase 2: System prompt
|-- historical_context_agent.py      # Phase 3: Agentic historical context orchestrator
|-- historical_context_agent_tools.py # Phase 3: Tool schemas + handlers (7 tools)
|-- historical_context_agent_prompts.py # Phase 3: System prompt
|
|-- data/
|   |-- relationships.json           # Persistent chain storage
|   |-- theme_index.json             # Theme-organized chain index (auto-maintained)
|   +-- variable_frequency.json      # Variable appearance frequency tracking (auto-maintained)
|
+-- CLAUDE.md                        # This file

shared/
|-- chain_graph.py                   # ChainGraph: directed graph with DFS path-finding
|-- schemas.py                       # Canonical types: LogicChainStep, LogicChain, ConfidenceMetadata
|-- model_config.py                  # Central model selection for all subprojects
|-- run_logger.py                    # Pipeline run logger with LLM cost tracking
|-- snapshot.py                      # State capture for debugging
|-- variable_resolver.py             # Variable -> data source lookup
|-- theme_config.py                  # 6 macro themes with anchor variables
|-- theme_index.py                   # Theme-organized chain index
|-- agent_loop.py                    # Generic ReAct loop runner for agentic phases
+-- feature_flags.py                 # Agentic pipeline iteration limits
```

### Workflow
```
query (CLI input)
    |
    v
+-- PHASE 1: RETRIEVAL AGENT (agentic, iterate until coverage adequate) --+
|   Tools: search_pinecone, extract_web_chains, web_search,               |
|          generate_synthesis, assess_coverage, finish_retrieval           |
|   Returns: enriched context with merged DB + web chains                 |
+------+------------------------------------------------------------------+
       |
       v
+-- SHARED CONTEXT (runs once for all asset classes) ---------------------+
|                                                                         |
|  +-- PHASE 2: DATA GROUNDING AGENT (agentic, adaptive depth) --------+ |
|  |   Tools: extract_variables, fetch_variable_data, validate_claim,   | |
|  |          validate_patterns, compute_derived, finish_grounding      | |
|  +--------------------------------------------------------------------+ |
|                                                                         |
|  +-- PHASE 3: HISTORICAL CONTEXT AGENT (agentic, adaptive analog) ---+ |
|  |   Tools: detect_analogs, fetch_analog_data, aggregate_analogs,     | |
|  |          characterize_regime, load_theme_chains, finish_historical  | |
|  +--------------------------------------------------------------------+ |
+------+------------------------------------------------------------------+
       |
       v  (per asset class, parallel if multiple)
+-- PER-ASSET IMPACT ------------------------------------------------+
|  load_chains → build_chain_graph → characterize_regime              |
|  → PHASE 4: SYNTHESIS (Opus generate + Sonnet self-check + patch)   |
|  → store_chains → update_regime                                     |
+------+--------------------------------------------------------------+
       |
       v
   Output (format_insight)
```

## Usage

```bash
python -m subproject_risk_intelligence "How does the Japan snap election affect risk assets?"
python -m subproject_risk_intelligence "TGA increased +10% this week, what's the impact?"
python -m subproject_risk_intelligence --asset btc,equity "A new global contagion is spreading"
python -m subproject_risk_intelligence --skip-data --skip-chains "Test query"
python -m subproject_risk_intelligence --json "Bank reserves dropped 5%"
python -m subproject_risk_intelligence -v "VIX spiked to 40"
```

## Key Components

### Multi-Hop Chain Graph (`shared/chain_graph.py`)

Directed graph of causal chains built at query time. Ephemeral (built fresh per query), dict-of-lists, no external deps.

| Method | Purpose |
|--------|---------|
| `add_chain()` / `add_chains_from_list()` | Build graph from chain steps (handles both `{steps}` and `{logic_chain: {steps}}` formats) |
| `find_paths(start, end, max_depth)` | DFS with cycle detection, returns all paths |
| `get_tracks(trigger)` | Group paths by terminal effect into reasoning tracks |
| `get_trigger_variables(query)` | Match query tokens to graph variables, sorted by out-degree |
| `get_convergence_points(min_in_degree)` | Find nodes where multiple independent causes converge (in-degree >= 2) |
| `format_for_prompt(tracks, convergence_points)` | Format as `## MULTI-HOP CAUSAL PATHS` + `## CONVERGENCE POINTS` sections |

### Historical N-Analog Aggregation (`historical_aggregator.py`)

Finds up to 5 historical analogs, fetches market data in parallel, computes aggregate statistics.

| Function | Purpose |
|----------|---------|
| `detect_historical_analogs()` | LLM (Haiku + tool_use) detects up to 5 analogs with relevance scores |
| `fetch_multiple_analogs()` | Parallel data fetch via ThreadPoolExecutor (max 3 workers) |
| `aggregate_analogs()` | Direction distribution, magnitude (median/min/max), timing (recovery days) |
| `format_analogs_for_prompt()` | Format as `## HISTORICAL PRECEDENT ANALYSIS (Multi-Analog)` section |

### Derived Macro Metrics (`current_data_fetcher.py`)

Computes standard macro spreads from raw fetched data. Traders think in derived metrics — "real yield rose 50bps" is actionable, "10Y at 4.5% and breakeven at 2.3%" requires mental math.

| Metric | Formula | Inputs |
|--------|---------|--------|
| `term_premium` | us10y - us02y | Yield curve slope |
| `real_yield_10y` | us10y - breakeven_inflation | Inflation-adjusted yield |
| `sofr_spread` | sofr - fed_funds | Money market stress indicator |
| `equity_risk_premium` | sp500_earnings_yield - us10y | Equity vs bond attractiveness |
| `credit_spread_ig` | ig_corporate_yield - us10y | Investment grade credit risk |
| `credit_spread_hy` | hy_corporate_yield - us10y | High yield credit risk |
| `real_fed_funds` | fed_funds - breakeven_inflation | Inflation-adjusted policy rate |
| `money_supply_velocity_proxy` | nominal_gdp_proxy - m2 | Money velocity approximation |

`compute_derived_metrics()` is called in both `fetch_current_data()` (current values) and `fetch_conditions_at_date()` (historical Then-vs-Now comparison). Derived values include period-over-period changes when input changes are available.

### Claim Validation (`insight_orchestrator.py` → `data_collection`)

Wires the existing `data_collection` claim validation pipeline into the insight flow. After data fetch, `validate_claims()` calls `run_claim_validation(synthesis_text=...)` which parses quantitative claims, fetches historical data, and validates statistically.

Results appear in the LLM prompt as `## CLAIM VALIDATION (Data-Tested)`:
```
- "BTC follows gold with 63-428 day lag": PARTIALLY CONFIRMED (correlation=0.45, p=0.001)
- "VIX above 30 leads to BTC selloff": CONFIRMED (correlation=-0.72, p=0.000)
- "TGA drawdown always leads to reserve increase": REFUTED (correlation=-0.15, p=0.420)
```

Feature-flagged via `ENABLE_CLAIM_VALIDATION` (default: true).

### Chain-Specific Trigger Conditions (`relationship_store.py`, `theme_refresh.py`)

Replaces the universal 5% weekly change threshold for active chain detection with variable-appropriate thresholds. A 5% VIX move is routine; a 5% DXY move is extreme.

`extract_chain_triggers()` uses Haiku + tool_use (same pattern as `extract_patterns()` in pattern_validator) to extract 1-2 trigger conditions per chain at store time. Each trigger specifies `{variable, condition_type, condition_value, condition_direction, timeframe_days}`.

`theme_refresh.py` reads `chain["trigger_conditions"]` and falls back to the 5% heuristic when no triggers exist. Backfill script: `python scripts/backfill_chain_triggers.py`.

### Convergence Detection (`shared/chain_graph.py`)

Detects when multiple independent causes feed the same intermediate node (e.g., TGA drawdown AND Fed QE AND fiscal spending all → liquidity). Uses the existing `self.reverse` adjacency to find nodes with in-degree >= 2. Results appear in the LLM prompt as `## CONVERGENCE POINTS (multiple causes → same effect)`.

### Sequential Reasoning (`impact_analysis.py`, `insight_orchestrator.py`)

Tracks can express temporal dependency via `sequence_position` (1=first, 2=next, etc.). The LLM is instructed to assign sequence positions when tracks are genuinely sequential (e.g., "carry unwind selloff" phase 1 → "central bank easing response" phase 2 → "liquidity-driven recovery" phase 3). Output rendering sorts sequenced tracks first and displays "Phase: N".

### Regime Characterization (`insight_orchestrator.py`)

Compares current market conditions against historical analogs to produce a structured "then vs now" assessment. Uses Haiku + tool_use (same pattern as other extraction steps) to output: regime name, closest analog, similarities, key differences, and summary. Results appear in the LLM prompt as `## REGIME CHARACTERIZATION (Then vs Now)`. Feature-flagged via `ENABLE_REGIME_CHARACTERIZATION`.

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `run_impact_analysis()` | `insight_orchestrator.py` | Single-asset entry point (default: BTC) |
| `run_multi_asset_analysis()` | `insight_orchestrator.py` | Multi-asset entry point |
| `build_chain_graph()` | `insight_orchestrator.py` | Build ChainGraph from retrieved + historical chains |
| `format_insight()` | `insight_orchestrator.py` | Format insight tracks for CLI display |
| `analyze_impact()` | `impact_analysis.py` | LLM insight generation (Opus + output_insight tool) |
| `get_insight_prompt()` | `impact_analysis_prompts.py` | Build insight prompt with shared data sections |
| `_format_data_sections()` | `impact_analysis_prompts.py` | Shared data formatting for prompt |
| `detect_historical_gap()` | `historical_event_detector.py` | Single-analog gap detection |
| `detect_historical_analogs()` | `historical_event_detector.py` | Multi-analog detection (up to 5) |
| `compute_derived_metrics()` | `current_data_fetcher.py` | Compute 8 derived metrics from raw data |
| `validate_claims()` | `insight_orchestrator.py` | Wire data_collection claim validation into pipeline |
| `extract_chain_triggers()` | `relationship_store.py` | Extract chain-specific trigger conditions via Haiku |
| `characterize_regime()` | `insight_orchestrator.py` | Compare current regime vs historical analogs (Haiku + tool_use) |
| `get_convergence_points()` | `shared/chain_graph.py` | Find nodes where multiple causes converge |

## State Definition (`states.py`)

Key types:
- `InsightTrack` — Single reasoning track: title, causal_mechanism, historical_evidence, asset_implications, monitoring_variables, confidence, time_horizon, sequence_position (temporal ordering)
- `RiskImpactState` — Full pipeline state including: chain_tracks, chain_graph_text, historical_analogs, historical_analogs_text, claim_validation_results, regime_characterization_text, insight_output

## Configuration (`config.py`)

```python
# Historical Event Detection (Phase 4)
ENABLE_HISTORICAL_EVENT_DETECTION = True
HISTORICAL_DATE_BUFFER_DAYS = 7
MAX_INSTRUMENTS_PER_EVENT = 6

# Multi-Analog Historical Precedent Analysis
ENABLE_MULTI_ANALOG = True         # env: RISK_MULTI_ANALOG
MAX_HISTORICAL_ANALOGS = 5
ANALOG_RELEVANCE_THRESHOLD = 0.5

# Claim Validation (wires data_collection into insight pipeline)
ENABLE_CLAIM_VALIDATION = True     # env: RISK_CLAIM_VALIDATION

# Chain-Specific Trigger Conditions (per-chain activation thresholds)
ENABLE_CHAIN_TRIGGERS = True       # env: RISK_CHAIN_TRIGGERS

# Regime Characterization (then vs now comparison)
ENABLE_REGIME_CHARACTERIZATION = True  # env: RISK_REGIME_CHAR
```

## Implementation Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: MVP | Done | Core loop: retrieve -> analyze -> output |
| Phase 2: Data Fetching | Done | Fetch current values (FRED, Yahoo) with period changes |
| Phase 2b: Pattern Validation | Done | Extract & validate research patterns vs current data |
| Phase 3: Chain Store | Done | Persist discovered logic chains |
| Phase 4: Historical Event Detection | Done | Detect historical event gaps, fetch actual market data |
| Phase 5: Knowledge Gap Filling | Moved | Moved to `subproject_database_retriever` (topic-agnostic) |
| Phase 6: Theme-Organized Chains | Done | Theme index, theme-based loading, macro regime context in prompts |
| Phase 7: Validation Reinforcement | Done | Semantic dedup with Jaccard similarity |
| Phase 8: Daily Monitoring | Done | Theme refresh with active chain detection, morning briefing |
| Multi-Hop Chain Graph | Done | Directed graph with DFS path-finding, reasoning tracks |
| N-Analog Aggregation | Done | Up to 5 analogs, parallel fetch, aggregate statistics |
| Insight Output Format | Done | Multi-track reasoning with evidence, implications, monitoring |
| Derived Metrics | Done | 8 derived metrics: spreads, credit, real rates from raw data |
| Claim Validation | Done | Wire data_collection claim validation into insight pipeline |
| Chain-Specific Triggers | Done | Per-chain activation thresholds replace universal 5% heuristic |
| Convergence Detection | Done | Detect multi-cause convergence points in chain graph |
| Sequential Reasoning | Done | Temporal ordering of tracks (sequence_position) for phased analysis |
| Regime Characterization | Done | "Then vs Now" regime comparison via Haiku + tool_use |
| Agentic Pipeline | Done | Agentic data grounding, historical context, synthesis self-check. Tested Cases 1, 2, 4: +3 rubric improvement. Now the default (sequential pipeline removed). |

## Agentic Pipeline Phases

### Phase 2: Data Grounding Agent (`data_grounding_agent.py`)
Iteratively extracts variables, fetches data, validates claims, and computes derived metrics. Max 4 iterations via Sonnet.

**Tools**: `extract_variables`, `fetch_variable_data`, `validate_claim`, `validate_patterns`, `compute_derived`, `finish_grounding`

### Phase 3: Historical Context Agent (`historical_context_agent.py`)
Detects analogs, fetches market data, aggregates statistics, characterizes regime, and can discover preconditions worth checking in current data. Max 4 iterations via Sonnet.

**Tools**: `detect_analogs`, `fetch_analog_data`, `aggregate_analogs`, `characterize_regime`, `load_theme_chains`, `fetch_additional_data`, `finish_historical`

### Phase 4: Synthesis Self-Check (`synthesis_phase.py`)
Adds verification step after `analyze_impact()`: Sonnet checks if all evidence was addressed, and if gaps found, Opus re-generates with feedback appended.

## Theme-Organized Chains

Chains are organized by 6 macro themes: `liquidity`, `positioning`, `rates`, `risk_appetite`, `crypto_specific`, `event_calendar`. Each asset has `relevant_themes` in its config.

The impact analysis prompt includes a `## MACRO REGIME` section with per-theme assessments, populated by `scripts/daily_regime_scan.py --all --briefing`.

### Validation Reinforcement

When storing chains, semantic deduplication uses Jaccard similarity on normalized `(cause, effect)` variable pairs:
- Threshold: 0.7 (70% variable pair overlap)
- Similar chains: `validation_count += 1`, confidence blended (0.7 old + 0.3 new)
- New chains: stored as normal

### Daily Monitoring

`theme_refresh.py` provides `refresh_theme()`, `refresh_all_themes()`, `generate_briefing()`.
CLI: `python scripts/daily_regime_scan.py --all --briefing`

Active chain detection uses chain-specific `trigger_conditions` when available (e.g., VIX needs 20% move, DXY needs 2% move), falling back to the universal 5% heuristic for chains without triggers. Backfill existing chains: `python scripts/backfill_chain_triggers.py`.

## Dependencies

### Sibling Subprojects
- `subproject_database_retriever` - Provides `run_retrieval()` with gap detection, merged chains, enrichment text
- `subproject_data_collection` - Provides `run_claim_validation()` for statistical claim testing, `WebSearchAdapter` for web search

### Parent Directory
- `models.py` - AI model functions (`call_claude_sonnet`, `call_claude_haiku`)
- `.env` - API keys (FRED_API_KEY, TAVILY_API_KEY required)

### External APIs
- **FRED API** - Federal Reserve Economic Data (TGA, SOFR, reserves, Fed BS)
- **Yahoo Finance** - Market data (BTC, ETH, DXY, VIX, etc.) via `yfinance`
- **Tavily** - Web search for knowledge gap filling (via WebSearchAdapter)

## Notes for AI Assistants
- **Follow established patterns** from other subprojects
- **Main file = orchestration only** - no business logic
- **Prompts in separate files** - `*_prompts.py`
- **AI calls via parent's `models.py`**
- **CRITICAL: DO NOT OVERCOMPLICATE** - Keep it minimal and focused
