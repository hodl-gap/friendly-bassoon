# BTC Intelligence Subproject - Claude Context

## Project Overview
This subproject analyzes the impact of macro events/conditions on Bitcoin price by retrieving relevant logic chains from the research database and producing directional assessments with confidence scores.

## Parent Project Goal
The entire project aims to produce an agentic research workflow. This subproject is specifically for **BTC impact analysis**.

## Technology Stack
- **Input**: User queries about macro → BTC relationships
- **Retrieval**: Uses `subproject_database_retriever` for context
- **Analysis**: Claude Sonnet for impact assessment
- **Output**: Direction, Confidence, Time Horizon, Rationale, Risk Factors
- **Framework**: Simple sequential workflow (LangGraph in future phases)

## Architecture

### Code Organization
```
subproject_btc_intelligence/
├── __init__.py                      # Package exports
├── __main__.py                      # CLI entry point
├── btc_impact_orchestrator.py       # Main workflow
├── states.py                        # BTCImpactState definition
├── config.py                        # Configuration
├── impact_analysis.py               # LLM-based impact analysis
├── impact_analysis_prompts.py       # Analysis prompts
├── variable_extraction.py           # Extract variables from chains (Phase 2)
├── current_data_fetcher.py          # Fetch live data with period changes (Phase 2)
├── pattern_validator.py             # Validate research patterns vs current data (Phase 2)
├── relationship_store.py            # Logic chain persistence (Phase 3)
│
├── data/
│   └── btc_relationships.json       # Persistent chain storage (Phase 3)
│
├── CLAUDE.md                        # This file
└── PLAN.md                          # Implementation plan
```

### Workflow (Phase 3 - Complete)
```
query (CLI input)
    │
    ▼
┌─────────────────────────┐
│ 1. retrieve_context     │  Call run_retrieval(query) from database_retriever
│                         │  Extract logic_chains from retrieved_chunks
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 2. load_chains          │  Load historical chains from btc_relationships.json
│                         │  Find relevant chains for current query
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 3. extract_variables    │  Parse chains/synthesis for variable names
│                         │  Output: [tga, bank_reserves, btc, sofr, ...]
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 4. fetch_current_data   │  Fetch from FRED (TGA, SOFR, etc.)
│                         │  Fetch from Yahoo (BTC, DXY, etc.)
│                         │  Include 1w and 1m period changes
│                         │  Output: {btc: $75K (-15% 1w), tga: $923B (+6% 1w), ...}
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 5. validate_patterns    │  Extract quantitative patterns from research
│                         │  (e.g., "TGA +200% over 3mo → BTC crash")
│                         │  Validate against current data
│                         │  Output: triggered/not-triggered for each pattern
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 6. analyze_impact       │  LLM call with:
│                         │    - Retrieved answer/synthesis
│                         │    - Logic chains + current data
│                         │    - Historical chains context
│                         │    - Validated patterns (triggered status)
│                         │    - Confidence metadata
│                         │  Output: direction, confidence, rationale, risks
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 7. store_chains         │  Extract new chains from answer
│                         │  Deduplicate against existing
│                         │  Save to btc_relationships.json
└───────────┬─────────────┘
            │
            ▼
        Output (CLI display with current values + changes)
```

## Usage

```bash
# Basic query
python -m subproject_btc_intelligence "What is the impact of TGA drawdown on BTC?"

# JSON output
python -m subproject_btc_intelligence --json "What is the impact of Fed rate cuts on BTC?"

# Verbose mode
python -m subproject_btc_intelligence -v "What is the impact of DXY strength on BTC?"
```

## Output Format

### CLI Output
```
============================================================
DIRECTION: BEARISH
CONFIDENCE: 0.75 (4 chains, 3 sources)
TIME HORIZON: weeks (medium decay)

CURRENT DATA:
  **Crypto**:
    - BTC: $75,470.91 (↓$13,714 / -15.4% 1w; ↓$15,556 / -17.1% 1m)
  **Liquidity**:
    - TGA: $923B (↑$54B / +6.2% 1w; ↑$86B / +10.2% 1m)
    - BANK_RESERVES: $2.94T
    - FED_BALANCE_SHEET: $6.59T (↑$3B / +0.0% 1w)
  **Rates**:
    - SOFR: 3.65% (→0.00pp / +0.0% 1w)

RATIONALE:
The TGA has increased +$86B (+10.2%) over the past month to $923B,
representing a liquidity drain from the banking system...

STRONGEST CHAIN: tga_increase -> bank_reserves_drain -> funding_stress -> btc_pressure

RISK FACTORS:
  - Rapid TGA drawdown reversal if Treasury begins spending aggressively
  - Institutional accumulation override at lower BTC prices
  - Fed balance sheet expansion could override Treasury liquidity drain
============================================================
```

### JSON Output
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
  "rationale": "...",
  "risk_factors": ["...", "...", "..."],
  "current_values": {"btc": {...}, "tga": {...}, ...},
  "btc_price": 75470.91
}
```

## Implementation Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: MVP | ✅ Done | Core loop: retrieve → analyze → output |
| Phase 2: Data Fetching | ✅ Done | Fetch current values (FRED, Yahoo) with period changes |
| Phase 2b: Pattern Validation | ✅ Done | Extract & validate research patterns vs current data |
| Phase 3: Chain Store | ✅ Done | Persist discovered logic chains |
| Phase 4: Polish | Pending | Error handling, enhancements |

## Dependencies

### Sibling Subprojects
- `subproject_database_retriever` - Provides `run_retrieval()` function

### Parent Directory
- `models.py` - AI model functions (`call_claude_sonnet`, `call_claude_haiku`)
- `.env` - API keys (FRED_API_KEY required)

### External APIs
- **FRED API** - Federal Reserve Economic Data (TGA, SOFR, reserves, Fed BS)
- **Yahoo Finance** - Market data (BTC, ETH, DXY, VIX, etc.) via `yfinance`

## Notes for AI Assistants
- **Follow established patterns** from other subprojects
- **Main file = orchestration only** - no business logic
- **Prompts in separate files** - `*_prompts.py`
- **AI calls via parent's `models.py`**
- **CRITICAL: DO NOT OVERCOMPLICATE** - Keep it minimal and focused
