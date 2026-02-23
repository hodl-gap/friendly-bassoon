# Pipeline Architecture

Node-by-node reference for how a user query flows through the system and produces the final output.

All examples use real data from pipeline runs on 2026-02-11.

---

## End-to-End Flow

```
User Query
    │
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DATABASE RETRIEVER  (LangGraph)                                     │
│                                                                      │
│  process_query ──► search ──► generate ──► fill_gaps ──► resynthesis ──► persist_learning │
│                                                                      │
│  Output: synthesis, logic_chains, confidence, gap enrichment         │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  RISK INTELLIGENCE  (sequential)                                     │
│                                                                      │
│  retrieve ──► load_chains ──► extract_vars ──► fetch_data ──►        │
│  validate_claims* ──► validate_patterns ──► historical ──►           │
│  analyze_impact ──► store_chains                                     │
│                                                                      │
│  * validate_claims calls DATA COLLECTION internally                  │
│    (parse_claims ──► fetch_data ──► validate ──► format)             │
│                                                                      │
│  Output: direction, confidence, scenarios, rationale, risk factors   │
└──────────────────────────────────────────────────────────────────────┘

Note: VARIABLE MAPPER exists as standalone code (subproject_variable_mapper/)
but is NOT invoked in the standard pipeline. Variable extraction is handled
inline by Risk Intelligence's extract_variables step (LLM-based when
USE_LLM_VARIABLE_EXTRACTION=True). The integrated pipeline
(use_integrated_pipeline=True) can wire Variable Mapper → Data Collection
as an alternative path, but this is not the default.
```

**Shared module** (`shared/`) provides: canonical schemas, model config, variable resolver, integration wiring, run logger, and state snapshots. All subprojects import from `shared/` for consistent types and configuration.

---

## 1. Database Retriever — Node-by-Node

**Entry point**: `retrieval_orchestrator.py` → `run_retrieval(query)`
**State**: `RetrieverState`
**Graph**: `process_query → search → generate → fill_gaps → conditional_resynthesis → persist_learning → END`

### Node 1: `process_query`

Classifies the query, expands it into multiple search dimensions, and extracts temporal references.

**File**: `query_processing.py`
**LLM calls**: 1× Haiku (query expansion). Classification is pattern-match (no LLM).

<details>
<summary>Input (from initial state)</summary>

```json
{
  "query": "What does rising RDE indicate about liquidity conditions?",
  "iteration_count": 0,
  "needs_refinement": false
}
```
</details>

<details>
<summary>Output (added to state)</summary>

```json
{
  "processed_query": "What does rising RDE indicate about liquidity conditions?",
  "query_type": "research_question",
  "query_variations": [
    "RDE rising liquidity conditions market",
    "RDE liquidity indicator financial stress",
    "RDE money market liquidity tightening"
  ],
  "query_dimensions": [
    {
      "dimension": "Direct RDE-Liquidity Link",
      "reasoning": "Targets the core relationship between RDE movements and liquidity assessment.",
      "query": "RDE rising liquidity conditions market"
    },
    {
      "dimension": "RDE as Liquidity Indicator",
      "reasoning": "Frames RDE as a diagnostic tool for systemic liquidity tightness or ease.",
      "query": "RDE liquidity indicator financial stress"
    },
    {
      "dimension": "RDE and Money Market Conditions",
      "reasoning": "Connects RDE signals to short-term funding environment.",
      "query": "RDE money market liquidity tightening"
    }
  ],
  "query_temporal_reference": {
    "reference_year": null,
    "reference_period": null,
    "is_future": false,
    "is_current": false
  }
}
```
</details>

**Adaptive expansion**: Simple queries (≤10 words) → 2-3 dimensions. Complex queries → 4-6 dimensions.

---

### Node 2: `search`

Two-stage hybrid retrieval: broad semantic recall → LLM re-ranking for causal relevance. Original query's top-N results are protected from expansion dilution.

**File**: `vector_search.py`
**LLM calls**: 1× Haiku (re-ranking all candidates via tool_use)
**External**: Pinecone vector search (1 original + N expanded queries)

<details>
<summary>Input (key fields consumed)</summary>

```
processed_query     → primary search query
query_variations    → ["RDE rising liquidity conditions market", ...]  (3 expanded queries)
```
</details>

<details>
<summary>Output (added to state)</summary>

