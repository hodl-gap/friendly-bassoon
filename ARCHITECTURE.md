# Agentic Research Workflow - Architecture Overview

**Purpose**: Validate pipeline structure, data flow, and input/output contracts between subprojects.

---

## Project Goal

Build an **agentic research workflow** that:
1. Ingests financial research from Telegram channels
2. Stores structured insights in a vector database
3. Answers research questions using RAG with logic chain extraction
4. Maps extracted variables to real data sources
5. Validates claims with historical data
6. Produces actionable impact assessments (starting with BTC)

---

## Pipeline Overview

```
                                    ┌─────────────────────────┐
                                    │   Telegram Channels     │
                                    │   (Korean macro research)│
                                    └───────────┬─────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SUBPROJECT 1: DATABASE MANAGER                                             │
│  Purpose: Ingest, structure, embed, store                                   │
│                                                                             │
│  Telegram JSON → Extract → Categorize → Structure → Embed → Pinecone       │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                                    ┌─────────────────────────┐
                                    │   Pinecone Vector DB    │
                                    │   (436 vectors)         │
                                    └───────────┬─────────────┘
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        │                       │                       │
                        ▼                       ▼                       ▼
┌───────────────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  SUBPROJECT 2: RETRIEVER      │  │  User Query         │  │  SUBPROJECT 5:      │
│  Purpose: RAG + synthesis     │◄─┤  "What drives       │  │  BTC INTELLIGENCE   │
│                               │  │   liquidity?"       │  │  (calls retriever)  │
└───────────────────────────────┘  └─────────────────────┘  └─────────────────────┘
                │                                                   │
                ▼                                                   │
┌───────────────────────────────┐                                   │
│  SUBPROJECT 3: VARIABLE MAPPER│◄──────────────────────────────────┤
│  Purpose: Logic → Data IDs    │     (via shared/integration.py)   │
└───────────────────────────────┘                                   │
                │                                                   │
                ▼                                                   │
┌───────────────────────────────┐                                   │
│  SUBPROJECT 4: DATA COLLECTION│◄──────────────────────────────────┘
│  Purpose: Fetch & validate    │     (via shared/integration.py)
└───────────────────────────────┘
                │
                ▼
        ┌───────────────┐
        │  Final Output │
        │  (Validated   │
        │   insights)   │
        └───────────────┘

                    ┌─────────────────────────────────────┐
                    │         SHARED MODULE               │
                    │  shared/                            │
                    │  ├── data_id_utils.py    (parsing) │
                    │  ├── variable_resolver.py (lookup) │
                    │  └── integration.py      (wiring)  │
                    └─────────────────────────────────────┘
```

---

## Subproject Details

### 1. Database Manager

**Role**: Telegram → Structured Vectors

| Stage | Input | Output |
|-------|-------|--------|
| Fetch | Telegram channel + date range | `result.json` (raw messages) |
| Extract | JSON messages | CSV with `telegram_msg_id`, `text`, `date` |
| Categorize | Raw text | `category`: data_opinion, interview_meeting, data_update, greeting, schedule, other |
| Structure | Categorized message | Structured JSON (see below) |
| Embed | Structured text | 3072-dim OpenAI embedding |
| Upload | Embedding + metadata | Pinecone vector |

**Structured Output Schema** (per message):
```json
{
  "source": "Goldman Sachs",
  "data_source": "FICC Weekly",
  "what_happened": "TGA drawdown accelerating",
  "interpretation": "Liquidity injection into banking system",
  "tags": "indirect_liquidity",
  "topic_tags": ["US", "liquidity", "treasury"],
  "liquidity_metrics": [
    {"name": "tga", "value": "750B", "direction": "down"}
  ],
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
  ],
  "temporal_context": {
    "policy_regime": "QT",
    "liquidity_regime": "transitional"
  }
}
```

**Pinecone Metadata**:
```json
{
  "telegram_msg_id": 12345,
  "tg_channel": "hyottchart",
  "date": "2026-01-15",
  "category": "data_opinion",
  "source": "Goldman Sachs",
  "tags": "indirect_liquidity",
  "topic_tags": ["US", "liquidity"]
}
```

---

### 2. Database Retriever

**Role**: Query → Synthesized Answer with Logic Chains

| Stage | Input | Output |
|-------|-------|--------|
| Query Processing | User query string | Classified query + expanded queries |
| Vector Search | Query embeddings | Top-K chunks (with LLM re-ranking) |
| Chain Expansion | Initial chunks | Additional chunks for dangling effects |
| Synthesis | Retrieved chunks | Organized logic chains + confidence |
| Contradiction | Synthesis | Contradicting evidence (if any) |

**Input**:
```
"What features predict liquidity expansion in 2026?"
```

