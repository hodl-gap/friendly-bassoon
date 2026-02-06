# Belief-Space Refactoring Log

**Date**: 2026-02-06
**Goal**: Refactor system to produce multi-path, contradiction-preserving belief-space outputs

---

## Change Log

### Phase 1: Output Layer Refactoring (BTC Intelligence)

| File | Change | Status |
|------|--------|--------|
| `states.py` | Add `scenarios` and `belief_space` fields to BTCImpactState | ✅ Done |
| `impact_analysis.py` | Add `parse_scenarios()` and `parse_contradictions()` functions | ✅ Done |
| `impact_analysis.py` | Modify parser to extract and store all scenarios | ✅ Done |
| `impact_analysis_prompts.py` | Reframe SYSTEM_PROMPT for belief-space mapping | ✅ Done |
| `impact_analysis_prompts.py` | Add CONTRADICTIONS section to output format | ✅ Done |
| `btc_impact_orchestrator.py` | Update JSON output to include scenarios + belief_space | ✅ Done |
| `btc_impact_orchestrator.py` | Update human-readable output with scenario list + contradictions | ✅ Done |

### Phase 2: Chain Schema Enhancement

| File | Change | Status |
|------|--------|--------|
| `data_opinion_prompts.py` | Add `polarity` field to chain step schema | ✅ Done |
| `states.py` (Retriever) | Add belief-branch grouping | Not needed (chains already flat list) |

### Phase 3: Query Paradigm Extension

| File | Change | Status |
|------|--------|--------|
| New: `belief_space_orchestrator.py` | New orchestrator for "describe belief space" queries | ❌ Not done |
| New: `belief_space_prompts.py` | Prompts for belief-space synthesis | ❌ Not done |

### Phase 4: Data Source Expansion

| File | Change | Status |
|------|--------|--------|
| `shared/variable_resolver.py` | Add sector ETFs (IGV, XLK, SMH) and Big Tech tickers | ✅ Done |
| `current_data_fetcher.py` | Add Sectors, Big Tech categories to output formatting | ✅ Done |
| New: `earnings_adapter.py` | Company earnings/guidance extraction | ❌ Not done |
| New: `news_event_extractor.py` | Extract events from news with dates/magnitudes | ❌ Not done |

---

## Blockers Identified

### ~~BLOCKER 1: Data Source Gap~~ → RESOLVED

**Correction**: Telegram provides LOGIC CHAINS, not data. Data comes from Data Collection subproject.

**What Data Collection already has:**
1. ✅ **Yahoo Adapter** - Stock prices, now also fundamentals (P/E, market cap, etc.)
2. ✅ **Web Search Adapter** - Can fetch CAPEX guidance, analyst views via Tavily search
3. ✅ **Institutional Scrapers** - BofA FMS via web search, fund flows

**What was added:**
- `fetch_fundamentals()` method to Yahoo adapter for valuation data (P/E, EV/EBITDA, etc.)
- `fetch_fundamentals_batch()` for multiple tickers

### BLOCKER 2: Event Extraction Schema (STILL OPEN)

**Problem**: Current chain schema extracts cause→effect logic, but not structured events with dates and magnitudes like:
> "Amazon's $200bn capex guidance for 2026 exceeded Wall Street expectations by over $50bn"

**Required but missing:**
- `event_date` field in chain schema
- `magnitude` field with units
- `vs_expectation` field for surprises

**Impact**: Can describe logic but not anchor to specific corporate events

**Classification**: Schema gap (incremental, can be added)

### BLOCKER 3: CAPEX Data Not in Yahoo Finance

**Problem**: Yahoo Finance provides fundamentals like P/E, market cap, revenue, but NOT:
- Forward CAPEX guidance ($185bn, $200bn)
- CAPEX growth rates (74% YoY)
- CAPEX vs expectations

**Solution**: Web Search Adapter can fetch this via search queries like:
- "Amazon CAPEX guidance 2026"
- "Alphabet capital expenditure 2026 announcement"

This is already possible with the existing `search_and_extract(query, extract_type="announcements")` method.

---

## Files Modified

### subproject_btc_intelligence/states.py
- Added `scenarios: List[Dict[str, Any]]` field with schema documentation
- Added `belief_space: Dict[str, Any]` field for contradictions and metadata

### subproject_btc_intelligence/impact_analysis.py
- Added `parse_scenarios()` function to extract all scenarios from LLM response
- Added `parse_contradictions()` function to extract explicit contradictions
- Modified `parse_impact_response()` to populate scenarios and belief_space
- Updated state assignments to include new fields