```json
{
  "retrieved_chunks": [
    {
      "id": "754d3067272f86dd_270",
      "score": 0.542,
      "metadata": {
        "category": "data_opinion",
        "date": "2026-01-01T07:32:56+00:00",
        "source": "@FinanceLancelot",
        "tg_channel": "Fomo CTRINE",
        "telegram_msg_id": "13024",
        "what_happened": "Primary Credit facility rising to ~$9.87B...",
        "interpretation": "Rising usage indicates banking system stress...",
        "extracted_data": "{\"logic_chains\": [...], \"source\": \"...\"}"
      },
      "matched_query_idx": 2,
      "is_original_top": false,
      "rerank_score": 0.92
    }
  ],
  "retrieval_scores": [0.92, 0.90, 0.75, 0.72, 0.65, 0.60, 0.58, 0.58, 0.55, 0.55],
  "iteration_count": 1,
  "needs_refinement": false,
  "dangling_effects_followed": ["funding_stress", "sofr", "bitcoin_price"]
}
```

10 chunks returned after re-ranking. Chain expansion followed 3 dangling effects (additional semantic searches for effects that appear as outputs but never as inputs).
</details>

**Re-ranking scores**: 0.9+ = directly answers with causal logic, 0.5-0.6 = related but no direct causal link, <0.3 = off-topic.

---

### Node 3: `generate`

Three-stage answer generation:
1. **Stage 1** — Extract and organize logic chains from chunks (grouped by theme)
2. **Stage 2** — Synthesize consensus conclusions with confidence scoring (via tool_use for structured output)
3. **Stage 3** — Identify contradicting evidence (conditional: skipped for data_lookup or high-confidence)

**File**: `answer_generation.py`
**LLM calls**: 1× Sonnet (Stage 1: chain extraction), 1× Sonnet tool_use (Stage 2: synthesis), 0-1× Haiku (Stage 3: contradictions)

<details>
<summary>Output (added to state)</summary>

```json
{
  "answer": "## Direct Liquidity Indicators\n\n**CHAIN:** rising Primary Credit usage [primary_credit] → banking system liquidity stress [liquidity_stress]\n**MECHANISM:** Banks only use the discount window when unable to obtain liquidity elsewhere...\n**SOURCE:** Source 1, Source 2\n\n**CHAIN:** large repo usage detected [repo_usage] → sign of funding demand/stress [funding_stress]\n...\n\n## Multi-Hop Liquidity Resolution Chains\n\n**CHAIN:** bank reserves rebound to $3T [bank_reserves] → funding issue resolved [funding_liquidity] → shift to long-biased futures [futures_bias]\n...",

  "synthesis": "## CONSENSUS CONCLUSIONS\n\n**CONCLUSION:** Rising RDE indicates emerging banking system liquidity stress\n**SUPPORTING PATHS:**\n- Path 1: Primary Credit spike → liquidity stress signal\n- Path 2: Repo spike → funding demand → Fed intervention needed\n...\n**CONFIDENCE_SCORE:** 0.85\n\n## KEY VARIABLES TO MONITOR\n- Primary Credit ($50B+ = crisis)\n- Bank reserves ($3T target)\n- Overnight repo (>$25B threshold)\n...",

  "confidence_metadata": {
    "overall_score": 0.85,
    "chain_count": 6,
    "source_diversity": 10,
    "confidence_level": "High",
    "strongest_chain": "Primary Credit spikes → precede major financial crises (2008: $100B+, 2020: $60B, 2023: $90B)"
  },

  "contradictions": "Skipped: confidence 0.85 >= threshold 0.85",

  "topic_coverage": {
    "found_entities": ["Japan", "TGA", "Fed", "US", "QT", "RRP"],
    "direct_match": true,
    "match_ratio": 1.0,
    "unresolved_dangles": ["data_center_ai_financing", "futures_bias", "funding_stress", "sofr", "bitcoin_price"],
    "gap_type": "unresolved_dangles"
  },

  "data_temporal_summary": {
    "structural_count": 17,
    "forward_looking_count": 0,
    "time_bound_count": 0
  }
}
```
</details>

---

### Node 4: `fill_gaps`

Detects knowledge gaps in the synthesis and attempts to fill them via web search, data fetching, or historical analog lookup.

**File**: `knowledge_gap_detector.py`
**LLM calls**: 1× Haiku (gap detection via tool_use), 0-6× Haiku (gap filling extractions)
**External**: Tavily web search (0-6 queries), Yahoo/FRED data fetch (for correlation computation)

