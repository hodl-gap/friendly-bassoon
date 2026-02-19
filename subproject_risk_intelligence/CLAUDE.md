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
- Computes **derived macro metrics** (term premium, real yield, SOFR spread) from raw data
- Produces **independent reasoning tracks** — each with its own evidence, implications, and monitoring variables
- Supports **multi-asset analysis** (BTC, equity, or both)

### Output Modes
- **`insight`** (default): Multi-track reasoning with independent evidence per track. Each track has causal mechanism, historical precedent counts, asset implications with magnitude ranges, and monitoring variables with thresholds.
- **`belief_space`** (legacy): Multi-scenario output with direction, confidence scores, contradictions, and regime uncertainty.

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
- **Analysis**: Claude Opus for insight analysis, Sonnet for belief space, Haiku for extraction
- **Output**: Multi-track insight reports or legacy belief space scenarios
- **Framework**: Simple sequential workflow

## Architecture

### Code Organization
```
subproject_risk_intelligence/
|-- __init__.py                      # Package exports (run_impact_analysis, run_multi_asset_analysis)
|-- __main__.py                      # CLI entry point (--mode insight|belief_space, --asset)
|-- insight_orchestrator.py          # Main workflow orchestration
|-- states.py                        # RiskImpactState, InsightTrack type definitions
|-- config.py                        # Configuration (multi-analog, historical detection flags)
|-- impact_analysis.py               # Dual-mode LLM analysis (insight + belief_space dispatch)
|-- impact_analysis_prompts.py       # INSIGHT_SYSTEM_PROMPT, BELIEF_SPACE_SYSTEM_PROMPT, shared data sections
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
+-- theme_index.py                   # Theme-organized chain index
```

### Workflow (Current)
```
query (CLI input)
    |
    v
+-------------------------+
| 1. retrieve_context     |  Call run_retrieval(query) from database_retriever
|                         |  Retriever handles: query expansion, vector search,
|                         |  answer generation, gap detection/filling, web chain extraction
|                         |  Returns: enriched context with merged DB + web chains
+-----------+-------------+
            |
            v
+-------------------------+
| 2. load_chains          |  Load chains by theme (via ThemeIndex + asset's relevant_themes)
|                         |  Load per-theme assessments into state (macro regime context)
+-----------+-------------+
            |
            v
+-------------------------+
| 2.5 build_chain_graph   |  Build directed graph from retrieved + historical chains
|                         |  Find trigger variables matching query
|                         |  DFS to find all multi-hop paths from triggers to terminals
|                         |  Group paths into reasoning tracks
|                         |  Output: chain_tracks, chain_graph_text for prompt
+-----------+-------------+
            |
            v
+-------------------------+
| 3. extract_variables    |  Parse chains/synthesis for variable names
|                         |  Output: [tga, bank_reserves, btc, sofr, ...]
+-----------+-------------+
            |
            v
+-------------------------+
| 4. fetch_current_data   |  Fetch from FRED (TGA, SOFR, etc.)
|                         |  Fetch from Yahoo (BTC, DXY, etc.)
|                         |  Include 1w and 1m period changes
|                         |  Compute derived metrics: term_premium, real_yield_10y, sofr_spread
+-----------+-------------+
            |
            v
+-------------------------+
| 4.5 validate_claims     |  Call run_claim_validation() from data_collection
|                         |  Parses quantitative claims from synthesis
|                         |  Validates against actual data (correlation, p-value)
|                         |  Output: claim_validation_results
|                         |  Feature-flagged: ENABLE_CLAIM_VALIDATION
+-----------+-------------+
            |
            v
+-------------------------+
| 5. validate_patterns    |  Extract quantitative patterns from research
|                         |  Validate against current data
|                         |  Output: triggered/not-triggered for each pattern
+-----------+-------------+
            |
            v
+-------------------------+
| 5.5 enrich_historical   |  Single-analog: detect historical gap, fetch data, compare
|     _event              |  Multi-analog: detect up to 5 analogs via LLM,
|                         |    fetch data in parallel (ThreadPoolExecutor),
|                         |    aggregate stats (direction, magnitude, timing)
|                         |  Output: historical_event_data + historical_analogs
+-----------+-------------+
            |
            v
+-------------------------+
| 6. analyze_impact       |  Dual-mode dispatch based on output_mode:
|                         |
|                         |  INSIGHT mode (default):
|                         |    - INSIGHT_SYSTEM_PROMPT + output_insight tool
|                         |    - Produces independent reasoning tracks
|                         |    - Each track: mechanism, evidence, implications, monitors
|                         |    - Populates legacy fields from best track for compat
|                         |
|                         |  BELIEF_SPACE mode (legacy):
|                         |    - BELIEF_SPACE_SYSTEM_PROMPT + output_assessment tool
|                         |    - Produces scenarios with likelihoods + contradictions
|                         |    - Direction, confidence, rationale, risk factors
|                         |
|                         |  Both modes receive:
|                         |    - Retrieved answer/synthesis + logic chains
|                         |    - Current data (raw + derived metrics) + validated patterns
|                         |    - Claim validation results (confirmed/refuted with stats)
|                         |    - Multi-hop causal paths (chain_graph_text)
|                         |    - Historical analog aggregation (historical_analogs_text)
|                         |    - MACRO REGIME context (per-theme assessments)
|                         |    - Historical event comparison (if detected)
|                         |    - Gap enrichment text (from retriever)
+-----------+-------------+
            |
            v
+-------------------------+
| 7. store_chains         |  Extract new chains from answer
|                         |  Semantic dedup (Jaccard similarity on variable pairs)
|                         |  Similar chains: increment validation_count + blend confidence
|                         |  New chains: extract trigger_conditions (Haiku + tool_use)
|                         |  Save to relationships.json
|                         |  Update theme index + variable frequency tracker
+-----------+-------------+
            |
            v
        Output (format_insight or format_output)
```

