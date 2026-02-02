# BTC Impact Module - Implementation Plan

> **Note**: This is the original implementation plan. For current state and usage, see **CLAUDE.md**.
>
> **Key Changes from Plan**:
> - Module renamed to `subproject_btc_intelligence` (not `subproject_btc_impact`)
> - Data fetching is self-contained in `current_data_fetcher.py` (not via `subproject_data_collection` due to import conflicts)
> - Added `pattern_validator.py` for validating research patterns against current data
> - All phases (1-3) are complete

## Overview

A new subproject that analyzes the impact of macro events/conditions on Bitcoin price by:
1. Retrieving relevant logic chains from the research database
2. Extracting variables mentioned in those chains
3. Fetching current values for those variables
4. Producing: **Direction + Confidence + Time Horizon + Rationale + Risk Factors**
5. Storing discovered **logic chains** (full causal paths to BTC) in a JSON database for future retrieval

**CLI Usage**: `python -m subproject_btc_impact "What is the impact of TGA drawdown on BTC?"`

---

## Module Structure

```
subproject_btc_impact/
├── __init__.py
├── __main__.py                      # CLI entry point
├── btc_impact_orchestrator.py       # Main workflow orchestrator
├── states.py                        # BTCImpactState TypedDict
├── config.py                        # Configuration
│
├── impact_analysis.py               # Core LLM-based impact analysis
├── impact_analysis_prompts.py       # LLM prompts
├── variable_extraction.py           # Extract variables from logic chains
├── relationship_store.py            # JSON relationship database CRUD
│
├── data/
│   └── btc_relationships.json       # Persistent relationship storage
│
└── CLAUDE.md                        # Subproject documentation
```

**Note**: No `data_fetching.py` in this module - uses `subproject_data_collection` for all data fetching.

---

## State Definition (`states.py`)

```python
from typing import TypedDict, List, Optional, Dict, Any

class BTCImpactState(TypedDict, total=False):
    # Input
    query: str                              # User's original query

    # Retrieval Results (from database_retriever)
    retrieved_chunks: List[Dict[str, Any]]  # Raw chunks from retriever
    logic_chains: List[Dict[str, Any]]      # Parsed logic chains
    confidence_metadata: Dict[str, Any]     # {overall_score, path_count, source_diversity}

    # Variable Extraction
    extracted_variables: List[Dict[str, Any]]
    # Each: {normalized: str, role: "cause"|"effect", chain_path: str, source: str}

    # Data Fetching
    current_values: Dict[str, Any]          # {variable_name: {value, timestamp, source}}
    btc_price: float                        # Current BTC price (always fetched)
    fetch_errors: List[str]                 # Variables that failed to fetch

    # Relationship Store (logic chains ending in BTC)
    historical_chains: List[Dict]           # Loaded from btc_relationships.json
    discovered_chains: List[Dict]           # New logic chains found this run
    # Each chain: {logic_chain: {steps: [...], chain_summary: str}, terminal_effect, confidence, ...}

    # Output
    direction: str                          # BULLISH / BEARISH / NEUTRAL
    confidence: Dict[str, Any]              # Structured confidence (see below)
    # {
    #     "score": 0.72,                    # Overall 0.0-1.0
    #     "chain_count": 3,                 # Number of supporting chains
    #     "source_diversity": 2,            # Unique sources
    #     "strongest_chain": "tga -> liquidity -> btc"
    # }
    time_horizon: str                       # "intraday" | "days" | "weeks" | "months" | "regime_shift"
    decay_profile: str                      # "fast" | "medium" | "slow"
    rationale: str                          # Explanation text
    risk_factors: List[str]                 # What could invalidate the thesis

    # Debug
    retrieval_answer: str                   # Raw Stage 1 from retriever
    retrieval_synthesis: str                # Raw Stage 2 from retriever
```

---

## Workflow