<details>
<summary>Output (added to state)</summary>

```json
{
  "knowledge_gaps": {
    "coverage_rating": "PARTIAL",
    "gap_count": 3,
    "gaps": [
      {
        "category": "topic_not_covered",
        "status": "COVERED",
        "found": "Synthesis directly answers with multiple causal chains for rising RDE → liquidity stress."
      },
      {
        "category": "historical_precedent_depth",
        "status": "GAP",
        "found": "Mentions 2008, 2020, 2023 but no specific dates or outcomes.",
        "missing": "Specific dates and Primary Credit levels during crises.",
        "fill_method": "historical_analog",
        "indicator_name": "Primary Credit"
      },
      {
        "category": "quantified_relationships",
        "status": "GAP",
        "found": "Directional relationships only, no correlation coefficients.",
        "missing": "Correlation between Primary Credit usage and market drawdowns.",
        "fill_method": "data_fetch",
        "instruments": ["spy", "qqq", "vix"]
      }
    ]
  },

  "filled_gaps": [
    {
      "category": "quantified_relationships",
      "status": "FILLED",
      "computed_correlation": 0.8514,
      "data_points": 62,
      "period": "2025-11-11 to 2026-02-10"
    },
    {
      "category": "event_calendar",
      "status": "FILLED",
      "confidence": 0.85,
      "extracted_facts": [
        {"fact": "FOMC rate decision June 18, 2025", "source": "Forbes"},
        {"fact": "FOMC rate decision July 30, 2025", "source": "Forbes"}
      ]
    }
  ],

  "unfillable_gaps": [
    {
      "category": "historical_precedent_depth",
      "reason": "no_dates_found"
    }
  ],

  "gap_enrichment_text": "## Additional Context: Quantified Relationships\n- SPY vs QQQ correlation: 0.8514 (over 62 trading days)\n- Period: 2025-11-11 to 2026-02-10\n\n## Additional Context: Event Calendar\n- FOMC rate decision June 18, 2025\n- FOMC rate decision July 30, 2025\n...",

  "extracted_web_chains": [],
  "logic_chains": [ ... ]
}
```

Gap categories: `topic_not_covered`, `historical_precedent_depth`, `quantified_relationships`, `monitoring_thresholds`, `event_calendar`, `mechanism_conditions`, `exit_criteria`.
</details>

---

### Node 5: `conditional_resynthesis`

Only fires when gap filling discovered significant new information (web_chains ≥ 3 or filled_gaps ≥ 2). Re-runs Sonnet synthesis integrating new data.

**File**: `answer_generation.py` → `regenerate_synthesis()`
**LLM calls**: 0-1× Sonnet (only if threshold met)

<details>
<summary>Trigger condition</summary>

```python
if len(web_chains) < 3 and len(filled_gaps) < 2:
    return state  # skip — no re-synthesis needed
```

In the RDE example: 0 web chains, 2 filled gaps → threshold met → re-synthesis fires.
</details>

<details>
<summary>Output (updates synthesis field)</summary>

The `synthesis` field is replaced with an updated version that integrates gap enrichment. All other state fields are preserved.
</details>

---

### Node 6: `persist_learning`

Persists verified web chains to Pinecone for future retrieval (L1 learning) and updates variable frequency tracker.

**File**: `web_chain_persistence.py`, `retrieval_orchestrator.py`
**LLM calls**: None
**External**: Pinecone upsert, OpenAI embedding generation

<details>
<summary>Behavior</summary>

- Filters web chains: only `quote_verified=True` AND `confidence in ("high", "medium")`
- Generates embeddings and upserts to Pinecone with canonical metadata format
- Updates `variable_frequency.json` with newly seen variables
- Chain IDs: `web_{md5(cause+effect+source)[:16]}`
- Skipped when `skip_gap_filling=True` (used by daily theme refresh)
</details>

---

### Retriever — Complete State at Output

After all 5 nodes, the `RetrieverState` returned by `run_retrieval(query)` contains:

| Field | Type | Description |
|-------|------|-------------|
| `query` | str | Original user query |
| `query_type` | str | `"research_question"` or `"data_lookup"` |
| `query_variations` | list[str] | Expanded search queries |
| `retrieved_chunks` | list[dict] | Top-K chunks with metadata and rerank scores |
| `retrieval_scores` | list[float] | Re-rank scores for each chunk |
| `answer` | str | Stage 1 output: organized logic chains (markdown) |
| `synthesis` | str | Stage 2 output: consensus conclusions + key variables |
| `contradictions` | str | Stage 3 output: contradicting evidence analysis |
| `confidence_metadata` | dict | `{overall_score, chain_count, source_diversity, confidence_level, strongest_chain}` |
| `topic_coverage` | dict | Entity match info, unresolved dangles, gap type |
| `knowledge_gaps` | dict | Gap detection results with coverage rating |
| `gap_enrichment_text` | str | Additional context from filled gaps |
| `filled_gaps` | list[dict] | Successfully filled gaps with data |
| `unfillable_gaps` | list[dict] | Gaps that could not be filled |
| `extracted_web_chains` | list[dict] | Logic chains from web extraction |
| `logic_chains` | list[dict] | Merged DB + web chains |
| `data_temporal_summary` | dict | Temporal coverage of retrieved data |
| `skip_gap_filling` | bool | When true, skips gap detection/filling and persist_learning (used by theme refresh) |

---

## 2. Risk Intelligence — Node-by-Node

**Entry point**: `insight_orchestrator.py` → `run_multi_asset_analysis(query, assets=["equity"])`
**State**: `RiskImpactState`
**Flow**: Sequential (no LangGraph). Two phases: shared context preparation, then per-asset analysis.

### Step 1: `retrieve_context`

Calls `run_retrieval(query)` from the database retriever. All retriever nodes (process_query → search → generate → fill_gaps → resynthesis) execute here.

**Output to state**: `retrieved_chunks`, `logic_chains`, `synthesis`, `confidence_metadata`, `knowledge_gaps`, `gap_enrichment_text`, `filled_gaps`

---

### Step 2: `load_chains`

Loads historical logic chains organized by theme. Uses the asset's `relevant_themes` config to load chains from matching themes via `ThemeIndex`, then filters by keyword relevance to the query. Also loads per-theme assessments into state for macro regime context.

**File**: `relationship_store.py`
**LLM calls**: None
**Output to state**: `historical_chains` (list of previously discovered chains), `theme_states` (per-theme assessments from daily scan)

---

### Step 3: `extract_variables`

Parses logic chains and synthesis text to extract variable names for data fetching. When `USE_LLM_VARIABLE_EXTRACTION=True` (default), supplements keyword extraction with LLM inference to capture logically implied variables.

**File**: `variable_extraction.py`
**LLM calls**: 0-2× Haiku (when `USE_LLM_VARIABLE_EXTRACTION=True`: 1× query-frame identification + 1× synthesis extraction; falls back to regex-only when disabled)

**Output to state**:
```json
{
  "extracted_variables": [
    {"normalized": "tga", "role": "cause", "chain_path": "tga -> bank_reserves"},
    {"normalized": "bank_reserves", "role": "effect", "chain_path": "tga -> bank_reserves"},
    {"normalized": "sofr", "role": "effect", "chain_path": "bank_reserves -> sofr"},
    {"normalized": "btc", "role": "effect", "chain_path": "risk_appetite -> btc"}
  ]
}
```

---

### Step 4: `fetch_current_data`

Fetches current values for each extracted variable from FRED and Yahoo Finance. Includes 1-week and 1-month period changes.

**File**: `current_data_fetcher.py`
**LLM calls**: None
**External**: FRED API, Yahoo Finance (yfinance)

**Output to state**:
```json
{
  "current_values": {
    "btc": {"value": 75470.91, "change_1w_abs": -13714, "change_1w_pct": -15.4, "change_1m_abs": -15556, "change_1m_pct": -17.1},
    "tga": {"value": 923000000000, "change_1w_pct": 6.2, "change_1m_pct": 10.2},
    "sofr": {"value": 3.65, "change_1w_abs": 0.0},
    "fed_balance_sheet": {"value": 6590000000000, "change_1w_pct": 0.0}
  },
  "btc_price": 75470.91
}
```

---

### Step 5: `validate_patterns`

Extracts quantitative patterns from research text (e.g., "TGA +200% over 3mo → BTC crash") and validates against current data.

**File**: `pattern_validator.py`
**LLM calls**: 1× Haiku (pattern extraction)

