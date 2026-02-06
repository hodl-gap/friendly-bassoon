# BTC Intelligence Subproject - Claude Context

## Project Overview
This subproject analyzes the impact of **specific macro events or data updates** on Bitcoin price. Given a current event, it retrieves relevant logic chains, finds similar historical analogs, and produces directional assessments with confidence scores.

## Core Purpose

**Input**: A specific event or data update happening NOW (or hypothetically)
**Output**: BTC directional impact (BULLISH/BEARISH/NEUTRAL) with confidence and rationale

### What BTC Intelligence Does
- Takes a **specific event/data update** as input
- Retrieves logic chains explaining the causal mechanism (event → ... → BTC)
- Finds **similar historical events** referenced in research
- Fetches **actual data from historical analogs** to ground predictions
- Fetches **current data for same instruments** to compare "then vs now"
- **Extrapolates** past logic chains to predict current BTC impact

### What BTC Intelligence Does NOT Do
- Answer "what happened in X?" questions (that's the Retriever's job)
- General market comparisons without specific events
- Explain mechanisms without directional output

### Valid Query Examples
```
"TGA increased +10% this week, what's the BTC impact?"
"A new global contagion is spreading, what's the BTC impact?"
"JPY strengthened 12% rapidly, what's the BTC impact?"
"Fed just announced 50bps emergency rate cut, what's the BTC impact?"
```

### Invalid Query Examples
```
"What happened in August 2024 yen crash?" → Use Retriever
"Compare current market to March 2020" → Too vague, no specific event
"Explain how TGA affects liquidity" → Use Retriever
```

## Technology Stack
- **Input**: Specific event/data update → BTC impact question
- **Retrieval**: Uses `subproject_database_retriever` for logic chains
- **Historical Analog**: Fetches actual data from similar past events
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
# Current data update → BTC impact
python -m subproject_btc_intelligence "TGA increased +10% this week, what's the BTC impact?"
python -m subproject_btc_intelligence "Fed just cut rates 50bps, what's the BTC impact?"
python -m subproject_btc_intelligence "DXY strengthened 5% this month, what's the BTC impact?"

# Current event with historical analog (triggers Phase 4)
python -m subproject_btc_intelligence "A new global contagion is spreading, what's the BTC impact?"
python -m subproject_btc_intelligence "JPY is strengthening rapidly like in August 2024, what's the BTC impact?"

# JSON output
python -m subproject_btc_intelligence --json "Bank reserves dropped 5%, what's the BTC impact?"

# Verbose mode
python -m subproject_btc_intelligence -v "VIX spiked to 40, what's the BTC impact?"
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
| Phase 5: Knowledge Gap Filling | ✅ Done | Detect gaps, fill via web search (Tavily) or data computation |
| Phase 6: Web Chain Extraction | ✅ Done | Extract logic chains from trusted web sources when topic not covered |

## Historical Event Detection (Phase 4)

### Purpose
When user asks about a **CURRENT event**, the system finds **similar historical analogs** in the research, fetches **actual data from those past events**, and **extrapolates** the logic chains to predict current BTC impact.

### Problem
User asks: "A new contagion is spreading, what's the BTC impact?"
- Retriever finds research that mentions **COVID 2020** as a similar historical analog
- Research explains the logic chains qualitatively (contagion → risk-off → BTC sell)
- But research lacks **actual historical prices** (BTC dropped 45%, VIX spiked 158%)
- Without actual data, LLM can't ground predictions ("last time this happened, BTC dropped X%")

### Solution
1. Detect when retrieved research **references a historical analog**
2. Fetch **actual data from that historical event** (prices, correlations, magnitudes)
3. Fetch **current data for same instruments** (to compare "then vs now")
4. **Extrapolate** logic chains: "Last time contagion spread, VIX spiked before BTC crashed. Current VIX is X, suggesting..."

### Flow
```
Query: "A new global contagion is spreading, what's the BTC impact?"
    │
    ▼
[1] retrieve_context()
    └─ Finds research mentioning "COVID 2020" as similar historical event
    │
    ▼
[2] detect_historical_gap()
    ├─ Research mentions COVID but lacks actual 2020 price data
    └─ → gap_detected = True, analog = "March 2020 COVID crash"
    │
    ▼
[3] identify_instruments()
    ├─ From research: VIX, SP500, BTC mentioned in COVID context
    └─ → [^GSPC, ^VIX, BTC-USD, ^TNX, GC=F]
    │
    ▼
[4] get_date_range()
    └─ → 2020-02-23 to 2020-04-07
    │
    ▼
[5] fetch_historical_event_data()
    ├─ Historical (March 2020): BTC -45%, VIX +158%, SP500 -28%
    └─ Correlations: BTC vs SP500: 0.82, BTC vs VIX: -0.84
    │
    ▼
[6] fetch_current_data() [already done in Step 4]
    └─ Current: BTC -15%, VIX +5%, SP500 -0.7%
    │
    ▼
[7] compare_to_current()
    └─ "Current VIX (+5%) much smaller than COVID analog (+158%)"
    └─ "If VIX approaches COVID levels, expect BTC to drop similarly"
    │
    ▼
[8] analyze_impact()
    └─ Extrapolates: "Based on COVID analog where BTC dropped 45% with 0.82
       SP500 correlation, current contagion could trigger similar risk-off.
       However, current stress indicators (VIX +5%) are far below COVID levels
       (+158%), suggesting impact may be more muted unless stress escalates."
```