```
query (CLI input)
    │
    ▼
┌─────────────────────────┐
│ 1. retrieve_context     │  Call run_retrieval(query) from database_retriever
│                         │  Parse logic_chains from retrieved_chunks
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 2. load_chains          │  Load btc_relationships.json (historical logic chains)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 3. extract_variables    │  Parse cause_normalized, effect_normalized from chains
│                         │  Filter for BTC-relevant variables
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 4. fetch_current_data   │  *** USES subproject_data_collection ***
│                         │  Call resolve_data_ids() + fetch_historical_data()
│                         │  from subproject_data_collection/data_fetching.py
│                         │  Extract latest values for each variable
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 5. analyze_impact       │  LLM call with:
│                         │    - Retrieved logic chains (from retriever)
│                         │    - Current variable values
│                         │    - Historical chains (from btc_relationships.json)
│                         │  Output: direction, confidence (structured),
│                         │          time_horizon, decay_profile, rationale, risks
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 6. store_chains         │  Extract new logic chains (full causal paths to BTC)
│                         │  Append to btc_relationships.json
└───────────┬─────────────┘
            │
            ▼
        Return BTCImpactState
```

---

## Relationship Database Schema (`data/btc_relationships.json`)

```json
{
  "metadata": {
    "last_updated": "2026-02-01T10:30:00Z",
    "total_relationships": 0
  },
  "relationships": [
    {
      "id": "rel_001",
      "logic_chain": {
        "steps": [
          {
            "cause": "TGA drawdown",
            "cause_normalized": "tga",
            "effect": "bank reserves increase",
            "effect_normalized": "bank_reserves",
            "mechanism": "Treasury spending releases TGA funds into banking system"
          },
          {
            "cause": "bank reserves increase",
            "cause_normalized": "bank_reserves",
            "effect": "risk appetite increases",
            "effect_normalized": "risk_appetite",
            "mechanism": "More liquidity reduces funding pressure, encourages risk-taking"
          },
          {
            "cause": "risk appetite increases",
            "cause_normalized": "risk_appetite",
            "effect": "BTC price rises",
            "effect_normalized": "btc_price",
            "mechanism": "BTC as risk asset benefits from increased liquidity and risk-on sentiment"
          }
        ],
        "chain_summary": "tga -> bank_reserves -> risk_appetite -> btc_price"
      },
      "terminal_effect": "btc_price",
      "relationship_type": "positive",
      "confidence": 0.75,
      "source_attribution": "Goldman Sachs via retrieval",
      "evidence_quote": "TGA 잔고가 감소하면 시스템 유동성이 증가하여 위험자산 선호도 상승",
      "discovered_at": "2026-02-01T10:30:00Z",
      "validation_count": 1
    }
  ]
}
```

**Key fields:**
- `logic_chain.steps[]` - Full multi-hop chain with cause/effect/mechanism per step
- `logic_chain.chain_summary` - Quick reference string for the full path
- `terminal_effect` - Final effect (should be `btc_price` or BTC-related)
- `evidence_quote` - Verbatim source text supporting the chain

---

## Prerequisites: Data Collection Subproject

Before BTC module can fully integrate, verify/complete the following in `subproject_data_collection`:

### Required (Must Have)

1. **Verify adapters are working**
   - [ ] FRED Adapter: Test with `WTREGEN` (TGA), `DGS10` (10Y yield)
   - [ ] Yahoo Adapter: Test with `BTC-USD`, `DX-Y.NYB` (DXY), `^VIX`
   - [ ] CoinGecko Adapter: Test with `bitcoin`

2. **Verify environment setup**
   - [ ] `FRED_API_KEY` set in `.env` (required for FRED adapter)
   - [ ] `yfinance` package installed (required for Yahoo adapter)
   - [ ] `requests` package installed (required for CoinGecko adapter)

3. **Verify variable resolution works**
   - [ ] `resolve_single_variable("tga")` returns `{source: "FRED", series_id: "WTREGEN"}`
   - [ ] `resolve_single_variable("btc")` returns valid mapping
   - [ ] `resolve_single_variable("dxy")` returns valid mapping

### Recommended (Nice to Have)