**Output to state**:
```json
{
  "validated_patterns": [
    {
      "pattern": "TGA increase > 10% monthly",
      "triggered": true,
      "current_metric": 10.2,
      "threshold": 10.0,
      "explanation": "TGA +10.2% this month exceeds threshold"
    },
    {
      "pattern": "Reserve floor breach at $3T",
      "triggered": false,
      "current_metric": 2940000000000,
      "threshold": 3000000000000,
      "explanation": "Reserves at $2.94T, below $3T but not breaching floor"
    }
  ]
}
```

---

### Step 5.5: `enrich_with_historical_event`

Detects if the query references a historical event, fetches actual market data from that period, and compares to current conditions.

**File**: `historical_event_detector.py`, `historical_data_fetcher.py`
**LLM calls**: 0-1× Haiku (event detection), 0-1× Haiku (instrument identification), 0-1× Haiku (date range extraction)
**External**: Yahoo Finance (historical data), Tavily (date lookup)

**Trigger**: Only activates when retrieved research references a past event (e.g., "similar to COVID 2020", "like the 2024 yen crash").

**Output to state** (when triggered):
```json
{
  "historical_event_data": {
    "event_detected": true,
    "event_name": "March 2020 COVID Crash",
    "period": {"start": "2020-02-23", "end": "2020-04-07"},
    "instruments": {
      "BTC-USD": {"peak_to_trough": -45.5, "peak_date": "2020-02-14"},
      "^GSPC": {"peak_to_trough": -28.5, "peak_date": "2020-02-19"},
      "^VIX": {"peak_to_trough": 158.5, "peak_date": "2020-03-16"}
    },
    "correlations": {"BTC_vs_SP500": 0.82, "BTC_vs_VIX": -0.84},
    "comparison_to_current": {
      "VIX": "Then +158.5% → Now +5.8% (stress much lower)",
      "BTC": "Then -45.5% → Now -15.6% (decline smaller)"
    }
  }
}
```

---

### Step 6: `analyze_impact`

The highest-leverage LLM call. Receives all accumulated context and produces directional assessment with belief-space scenarios.

**File**: `impact_analysis.py`
**LLM calls**: 1× Opus (impact analysis — configurable in `shared/model_config.py`)

**Input context assembled for LLM prompt**:
- Retrieved answer + synthesis (from retriever)
- Logic chains (DB + web, merged)
- Current data values with period changes
- Validated patterns (triggered/not-triggered)
- Historical event comparison (if detected)
- Gap enrichment text
- Historical chains from relationship store
- Macro regime context (per-theme assessments from daily scan)

**Output to state**:
```json
{
  "direction": "BEARISH",
  "confidence": {
    "score": 0.75,
    "chain_count": 4,
    "source_diversity": 3,
    "strongest_chain": "tga_increase -> bank_reserves_drain -> funding_stress -> btc_pressure"
  },
  "time_horizon": "weeks",
  "decay_profile": "medium",
  "rationale": "TGA has increased +$86B (+10.2%) over the past month to $923B, representing a liquidity drain from the banking system...",
  "risk_factors": [
    "Rapid TGA drawdown reversal if Treasury begins spending aggressively",
    "Institutional accumulation override at lower BTC prices",
    "Fed balance sheet expansion could override Treasury liquidity drain"
  ],
  "scenarios": [
    {
      "name": "Liquidity Crunch",
      "direction": "BEARISH",
      "likelihood": 0.65,
      "chain": "tga_increase -> reserve_drain -> funding_stress -> btc_pressure"
    },
    {
      "name": "Institutional Accumulation",
      "direction": "BULLISH",
      "likelihood": 0.25,
      "chain": "price_decline -> institutional_buying -> supply_absorption -> recovery"
    }
  ],
  "belief_space": {
    "contradictions": [
      {
        "thesis_a": "TGA drain → liquidity crisis → BTC down",
        "thesis_b": "Institutional accumulation → BTC floor",
        "implication": "Timing depends on pace of TGA moves"
      }
    ],
    "regime_uncertainty": "medium",
    "dominant_narrative": "Liquidity Crunch"
  }
}
```

---

### Step 7: `store_chains`

Extracts new logic chains from the analysis. Uses semantic deduplication (Jaccard similarity on normalized variable pairs, threshold 0.7) — similar chains increment `validation_count` and blend confidence (0.7 old + 0.3 new) instead of storing duplicates (L2/L3 learning). New chains are persisted to `data/relationships.json`, then the theme index and variable frequency tracker are updated.

**File**: `relationship_store.py`
**LLM calls**: None
**Output**: Updated JSON file on disk, updated theme index and variable frequency. State field `discovered_chains` populated.