## Usage

```bash
# Default insight mode (multi-track reasoning)
python -m subproject_risk_intelligence "How does the Japan snap election affect risk assets?"
python -m subproject_risk_intelligence "TGA increased +10% this week, what's the impact?"

# Legacy belief_space mode (scenarios + contradictions)
python -m subproject_risk_intelligence --mode belief_space "Fed just cut rates 50bps"

# Multi-asset analysis
python -m subproject_risk_intelligence --asset btc,equity "A new global contagion is spreading"

# Skip data fetch / chain store for faster iteration
python -m subproject_risk_intelligence --skip-data --skip-chains "Test query"

# JSON output
python -m subproject_risk_intelligence --json "Bank reserves dropped 5%"

# Verbose mode
python -m subproject_risk_intelligence -v "VIX spiked to 40"
```

## Output Formats

### Insight Mode (default)
```
============================================================
INSIGHT REPORT -- BITCOIN
============================================================

TRACK 1: BOJ Tightening Acceleration Track
  Confidence: 72%
  Mechanism: election -> fiscal_expansion -> BOJ_rate_hike -> carry_unwind -> BTC_selloff
  Time Horizon: February 2026 - June 2026
  Evidence: 3 precedents, 67% success rate
    3/3 prior BOJ rate hike episodes correlated with BTC drawdowns of 20-30%.
    - BOJ rate hike August 2000: SPY +5.9% (1mo), VIX -18.1% (1mo)
    - BOJ negative rate January 2016: SPY -4.7% (1mo), VIX +5.5% (1mo)
  Asset Implications:
    - BTC: bearish (-20% to -30%, 1-3 months)
    - USDJPY: bearish (yen strengthens) (-3% to -8%, 2-4 weeks)
  Monitor:
    - BOJ April 2026 hike probability >70%: Confirms accelerated timeline
    - JGB 10-year yield >1.90%: Signals aggressive tightening
----------------------------------------

TRACK 2: Carry Trade Unwind Liquidity Drain Track
  ...
----------------------------------------

SYNTHESIS:
[Narrative connecting all tracks with quantified relationships]

KEY UNCERTAINTIES:
  - BOJ April vs June 2026 hike timing
  - Carry trade positioning data opacity
============================================================
```