4. **Add `fetch_current_values()` function** to `data_fetching.py`
   ```python
   def fetch_current_values(
       variables: List[str],
       variable_mappings: Dict[str, Any] = None,
       lookback_days: int = 7
   ) -> Dict[str, Dict]:
       """
       Fetch only current/latest values for variables.

       Returns: {variable: {value, date, source}}

       Unlike fetch_historical_data() which fetches 5 years,
       this fetches only recent data (default 7 days) and
       returns the latest value.
       """
       # Implementation: reuse existing adapters with short date range
   ```

   **Why**: Current `fetch_historical_data()` fetches 5 years by default - wasteful for "current value" use case.

   **Workaround if not implemented**: BTC module calls adapters directly with 1-day window.

### Known Variable Mappings (Already Available)

| Variable | Source | Series ID | Notes |
|----------|--------|-----------|-------|
| `tga` | FRED | WTREGEN | Treasury General Account |
| `dxy` | Yahoo | DX-Y.NYB | US Dollar Index |
| `btc` | Yahoo | BTC-USD | Bitcoin (also CoinGecko:bitcoin) |
| `vix` | Yahoo | ^VIX | Volatility Index (also FRED:VIXCLS) |
| `us10y` | FRED | DGS10 | 10-Year Treasury Yield |
| `us02y` | FRED | DGS2 | 2-Year Treasury Yield |
| `gold` | Yahoo | GC=F | Gold Futures |
| `fed_balance_sheet` | FRED | WALCL | Fed Total Assets |
| `reserves` | FRED | TOTRESNS | Bank Reserves |

---

## Key Integration Points

### 1. Calling Database Retriever
```python
# In btc_impact_orchestrator.py
import sys
sys.path.append(str(Path(__file__).parent.parent / "subproject_database_retriever"))
from retrieval_orchestrator import run_retrieval

result = run_retrieval(query)
# Access: result["answer"], result["synthesis"], result["confidence_metadata"], result["retrieved_chunks"]
```

### 2. Calling Data Collection (for fetching current values)
```python
# In btc_impact_orchestrator.py
#
# USE subproject_data_collection for ALL data fetching.
# Do NOT call adapters directly - use the existing data_fetching module.
#
# Integration approach:
# 1. Import functions from data_collection/data_fetching.py
# 2. Build a DataCollectionState with extracted variables
# 3. Call resolve_data_ids() to map variables to data sources
# 4. Call fetch_historical_data() with short lookback to get recent values
# 5. Extract latest value from fetched_data

import sys
sys.path.append(str(Path(__file__).parent.parent / "subproject_data_collection"))
from data_fetching import resolve_data_ids, fetch_historical_data
from states import DataCollectionState

def fetch_current_values(variables: List[str]) -> Dict[str, Any]:
    """
    Fetch current values for extracted variables via data_collection.

    TODO: Implement exact integration once data_collection is fully tested.

    Expected flow:
    1. Build DataCollectionState with parsed_claims containing variables
    2. Call resolve_data_ids(state) - resolves to FRED/Yahoo/CoinGecko series
    3. Call fetch_historical_data(state) - fetches recent data (7 days)
    4. Extract latest value from state["fetched_data"][variable]["data"][-1]

    For BTC price specifically:
    - Use CoinGecko adapter's _get_coin_metadata("bitcoin") for real-time price
    - Or fetch via Yahoo: BTC-USD ticker
    """
    # Build state with variables as if they were claims
    state = DataCollectionState(
        mode="claim_validation",
        parsed_claims=[
            {"variable_a": var, "variable_b": None}
            for var in variables
        ]
    )

    # Resolve variable names to data IDs
    state = resolve_data_ids(state)

    # Fetch data (will get last N days based on DEFAULT_LOOKBACK_YEARS)
    # TODO: May need to modify data_collection to support shorter lookback
    state = fetch_historical_data(state)

    # Extract latest values
    current_values = {}
    for var, data in state.get("fetched_data", {}).items():
        if data.get("data"):
            latest = data["data"][-1]  # (date, value) tuple
            current_values[var] = {
                "value": latest[1],
                "date": latest[0],
                "source": data.get("source")
            }

    return current_values
```

