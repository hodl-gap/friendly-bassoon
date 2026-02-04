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
├── historical_event_detector.py     # Gap detection + instrument mapping (Phase 4)
├── historical_event_prompts.py      # LLM prompts for historical detection (Phase 4)
├── historical_data_fetcher.py       # Fetch historical data + metrics (Phase 4)
│
├── data/
│   └── btc_relationships.json       # Persistent chain storage (Phase 3)
│
└── CLAUDE.md                        # This file
```

### Workflow (Phase 4 - Complete)
```
query (CLI input)
    │
    ▼
┌─────────────────────────┐
│ 1. retrieve_context     │  Call run_retrieval(query) from database_retriever
│                         │  Extract logic_chains from retrieved_chunks
│                         │  + parse_logic_chains_from_answer() for Stage 1 chains
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
│ 5.5 enrich_historical   │  Detect if query references historical event
│     _event              │  If gap detected:
│                         │    - identify_instruments() from synthesis
│                         │    - get_date_range() via web search
│                         │    - fetch_historical_event_data() from Yahoo/FRED
│                         │    - compare_to_current() for "Then vs Now"
│                         │  Output: historical_event_data in state
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 6. analyze_impact       │  LLM call with:
│                         │    - Retrieved answer/synthesis
│                         │    - Logic chains + current data
│                         │    - Historical chains context
│                         │    - Validated patterns (triggered status)
│                         │    - Historical event comparison (if detected)
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

# Historical event comparison (triggers Phase 4 detection)
python -m subproject_btc_intelligence "Compare current market to March 2020 COVID crash"
python -m subproject_btc_intelligence "What happened in August 2024 yen carry crash?"
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
| Phase 4: Historical Event Detection | ✅ Done | Detect historical event gaps, fetch actual market data |
| Phase 5: Polish | Pending | Error handling, enhancements |

## Historical Event Detection (Phase 4)

### Problem
When user asks about historical events (e.g., "August 2024 yen carry crash", "March 2020 COVID crash"), the retriever finds research that *mentions* these events qualitatively, but lacks actual historical prices, correlations, and magnitudes.

### Solution
Detect historical event gaps → Identify relevant instruments → Fetch actual data → Calculate metrics → Feed to LLM

### Flow
```
Query: "Compare current market to March 2020 COVID crash"
    │
    ▼
[1] detect_historical_gap()
    ├─ Regex pre-filter: temporal keywords ("compare", "2020", "crash")
    ├─ LLM (Haiku): Confirms gap exists
    └─ → gap_detected = True, event_description = "March 2020 COVID crash"
    │
    ▼
[2] identify_instruments()
    ├─ Input: retrieval_synthesis + logic_chains
    ├─ LLM extracts instruments MENTIONED in research context
    └─ → [^GSPC, ^VIX, BTC-USD, ^TNX, GC=F, ^IXIC]
    │
    ▼
[3] get_date_range()
    ├─ Web search: "March 2020 COVID crash exact dates"
    ├─ LLM (Haiku): Extract dates from search results
    └─ → 2020-02-23 to 2020-04-07 (with buffer)
    │
    ▼
[4] fetch_historical_event_data()
    ├─ Yahoo Finance API for each instrument
    └─ Calculate metrics:
       - Peak-to-trough drawdown %
       - Peak/trough dates
       - Recovery days (50% recovery)
       - Max single-day move %
       - Pairwise correlations (BTC vs VIX, BTC vs SP500)
    │
    ▼
[5] compare_to_current()
    └─ "Current move (-0.7%) much smaller than historical (-28.5%)"
    │
    ▼
[6] analyze_impact() receives historical comparison section
```

### Configuration (`config.py`)
```python
ENABLE_HISTORICAL_EVENT_DETECTION = True  # Toggle feature
HISTORICAL_DATE_BUFFER_DAYS = 7           # Days buffer around event
MAX_INSTRUMENTS_PER_EVENT = 6             # Limit instruments fetched
```

### Output Format (added to impact analysis prompt)
```
## HISTORICAL EVENT COMPARISON (Data-Driven)

**Event:** March 2020 COVID crash
**Period:** 2020-02-23 to 2020-04-07

**What the DATA shows:**
- SP500: -28.5% (peak 2020-02-19, trough 2020-03-23)
- VIX: +158.5% (peak 2020-03-16, trough 2020-02-19)
- BTC: -45.5% (peak 2020-02-14, trough 2020-03-13)

**Correlations during event:**
- BTC vs SP500: 0.82
- BTC vs VIX: -0.84

**Then vs Now:**
- SP500: Current move (-0.7%) much smaller than historical (-28.5%)
- BTC: Current move (-15.4%) smaller than historical (-45.5%)
```

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `detect_historical_gap()` | `historical_event_detector.py` | Regex + LLM to detect if query needs historical data |
| `identify_instruments()` | `historical_event_detector.py` | LLM extracts instruments from synthesis/chains |
| `get_date_range()` | `historical_event_detector.py` | Web search + LLM for event dates |
| `fetch_historical_event_data()` | `historical_data_fetcher.py` | Fetch from Yahoo/FRED, calculate metrics |
| `compare_to_current()` | `historical_data_fetcher.py` | Compare historical vs current values |
| `format_historical_data_for_prompt()` | `historical_data_fetcher.py` | Format for LLM prompt |
| `parse_logic_chains_from_answer()` | `btc_impact_orchestrator.py` | Extract chains from Stage 1 answer text |
| `enrich_with_historical_event()` | `btc_impact_orchestrator.py` | Step 5.5 orchestration |

### Temporal Keywords Detected
```
"what happened", "during the X 2024", "in August 2024",
"2024 crash", "crash in 2024", "previous crash",
"compare to 2020", "like in 2020"
```

### Cost
~$0.001 per query when gap detected (zero when no gap)

## Dependencies

### Sibling Subprojects
- `subproject_database_retriever` - Provides `run_retrieval()` function
- `subproject_data_collection` - Provides `WebSearchAdapter` for historical date lookup (Phase 4)

### Parent Directory
- `models.py` - AI model functions (`call_claude_sonnet`, `call_claude_haiku`)
- `.env` - API keys (FRED_API_KEY required)

### External APIs
- **FRED API** - Federal Reserve Economic Data (TGA, SOFR, reserves, Fed BS)
- **Yahoo Finance** - Market data (BTC, ETH, DXY, VIX, etc.) via `yfinance`
- **DuckDuckGo** - Web search for historical event dates (via WebSearchAdapter)

## Notes for AI Assistants
- **Follow established patterns** from other subprojects
- **Main file = orchestration only** - no business logic
- **Prompts in separate files** - `*_prompts.py`
- **AI calls via parent's `models.py`**
- **CRITICAL: DO NOT OVERCOMPLICATE** - Keep it minimal and focused