---

## 3. Variable Mapper — Node-by-Node

**Entry point**: `variable_mapper_orchestrator.py` → `run_variable_mapper(synthesis_text)`
**State**: `VariableMapperState`
**Graph**: `extract_variables → normalize_variables → [detect_missing] → map_data_ids → END`

Step 3 (`detect_missing`) is skipped when `USE_COMBINED_EXTRACTION=True` (default).

### Node 1: `extract_variables`

Extracts variables from synthesis text. If `logic_chains` are provided, extracts from structure first (no LLM needed for those), then supplements with LLM extraction.

**File**: `variable_extraction.py`
**LLM calls**: 1× Haiku (combined extraction prompt)

**Input**: `synthesis` (text), optionally `logic_chains` (structured)
**Output**:
```json
{
  "extracted_variables": [
    {"raw_name": "Treasury General Account", "normalized_name": "tga", "role": "trigger", "role_reasoning": "initiates liquidity response", "category": "direct"},
    {"raw_name": "bank reserves", "normalized_name": "bank_reserves", "role": "indicator", "category": "direct"},
    {"raw_name": "SOFR", "normalized_name": "sofr", "role": "confirmation", "category": "direct"}
  ],
  "chain_dependencies": [
    {"from": "tga", "to": "bank_reserves", "relationship": "causes"},
    {"from": "bank_reserves", "to": "sofr", "relationship": "causes"}
  ],
  "skip_step3": true
}
```

### Node 2: `normalize_variables`

Normalizes variable names to canonical forms using `liquidity_metrics_mapping.csv`. Exact match first, then LLM fuzzy match.

**File**: `normalization.py`
**LLM calls**: 0-1× Haiku (fuzzy matching for unrecognized names)

### Node 3: `detect_missing` (conditional — usually skipped)

Parses logic chains to find variables mentioned in chains but not explicitly extracted. Skipped when combined extraction already handled this.

### Node 4: `map_data_ids`

Maps normalized variable names to data source IDs using `discovered_data_ids.json`. Auto-triggers discovery (via Claude Code SDK + web search) for unmapped variables.

**File**: `data_id_mapping.py`
**LLM calls**: 0× normally (lookup), N× if auto-discovery triggers

**Output** (final state):
```json
{
  "normalized_variables": [
    {
      "raw_name": "TGA",
      "normalized_name": "tga",
      "role": "trigger",
      "data_id": "FRED:WTREGEN",
      "source": "FRED",
      "api_url": "https://api.stlouisfed.org/fred/series/observations?series_id=WTREGEN",
      "frequency": "weekly",
      "validated": true
    }
  ],
  "unmapped_variables": ["unknown_metric"],
  "missing_variables": ["fci"],
  "chain_dependencies": [
    {"from": "tga", "to": "bank_reserves", "relationship": "causes"}
  ]
}
```

---

## 4. Data Collection — Node-by-Node

**Entry point**: `data_collection_orchestrator.py` → `run_claim_validation(synthesis_text)`
**State**: `DataCollectionState`
**Graph (claim_validation mode)**: `parse_claims → resolve_data_ids → fetch_data → validate_claims → format_output → END`

### Node 1: `parse_claims`

LLM extracts testable claims from synthesis text (e.g., "BTC follows gold with 63-428 day lag").

**File**: `claim_parsing.py`
**LLM calls**: 1× Haiku

### Node 2: `resolve_data_ids`

Resolves each claim's variables to data source IDs using the shared variable resolver.

**File**: `data_fetching.py`
**LLM calls**: None

### Node 3: `fetch_data`

Fetches historical time series for each variable via FRED/Yahoo adapters.

**File**: `data_fetching.py`
**External**: FRED API, Yahoo Finance

### Node 4: `validate_claims`

Runs statistical validation: correlation, lag analysis, threshold breach checking.

**File**: `validation_logic.py`
**LLM calls**: 0-1× Haiku (interpretation)

### Node 5: `format_output`

Formats final output JSON.

**Output**:
```json
{
  "mode": "claim_validation",
  "results": [
    {
      "claim": "BTC follows gold with 63-428 day lag",
      "status": "partially_confirmed",
      "actual_correlation": 0.45,
      "optimal_lag_days": 127,
      "p_value": 0.001,
      "interpretation": "Correlation exists but weaker than implied"
    }
  ]
}
```

---

## 5. Database Manager — Ingestion Pipeline