**Output** (`RetrieverState`):
```json
{
  "query": "What features predict liquidity expansion in 2026?",
  "query_type": "research_question",
  "retrieved_chunks": [...],
  "answer": "Based on 4 sources...",
  "synthesis": "## STAGE 1: Logic Chains\n...\n## STAGE 2: Synthesis\n...",
  "logic_chains": [
    {
      "chain": "tga_drawdown -> bank_reserves -> risk_appetite",
      "source": "Goldman Sachs",
      "confidence": 0.75
    }
  ],
  "confidence_metadata": {
    "overall_score": 0.72,
    "path_count": 3,
    "source_diversity": 2,
    "confidence_level": "High"
  },
  "contradictions": {
    "found": true,
    "evidence": "UBS notes QT acceleration could offset...",
    "impact": "Medium"
  }
}
```

---

### 3. Variable Mapper

**Role**: Synthesis Text → Data Source Mappings

| Stage | Input | Output |
|-------|-------|--------|
| Extraction | Synthesis text | List of variable names |
| Normalization | Raw names | Canonical names (via metrics CSV) |
| Missing Detection | Logic chains | Variables in chain but not provided |
| Data ID Mapping | Normalized names | API endpoints + metadata |

**Input**: Retriever's `synthesis` field (text)

**Output** (`VariableMapperState`):
```json
{
  "variables": [
    {
      "raw_name": "Treasury General Account",
      "normalized_name": "tga",
      "role": "trigger",
      "role_reasoning": "mentioned as condition initiating response",
      "category": "direct",
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

### 4. Data Collection

**Role**: Fetch Data + Validate Claims

**Mode A: Claim Validation**

| Stage | Input | Output |
|-------|-------|--------|
| Parse Claims | Synthesis text | Structured claims |
| Fetch Data | Variable mappings | Historical time series |
| Validate | Claim + data | Statistical result |

**Input**:
```json
{
  "mode": "claim_validation",
  "retriever_synthesis": "BTC follows gold with 63-428 day lag...",
  "variable_mappings": {...}
}
```

**Output**:
```json
{
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

**Mode B: News Collection**

| Stage | Input | Output |
|-------|-------|--------|
| Collect | RSS feeds | Raw articles |
| Filter | Articles | Relevant institutional news |
| Analyze | Filtered news | Actionable insights |

**Output**:
```json
{
  "insights": [
    {
      "institution": "GPIF",
      "action": "rebalancing_to_jgb",
      "direction": "buy",
      "confidence": 0.85
    }
  ],
  "retriever_queries": [
    "What does Japanese pension rebalancing into JGBs mean for risk assets?"
  ]
}
```

---

### 5. BTC Intelligence

**Role**: Query → Directional Impact Assessment

| Stage | Input | Output |
|-------|-------|--------|
| Retrieve Context | Query | Logic chains from retriever |
| Load Chains | - | Historical chains from JSON store |
| Extract Variables | Chains | Variable list |
| Fetch Current | Variables | Current values (FRED, Yahoo) |
| Validate Patterns | Research patterns + current data | Triggered/not-triggered |
| Analyze | All context | Direction + confidence + rationale |
| Store Chains | New chains | Persist to JSON |

**Input**:
```
"What is the impact of TGA drawdown on BTC?"
```

**Output** (`BTCImpactState`):
```json
{
  "direction": "BULLISH",
  "confidence": {
    "score": 0.72,
    "chain_count": 3,
    "source_diversity": 2,
    "strongest_chain": "tga -> bank_reserves -> risk_appetite -> btc"
  },
  "time_horizon": "weeks",
  "decay_profile": "medium",
  "current_values": {
    "btc": {"value": 75470, "change_1w": "-15.4%"},
    "tga": {"value": "923B", "change_1w": "+6.2%"}
  },
  "pattern_validation": {
    "tga_liquidity_drain": "TRIGGERED",
    "reserve_floor_breach": "NOT_TRIGGERED"
  },
  "rationale": "TGA has increased +$86B over past month...",
  "risk_factors": [
    "Rapid TGA drawdown reversal",
    "Institutional accumulation override"
  ]
}
```

---

## Data Flow Summary

```
Telegram Message
    │
    ├─► category: data_opinion
    ├─► logic_chains: [{cause, effect, mechanism, evidence}]
    ├─► liquidity_metrics: [{name, value, direction}]
    └─► temporal_context: {regime}
            │
            ▼
    Pinecone Vector (3072-dim + metadata)
            │
            ▼
    Retrieved Chunks (top-K, re-ranked)
            │
            ▼
    Synthesis + Confidence + Contradictions
            │
            ├─► Variable Mapper ─► Data IDs ─► Data Collection ─► Validation
            │
            └─► BTC Intelligence ─► Direction + Confidence + Rationale
```

---

## Key Integration Contracts

| From | To | Contract |
|------|-----|----------|
| Manager → Pinecone | `logic_chains` with `cause_normalized`, `effect_normalized` | Enables cross-chunk chain connection |
| Manager → Pinecone | `liquidity_metrics` with `epistemic_type` | Distinguishes observed/inferred/forecasted |
| Retriever → Mapper | `synthesis` text + `logic_chains` array | Mapper extracts variables from both |
| Mapper → Collection | `variables` with `data_id`, `api_url` | Collection fetches without re-discovery |
| Retriever → BTC Intel | Full `RetrieverState` via `run_retrieval()` | BTC accesses chains, confidence, synthesis |
| **shared/** → All | `parse_data_id()`, `resolve_variable()` | Consistent data ID handling |
| **shared/** → BTC Intel | `map_and_fetch_variables()` | Integrated Mapper → Collection pipeline |
| BTC Intel → Disk | `regime_state.json` | Persists liquidity regime across queries |

---

## Known Gaps / Limitations

| Gap | Status | Resolution |
|-----|--------|------------|
| No end-to-end orchestrator | Open | Each subproject callable independently |
| ~~BTC Intel doesn't use Data Collection~~ | ✅ Resolved | `shared/integration.py` wires Mapper → Collection → BTC |
| ~~Variable Mapper → Data Collection not wired~~ | ✅ Resolved | `shared/integration.py` provides `map_and_fetch_variables()` |
| ~~Data ID format inconsistent~~ | ✅ Resolved | `shared/data_id_utils.py` standardizes `SOURCE:SERIES` format |
| ~~BTC hard-codes variable mappings~~ | ✅ Resolved | `shared/variable_resolver.py` uses `discovered_data_ids.json` |
| ~~Confidence metadata via regex~~ | ✅ Resolved | Claude tool_use ensures structured JSON output |
| ~~Chain expansion is semantic only~~ | ✅ Resolved | Metadata filter on `cause_normalized` tried first |
| ~~Variable Mapper extracts from text only~~ | ✅ Resolved | Extracts from `logic_chains` structure first |
| ~~BTC Intelligence is stateless~~ | ✅ Resolved | Regime state persisted in `data/regime_state.json` |
| News Collection RSS disabled | Open | Pending RSS feed testing |
| Query refinement stub in Retriever | Open | Chain expansion compensates |

---

## Validation Questions

1. ~~**Are the logic chain contracts correct?**~~ ✅ Yes - `cause_normalized`/`effect_normalized` enables cross-chunk connection
2. ~~**Is the confidence metadata sufficient?**~~ ✅ Yes - Structured via tool_use with guaranteed JSON
3. ~~**Should Variable Mapper output feed directly into Data Collection?**~~ ✅ Yes - Implemented via `shared/integration.py`
4. ~~**Is the BTC Intelligence isolation acceptable long-term?**~~ ✅ Resolved - Now uses shared resolver + integration
5. **Are there missing input/output fields that downstream consumers need?** - Open for review
6. **Should regime state be shared across subprojects?** - Currently BTC-only, could expand

---

## Shared Module

The `shared/` directory provides cross-subproject utilities:

| File | Purpose | Key Functions |
|------|---------|---------------|
| `data_id_utils.py` | Data ID format standardization | `parse_data_id()`, `format_data_id()`, `get_source()`, `get_series_id()` |
| `variable_resolver.py` | Centralized variable lookup | `resolve_variable()`, `list_known_variables()` |
| `integration.py` | Mapper → Collection wiring | `map_and_fetch_variables()` |

**Data ID Format**: `SOURCE:SERIES` (e.g., `FRED:WTREGEN`, `Yahoo:BTC-USD`)
- Bare series IDs default to FRED for backward compatibility
- All subprojects use `parse_data_id()` for consistent handling

**Variable Resolution**: Uses `discovered_data_ids.json` as source of truth
- Falls back to Yahoo tickers for market data (BTC, SPY, etc.)
- BTC Intelligence no longer maintains hard-coded mappings

---

## File Reference

| Subproject | Main Entry | State Definition |
|------------|------------|------------------|
| **Shared** | `shared/__init__.py` | (utility module, no state) |
| Database Manager | `telegram_workflow_orchestrator.py` | (procedural, no state file) |
| Database Retriever | `retrieval_orchestrator.py` | `states.py` → `RetrieverState` |
| Variable Mapper | `variable_mapper_orchestrator.py` | `states.py` → `VariableMapperState` |
| Data Collection | `data_collection_orchestrator.py` | `states.py` → `DataCollectionState` |
| BTC Intelligence | `btc_impact_orchestrator.py` | `states.py` → `BTCImpactState` |