### 3. Calling LLM Models
```python
# In impact_analysis.py
import sys
sys.path.append(str(Path(__file__).parent.parent))
from models import call_claude_sonnet

response = call_claude_sonnet(prompt, system_prompt=SYSTEM_PROMPT)
```

### 4. Variable to Data ID Mapping
```python
# NOTE: This is handled by data_collection/data_fetching.py's resolve_data_ids()
# which already loads discovered_data_ids.json and common mappings.
#
# If direct access needed:
DISCOVERED_DATA_IDS = PROJECT_ROOT.parent / "subproject_variable_mapper" / "mappings" / "discovered_data_ids.json"

with open(DISCOVERED_DATA_IDS) as f:
    mappings = json.load(f)

# Look up: mappings["variables"]["tga"]["data_id"] -> "FRED:WTREGEN"
```

---

## Critical Files to Reference

| File | Purpose |
|------|---------|
| `subproject_database_retriever/retrieval_orchestrator.py` | `run_retrieval()` function |
| `subproject_database_retriever/states.py` | RetrieverState structure |
| `subproject_data_collection/data_fetching.py` | `resolve_data_ids()`, `fetch_historical_data()` - **USE THIS** |
| `subproject_data_collection/states.py` | DataCollectionState structure |
| `subproject_variable_mapper/mappings/discovered_data_ids.json` | Variable → data_id mappings (used by data_fetching) |
| `models.py` | `call_claude_sonnet()`, `call_claude_haiku()` |

---

## Implementation Phases

### Phase 1: Core Loop (MVP)
1. `__init__.py` - Package init
2. `__main__.py` - CLI entry point with argparse
3. `states.py` - BTCImpactState definition
4. `config.py` - Paths and settings
5. `btc_impact_orchestrator.py` - Simple sequential workflow (no LangGraph yet)
6. `impact_analysis_prompts.py` - Single impact analysis prompt
7. `impact_analysis.py` - LLM call to generate direction/confidence/rationale/risks

**MVP Output**: Takes query → calls retriever → calls LLM → prints result

### Phase 2: Variable Extraction & Data Fetching
8. `variable_extraction.py` - Parse logic chains, extract normalized variables
9. Integration with `subproject_data_collection` for fetching current values
   - Call `resolve_data_ids()` and `fetch_historical_data()` from data_fetching.py
   - No new adapter code - reuse existing infrastructure

**Phase 2 Output**: Fetches current values for variables mentioned in chains

### Phase 3: Logic Chain Store
10. `relationship_store.py` - JSON CRUD for logic chains
11. Initialize `data/btc_relationships.json`
12. Load historical chains before analysis (for context)
13. Store new chains after analysis (full causal paths)

**Phase 3 Output**: Persistent logic chain database that grows over time, enabling retrieval by any variable in the path

### Phase 4: Polish
14. `CLAUDE.md` - Documentation
15. Error handling and edge cases
16. Verbose/debug output mode

---

## Verification

After implementation, test with:

```bash
# Basic query
python -m subproject_btc_impact "What is the impact of TGA drawdown on BTC?"

# Verify output format - should show:
# - DIRECTION (BULLISH/BEARISH/NEUTRAL)
# - CONFIDENCE (score + chain_count + source_diversity)
# - TIME HORIZON (intraday/days/weeks/months/regime_shift)
# - DECAY PROFILE (fast/medium/slow)
# - RATIONALE
# - RISK FACTORS

# Check relationship storage
cat subproject_btc_impact/data/btc_relationships.json

# Test with different time horizons
python -m subproject_btc_impact "What is the impact of TGA drawdown on BTC?"      # months, slow
python -m subproject_btc_impact "What is the impact of CPI surprise on BTC?"      # days, fast
python -m subproject_btc_impact "What is the impact of ETF approval on BTC?"      # regime_shift, slow
python -m subproject_btc_impact "What is the impact of exchange hack on BTC?"     # intraday, fast
```

---

## Output Format