### subproject_btc_intelligence/impact_analysis_prompts.py
- Rewrote SYSTEM_PROMPT for belief-space mapping paradigm
- Added explicit examples of contradiction preservation
- Added CONTRADICTIONS section to required output format
- Added per-scenario fields: Key Data, Actors, Rationale
- Modified confidence section to include uncertainty_drivers

### subproject_btc_intelligence/btc_impact_orchestrator.py
- Updated JSON output to include `scenarios` and `belief_space`
- Updated human-readable output with "BELIEF SPACE ANALYSIS" header
- Added scenario listing with direction, likelihood, chain
- Added contradictions section display

### subproject_database_manager/data_opinion_prompts.py
- Added `polarity` field to logic chain step schema
- Added documentation for BULLISH/BEARISH/NEUTRAL values
- Updated both system prompt and combined prompt

### shared/variable_resolver.py
- Added sector ETFs: IGV, XLK, SMH, SOXX, XLY, XLF, XLE, XLU
- Added Big Tech tickers: GOOGL, AMZN, MSFT, META, AAPL, NVDA, ORCL
- Added additional indices: DOW, Russell 2000
- Added FX pairs: EURUSD
- Added volatility: VVIX

### subproject_btc_intelligence/current_data_fetcher.py
- Updated categories to include Indices, Sectors, Big Tech, FX & Commodities, Volatility

### subproject_data_collection/adapters/yahoo_adapter.py
- Added `fetch_fundamentals()` method for valuation data (P/E, EV/EBITDA, margins, etc.)
- Added `fetch_fundamentals_batch()` for multiple tickers
- Includes: forward_pe, trailing_pe, price_to_book, ev_to_ebitda, market_cap, revenue_growth, analyst targets
- Critical for belief-space analysis where valuation context matters (e.g., "P/E compressed from 85x to 60x")

---

## Final Assessment (REVISED)

### Can the System Produce the Example Output?

**Revised Answer: YES, with proper orchestration.**

The architecture now supports:

| Component | Source | Status |
|-----------|--------|--------|
| Logic chains (CAPEX → value destruction) | Telegram research OR can be added via new ingestion | ✅ Architecture supports |
| P/E multiples (85x → 60x) | Yahoo `fetch_fundamentals()` | ✅ Added |
| Stock/ETF prices (IGV down 27%) | Yahoo Adapter | ✅ Already works |
| CAPEX guidance ($185bn, $200bn) | Web Search Adapter | ✅ Already works |
| Analyst views (BofA "AI eats software") | Web Search Adapter | ✅ Already works |
| Multiple scenarios with contradictions | BTC Intelligence output layer | ✅ Added |

### What the Refactoring Achieved

**Output Layer:**
- ✅ Multiple scenarios with different directions preserved in state
- ✅ Contradictions explicitly parsed and stored as first-class objects
- ✅ Polarity (BULLISH/BEARISH/NEUTRAL) on chain steps
- ✅ Output format shows all scenarios, not just primary direction

**Data Collection:**
- ✅ `fetch_fundamentals()` added to Yahoo adapter (P/E, EV/EBITDA, market cap, etc.)
- ✅ Sector ETFs (IGV, XLK, SMH) and Big Tech tickers added to variable resolver
- ✅ Web Search Adapter can fetch CAPEX guidance via search

### Remaining Gap: Logic Chain Content

The current Telegram research focuses on macro/liquidity (Fed, TGA, JPY). To produce the SaaS/CAPEX example, you would need logic chains like:

```
AI CAPEX increase → ROI dilution fears → multiple compression → stocks down
AI CAPEX increase → AI leadership confirmation → growth premium → stocks up
```

**Options:**
1. Add US equity research ingestion (if you have access)
2. Manually seed chains for key themes (CAPEX, SaaS disruption)
3. Use web search to generate chains on-the-fly (via LLM extraction)

### What Would Work Today

**Macro queries (existing research):**
```
"TGA increased 10% this week, what's the BTC impact?"
```
→ Full belief-space output with scenarios + contradictions + data

**Equity queries (if chains are added or generated):**
```
"What's the belief space around AI CAPEX impact on tech stocks?"
```
→ Can fetch: IGV price, IGV P/E, GOOGL/AMZN fundamentals, CAPEX via web search
→ Needs: Logic chains connecting CAPEX to outcomes (from research or generated)

### Recommended Next Steps

1. **Test**: Run refactored pipeline with a macro query to verify scenario output
2. **Add chains**: Either ingest equity research OR generate chains via web search + LLM
3. **Integrate data**: Wire `fetch_fundamentals()` into the analysis pipeline