### Belief Space Mode (legacy)
```
============================================================
BELIEF SPACE ANALYSIS -- BITCOIN
============================================================

SCENARIOS (Market Belief Paths):
  [1] Carry Trade Unwind Cascade
      Direction: BEARISH
      Likelihood: 45%
      Chain: BOJ rate hike -> yen strengthens -> carry unwind -> risk asset selling

  [2] Fiscal Dominance / Yen Weakness
      Direction: BULLISH
      Likelihood: 30%
      ...

CONTRADICTIONS (Coexisting Beliefs):
  * "BOJ hikes cause carry unwind" vs "Takaichi fiscal dominance keeps yen weak"

SUMMARY:
  Primary Direction: BEARISH
  Confidence: 0.55 (6 chains, 10 sources)
  Regime Uncertainty: high
============================================================
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
| `format_for_prompt(tracks)` | Format as `## MULTI-HOP CAUSAL PATHS` section |

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

### Dual-Mode Impact Analysis (`impact_analysis.py`)

```python
def analyze_impact(state, asset_class="btc"):
    output_mode = state.get("output_mode", "insight")
    if output_mode == "insight":
        return _analyze_insight(state, asset_class)   # INSIGHT_SYSTEM_PROMPT + output_insight tool
    else:
        return _analyze_belief_space(state, asset_class)  # BELIEF_SPACE_SYSTEM_PROMPT + output_assessment tool
```

Shared prompt data preparation via `_prepare_prompt_data()` feeds both modes.

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `run_impact_analysis()` | `insight_orchestrator.py` | Single-asset entry point (default: BTC) |
| `run_multi_asset_analysis()` | `insight_orchestrator.py` | Multi-asset entry point |
| `build_chain_graph()` | `insight_orchestrator.py` | Build ChainGraph from retrieved + historical chains |
| `format_insight()` | `insight_orchestrator.py` | Format insight tracks for CLI display |
| `format_output()` | `insight_orchestrator.py` | Format belief space for CLI display (legacy) |
| `analyze_impact()` | `impact_analysis.py` | Dual-mode dispatch (insight vs belief_space) |
| `_analyze_insight()` | `impact_analysis.py` | Insight mode: tracks with evidence + implications |
| `_analyze_belief_space()` | `impact_analysis.py` | Legacy mode: scenarios + contradictions |
| `get_insight_prompt()` | `impact_analysis_prompts.py` | Build insight prompt with shared data sections |
| `get_impact_analysis_prompt()` | `impact_analysis_prompts.py` | Build belief space prompt (legacy) |
| `_format_data_sections()` | `impact_analysis_prompts.py` | Shared data formatting (DRY between modes) |
| `detect_historical_gap()` | `historical_event_detector.py` | Single-analog gap detection |
| `detect_historical_analogs()` | `historical_event_detector.py` | Multi-analog detection (up to 5) |
| `enrich_with_historical_event()` | `insight_orchestrator.py` | Orchestrate single + multi-analog enrichment |
| `compute_derived_metrics()` | `current_data_fetcher.py` | Compute term_premium, real_yield_10y, sofr_spread |
| `validate_claims()` | `insight_orchestrator.py` | Wire data_collection claim validation into pipeline |
| `extract_chain_triggers()` | `relationship_store.py` | Extract chain-specific trigger conditions via Haiku |

## State Definition (`states.py`)

Key types:
- `InsightTrack` — Single reasoning track: title, causal_mechanism, historical_evidence, asset_implications, monitoring_variables, confidence, time_horizon
- `RiskImpactState` — Full pipeline state including: chain_tracks, chain_graph_text, historical_analogs, historical_analogs_text, claim_validation_results, output_mode, insight_output

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
| Derived Metrics | Done | term_premium, real_yield_10y, sofr_spread from raw data |
| Claim Validation | Done | Wire data_collection claim validation into insight pipeline |
| Chain-Specific Triggers | Done | Per-chain activation thresholds replace universal 5% heuristic |

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
- **Dual-mode output** - always maintain both insight and belief_space paths
- **CRITICAL: DO NOT OVERCOMPLICATE** - Keep it minimal and focused