### CLI Output (Human Readable)
```
============================================================
DIRECTION: BULLISH
CONFIDENCE: 0.72 (3 chains, 2 sources)
TIME HORIZON: weeks-months (slow decay)

RATIONALE:
TGA drawdown releases liquidity into the banking system, which
historically correlates with increased risk appetite and BTC
price appreciation. Current TGA at $350B (declining from $450B)
aligns with the liquidity expansion thesis supported by 3
independent logic chains from Goldman Sachs and UBS research.

STRONGEST CHAIN: tga -> bank_reserves -> risk_appetite -> btc_price

RISK FACTORS:
  - Fed could accelerate QT, offsetting TGA liquidity release
  - Regulatory news could dominate liquidity signal
  - USD strength (DXY > 105) historically dampens BTC response
============================================================
```

### Structured Output (JSON)
```json
{
  "direction": "BULLISH",
  "confidence": {
    "score": 0.72,
    "chain_count": 3,
    "source_diversity": 2,
    "strongest_chain": "tga -> bank_reserves -> risk_appetite -> btc_price"
  },
  "time_horizon": "months",
  "decay_profile": "slow",
  "rationale": "TGA drawdown releases liquidity...",
  "risk_factors": [
    "Fed could accelerate QT, offsetting TGA liquidity release",
    "Regulatory news could dominate liquidity signal",
    "USD strength (DXY > 105) historically dampens BTC response"
  ]
}
```

### Time Horizon Categories

| Category | Duration | Example Catalysts | Decay |
|----------|----------|-------------------|-------|
| `intraday` | Hours | Exchange hack, flash crash | Fast |
| `days` | 1-7 days | CPI surprise, FOMC reaction | Fast |
| `weeks` | 1-4 weeks | ETF flow trends, earnings season | Medium |
| `months` | 1-6 months | TGA drawdown, QT pace change | Slow |
| `regime_shift` | 6+ months | ETF approval, regulatory clarity, halving | Slow |

---

## Future Work (Out of Scope for MVP)

These are valid requirements for a full allocation system but are **not part of this module's scope**.

### Gap: Multi-Query Aggregation Layer

**Problem**: BTC allocation is driven by many simultaneous forces (liquidity, rates, USD, regulation, equity beta, crypto-native flows). This module answers "What is the impact of X on BTC?" but allocation requires "Given ALL active forces, what is BTC's net expected return & risk?"

**Solution (Future)**: Build an **Aggregator/Orchestrator** layer that:
1. Runs multiple BTC impact queries in parallel
2. Combines signals with conflict resolution
3. Weights by time horizon and confidence
4. Outputs net directional view

```
BTC Impact: "TGA drawdown"     → BULLISH (0.72, months, slow)
BTC Impact: "DXY strength"     → BEARISH (0.65, weeks, medium)
BTC Impact: "ETF outflows"     → BEARISH (0.55, days, fast)
                    ↓
            Aggregator Layer
                    ↓
Net BTC View: NEUTRAL-BULLISH (0.58, conflicting signals)
```

**Why deferred**: Requires multiple asset modules first. BTC module is the foundation.

---

### Gap: Impact → Position Size Translation

**Problem**: Even a perfect directional call doesn't imply position size. Missing: base BTC exposure, risk budget, conviction scaling, correlation with other assets.

**Solution (Future)**: Build a **Portfolio Constructor** that:
1. Takes directional signals from asset modules
2. Applies risk budget constraints
3. Considers cross-asset correlations
4. Outputs actual position sizes (% of portfolio)

```
BTC Signal: BULLISH (0.72)
Risk Budget: 2% daily VaR
Correlation: BTC-SPX = 0.6
                    ↓
        Portfolio Constructor
                    ↓
Position: BTC = 5% of portfolio (reduced due to SPX correlation)
```

**Why deferred**: Requires risk models, correlation data, and portfolio context that don't exist yet.

---

### Dependency Chain

```
[BTC Impact Module]  ← YOU ARE HERE
        ↓
[Other Asset Modules: ETH, SPX, Gold, etc.]
        ↓
[Multi-Signal Aggregator]
        ↓
[Portfolio Constructor / Position Sizer]
        ↓
[Execution Layer]
```

Each layer builds on the previous. BTC Impact Module is the **foundation**.