**Entry point**: `telegram_workflow_orchestrator.py`
**Flow**: Procedural (no LangGraph)

Not query-triggered — runs as a batch process to ingest new Telegram messages.

```
Step 1: telegram_fetcher.py      → Fetch messages from Telegram API
Step 2: message_pipeline.py      → Per-channel processing:
        ├── extract_telegram_data.py   → JSON → CSV
        ├── process_messages_v3.py     → Categorize + extract structured data
        └── qa_validation.py           → QA sampling
Step 3: embedding_generation.py  → Generate OpenAI embeddings (3072-dim)
Step 4: pinecone_uploader.py     → Upsert to Pinecone
```

**Per-message structured output** stored in Pinecone metadata:
```json
{
  "source": "Goldman Sachs",
  "data_source": "FICC Weekly",
  "what_happened": "TGA drawdown accelerating",
  "interpretation": "Liquidity injection into banking system",
  "logic_chains": [
    {
      "steps": [
        {
          "cause": "TGA drawdown",
          "cause_normalized": "tga",
          "effect": "bank reserves increase",
          "effect_normalized": "bank_reserves",
          "mechanism": "Treasury spending releases funds",
          "evidence_quote": "TGA 잔고가 750B로 감소..."
        }
      ]
    }
  ]
}
```

The `cause_normalized` / `effect_normalized` fields enable cross-chunk chain connection at retrieval time.

---

## Shared Module

| File | Purpose | Key Exports |
|------|---------|-------------|
| `schemas.py` | Canonical types | `LogicChainStep`, `LogicChain`, `ConfidenceMetadata` |
| `model_config.py` | Central model selection | `EXTRACTION_MODEL`, `ANALYSIS_MODEL`, `IMPACT_ANALYSIS_MODEL` |
| `run_logger.py` | Pipeline run logger | `RunLogger` context manager, LLM cost tracking |
| `snapshot.py` | State capture | `snapshot_state()`, `start_run()` |
| `variable_resolver.py` | Variable → data source lookup | `resolve_variable()`, `list_known_variables()` |
| `theme_config.py` | Theme definitions | `get_theme()`, `get_all_themes()`, `get_all_anchor_variables()` |
| `theme_index.py` | Theme-organized chain index | `ThemeIndex` (load/save, assign chains, rebuild) |
| `variable_frequency.py` | Variable frequency tracking | `VariableFrequencyTracker` (record, promote, demote) |
| `data_id_utils.py` | Data ID format | `parse_data_id()`, `format_data_id()` |
| `integration.py` | Mapper → Collection wiring | `map_and_fetch_variables()` |
| `paths.py` | Project paths | `PROJECT_ROOT`, `SUBPROJECTS` |
| `log_utils.py` | Logging | `log()` |

**Model config** (current defaults):

| Role | Model | Used by |
|------|-------|---------|
| Extraction (parsing, re-ranking, gap detection) | Claude Haiku | All subprojects |
| Analysis (synthesis, answer generation) | Claude Sonnet | Retriever, Data Collection |
| Impact analysis (highest-leverage call) | Claude Opus | Risk Intelligence |
| Fallback | Claude Sonnet | All subprojects |

---

## LLM Cost Per Query (typical)

From the SaaS meltdown run (312s, 17 LLM calls):

| Model | Calls | Input Tokens | Output Tokens | Cost |
|-------|-------|-------------|--------------|------|
| Haiku | 13 | 58,566 | 12,607 | $0.12 |
| Sonnet | 3 | 13,995 | 6,096 | $0.13 |
| Opus | 1 | 11,405 | 1,704 | $0.30 |
| **Total** | **17** | **83,966** | **20,407** | **$0.55** |

---

## File Reference

| Subproject | Entry Point | State | Graph |
|------------|-------------|-------|-------|
| Database Manager | `telegram_workflow_orchestrator.py` | (procedural) | — |
| Database Retriever | `retrieval_orchestrator.py` → `run_retrieval()` | `RetrieverState` | LangGraph |
| Variable Mapper | `variable_mapper_orchestrator.py` → `run_variable_mapper()` | `VariableMapperState` | LangGraph |
| Data Collection | `data_collection_orchestrator.py` → `run_claim_validation()` | `DataCollectionState` | LangGraph |
| Risk Intelligence | `insight_orchestrator.py` → `run_multi_asset_analysis()` | `RiskImpactState` | Sequential |
| Shared | `shared/__init__.py` | — | — |