### Key Insight: Extrapolation Logic
The system should identify **leading indicators** from historical analogs:
- "In COVID, VIX spiked BEFORE BTC crashed"
- "In COVID, option spreads widened BEFORE the crash"
- Then check: "What are current VIX / option spreads?" to predict if similar pattern developing

### Configuration (`config.py`)
```python
ENABLE_HISTORICAL_EVENT_DETECTION = True  # Toggle feature
HISTORICAL_DATE_BUFFER_DAYS = 7           # Days buffer around event
MAX_INSTRUMENTS_PER_EVENT = 6             # Limit instruments fetched
```

### Output Format (added to impact analysis prompt)
```
## HISTORICAL ANALOG: March 2020 COVID Crash
**Period:** 2020-02-23 to 2020-04-07

**What happened in the analog:**
- BTC: -45.5% (peak 2020-02-14, trough 2020-03-13)
- SP500: -28.5% (peak 2020-02-19, trough 2020-03-23)
- VIX: +158.5% (peak 2020-03-16, trough 2020-02-19)

**Correlations during analog:**
- BTC vs SP500: 0.82 (moved together)
- BTC vs VIX: -0.84 (inverse relationship)

**Then vs Now (same instruments):**
- VIX: Then +158.5% → Now +5.8% (stress much lower)
- SP500: Then -28.5% → Now -0.7% (drawdown much smaller)
- BTC: Then -45.5% → Now -15.6% (decline smaller)

**Extrapolation:**
Current stress indicators far below COVID levels. If VIX approaches 80+
(COVID peak), expect BTC drawdown to approach -45% range.
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

### Gap Detection Triggers
The system detects historical analog gaps when:
1. Retrieved research **references a past event** (e.g., "similar to COVID 2020", "like the 2024 yen crash")
2. Research explains **logic chains qualitatively** but lacks **actual prices/data**
3. User's query involves a **current event** that maps to the historical reference

**Keywords in research that trigger detection:**
```
"similar to [year]", "like in [year]", "reminiscent of",
"[year] analog", "comparable to [event]", "last time this happened"
```

### Cost
~$0.001 per query when gap detected (zero when no gap)

## Knowledge Gap Filling (Phase 5)

### Purpose
Before the main impact analysis, detect what information is missing and fill gaps using the appropriate method:
- **Web search** (Tavily) — for facts we can't compute: dates, analyst targets, event schedules
- **Data fetch** (Yahoo/FRED) — for quantifiable data: correlations, drawdowns, price changes

### Gap Categories & Fill Methods

| Category | fill_method | What it searches for |
|----------|------------|---------------------|
| historical_precedent_depth | web_search | Event DATES only (we compute BTC impact ourselves) |
| quantified_relationships | data_fetch | Fetches instruments, computes correlation from price data |
| monitoring_thresholds | web_search | Analyst targets, intervention levels, price forecasts |
| event_calendar | web_search | Meeting dates, economic calendar |
| mechanism_conditions | web_search | Preconditions for causal mechanism |
| exit_criteria | web_search | Thesis resolution conditions |

### Key Design Principle
**Do not ask the web for things we can compute.** Correlations, drawdowns, and price reactions are computed from our own data adapters (Yahoo Finance, FRED). Web search is reserved for facts not derivable from price data: dates, announcements, analyst opinions, policy decisions.

### Configuration (`config.py`)
```python
ENABLE_GAP_FILLING = True       # Toggle gap filling
MAX_GAP_SEARCHES = 6            # Max web searches per query
MAX_ATTEMPTS_PER_GAP = 2        # Primary + 1 refinement per gap
```

### Search Backend
- **Tavily API** (default) — returns full page content, `topic="finance"`, ~$0.005/search
- **DuckDuckGo** (fallback) — free, snippets only, poor quality for financial queries
- Backend configured via `WEB_SEARCH_BACKEND` in `subproject_data_collection/config.py`

### Cost
~$0.035 per query with Tavily (6 searches + 6 Haiku extractions + 1 gap detection)

## Web Chain Extraction from Trusted Sources (Phase 6)

### Purpose
When retrieval finds **no relevant chunks** for a topic (e.g., "AI CAPEX impact on tech stocks"), search trusted web sources and extract logic chains on-the-fly.

### Trusted Domain Filtering
Only extract from verified financial institutions:

| Tier | Sources |
|------|---------|
| **Tier 1** | Goldman Sachs, Morgan Stanley, JPMorgan, BofA, Citi, UBS, Bloomberg, Reuters, FT, WSJ, Fed, ECB, BOJ, Bridgewater, BlackRock, VanEck, ARK Invest, Fundstrat, Yardeni |
| **Tier 2** | MarketWatch, CNBC, Economist, Grayscale, Glassnode, CryptoQuant, CoinDesk (optional, configurable) |

### Flow
```
Query → Retrieval → [LOW COVERAGE: match_ratio < 0.3]
                          ↓
           detect_topic_coverage() returns needs_web_chain_extraction=True
                          ↓
           fill_gaps_with_web_chains() in knowledge_gap_detector.py
                          ↓
           WebSearchAdapter.search_and_extract_chains()
             - Filter to trusted domains only
             - Extract chains with cause/effect/mechanism/evidence_quote
             - Verify quotes appear verbatim in source
                          ↓
           merge_web_chains_with_db_chains() (web=0.7 weight, db=1.0 weight)
                          ↓
           Impact Analysis with merged chains
```

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `search_and_extract_chains()` | `web_search_adapter.py` | Search + filter + extract chains |
| `fill_gaps_with_web_chains()` | `knowledge_gap_detector.py` | Orchestrate web chain extraction |
| `merge_web_chains_with_db_chains()` | `knowledge_gap_detector.py` | Merge with confidence weighting |
| `is_trusted_domain()` | `trusted_domains.py` | Check if URL is from trusted source |
| `filter_to_trusted_sources()` | `trusted_domains.py` | Filter search results to trusted only |

### Configuration (`subproject_data_collection/config.py`)
```python
ENABLE_WEB_CHAIN_EXTRACTION = True   # Toggle feature
TRUSTED_DOMAIN_MIN_TIER = 1          # 1 = Tier 1 only, 2 = include Tier 2
MAX_WEB_CHAINS_PER_QUERY = 5         # Limit chains per query
MIN_TRUSTED_SOURCES = 2              # Minimum sources required
WEB_CHAIN_CONFIDENCE_WEIGHT = 0.7    # Weight vs DB chains (1.0)
```

### Output Format (per chain)
```json
{
  "cause": "AI boom and need for advanced AI models",
  "effect": "Data center capex investment increases",
  "mechanism": "Companies must build infrastructure to support AI",
  "polarity": "positive",
  "evidence_quote": "VERBATIM quote from source (verified)",
  "source_name": "Goldman Sachs",
  "source_url": "https://...",
  "confidence": "high",
  "quote_verified": true,
  "source_type": "web",
  "confidence_weight": 0.7
}
```

### Graceful Degradation
- Feature disabled → proceed with DB chains only
- No trusted sources found → proceed with DB chains only
- Extraction fails → proceed with DB chains only
- Web chains are **transient** (not persisted to Pinecone)

### Cost
~$0.01 per web chain extraction query (1 Tavily search + 1 Haiku extraction)

## Dependencies

### Sibling Subprojects
- `subproject_database_retriever` - Provides `run_retrieval()` function, `detect_topic_coverage()`
- `subproject_data_collection` - Provides `WebSearchAdapter` for web search (Phase 4, 5, 6), `trusted_domains` for source filtering

### Parent Directory
- `models.py` - AI model functions (`call_claude_sonnet`, `call_claude_haiku`)
- `.env` - API keys (FRED_API_KEY, TAVILY_API_KEY required)

### External APIs
- **FRED API** - Federal Reserve Economic Data (TGA, SOFR, reserves, Fed BS)
- **Yahoo Finance** - Market data (BTC, ETH, DXY, VIX, etc.) via `yfinance`
- **Tavily** - Web search for knowledge gap filling (via WebSearchAdapter)

## TODO

- **Gap detection prompt examples are JPY/BOJ-specific** (`knowledge_gap_prompts.py`): The GOOD/BAD search query examples in categories 1 (historical_precedent_depth), 3 (monitoring_thresholds), and 6 (exit_criteria) are all from the JPY carry trade case study. Run 2-3 different query types (e.g., TGA, Fed rate cut, DXY) through the pipeline first. If the gap detector generates poor queries for those, diversify the examples using validated results from those runs.

## Notes for AI Assistants
- **Follow established patterns** from other subprojects
- **Main file = orchestration only** - no business logic
- **Prompts in separate files** - `*_prompts.py`
- **AI calls via parent's `models.py`**
- **CRITICAL: DO NOT OVERCOMPLICATE** - Keep it minimal and focused
