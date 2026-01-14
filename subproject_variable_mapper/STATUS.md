# Project Status - Variable Extractor & Mapper

**Last Updated**: 2026-01-14

## Current State: 4-Step Pipeline Complete + Auto-Discovery

All 4 steps implemented. Data ID discovery uses Claude Agent SDK for dynamic source finding.
**Auto-discovery enabled by default** - pipeline automatically discovers data sources for unmapped variables.

---

## Project Purpose

**The Variable Extractor & Mapper** translates text-based logic into data queries.

When the Retriever pulls a chain like `TGA up → Liquidity down`, this module scans the text for measurable entities.

---

## 4-Step Process

### Step 1: Variable Extraction (DONE)

**Goal:** Extract WHAT variables are mentioned in the synthesis text.

**Input:**
```
"QT reduction + TGA drawdown + Fed cuts → December liquidity surge"
```

**Output:** List of variable names found:
- QT
- TGA
- Fed funds rate
- Liquidity (system reserves)

**Key:** Just identify measurable entities. No Data IDs yet.

**Reference:** Use `liquidity_metrics_mapping.csv` as a dictionary of known metrics for normalization.

---

### Step 2: Normalize Variables (DONE)

**Goal:** Match extracted variables against `liquidity_metrics_mapping.csv` to get canonical names.

**Input:** Raw extracted names
- "Treasury General Account"
- "short rates"

**Output:** Normalized names
- `TGA`
- `fed_funds_rate` or `US02Y`

---

### Step 3: Identify Missing Variables (DONE)

**Goal:** Analyze the logic chain to find variables required for prediction but not provided by user.

**Example:**
- User asked about: TGA
- Chain says: `TGA down → Liquidity pressure → FCI tightens → Risk-off`
- **FCI is in the chain but user didn't provide it** → Mark as "missing required"

---

### Step 4: Map to Data IDs (DONE + AUTO-DISCOVERY)

**Goal:** Only after we know WHAT is needed, figure out WHERE to get it.

**Input:** Normalized variable name `TGA`

**Output:** Full mapping with API URL and details:
```json
{
  "data_id": "FRED:WTREGEN",
  "api_url": "https://api.stlouisfed.org/fred/series/observations?series_id=WTREGEN&api_key=YOUR_API_KEY",
  "description": "Treasury General Account...",
  "frequency": "weekly",
  "notes": "..."
}
```

**Implementation:**
- First checks `mappings/discovered_data_ids.json` for cached mappings
- If unmapped variables exist, **auto-triggers discovery** (Claude Agent SDK)
- Validates by pinging APIs (FRED, World Bank, BLS)
- Saves new mappings to JSON for future reuse
- Full debug logs saved to `logs/discovery_YYYYMMDD_HHMMSS.log`

---

## Core Tasks Summary

1. **Identify key variables** in the chain (e.g., "TGA", "FCI", "Short rates") - DONE
2. **Normalize variables** using `liquidity_metrics_mapping.csv` - DONE
3. **Identify missing variables** - If user provided "TGA" but the chain requires "FCI" to make a prediction, mark "FCI" as a required data fetch - DONE
4. **Map variables to Data IDs** (e.g., TGA = `FRED:WTREGEN`) via Claude Agent SDK discovery - DONE

---

## Input / Output

### Sample Input File

**Location**: `subproject_database_retriever/tests/query_result.md`

This file contains a real example of retriever output with:
- STAGE 1: Logic chains extracted from sources
- STAGE 2: Synthesis with consensus conclusions and key variables to monitor

### Input Format (from database_retriever)

The input contains two main sections:

**STAGE 1 - Logic Chains:**
```
**CHAIN:** Fed rate cuts → short rates down → curve steepening → flows to duration/credit/alternatives
**MECHANISM:** easing lowers short-term rates → long rates remain sticky creating steeper curve → cash rollover less attractive driving reallocation
**SOURCE:** Source 7 (Franklin Templeton)

**CHAIN:** QT reduction + TGA drawdown + Fed cuts → December liquidity surge → year-end risk-on rally
**MECHANISM:** multiple liquidity sources converge → increases system reserves and funding availability → amplifies equity demand into year-end
**SOURCE:** Source 9 (GS)
```

**STAGE 2 - Synthesis (Key Variables to Monitor):**
```
**Liquidity Metrics:**
- QT reduction magnitude and timing
- TGA (Treasury General Account) drawdown schedule
- System reserves levels
- Financial Conditions Index (FCI) levels and troughs

**Yield Curve Dynamics:**
- Short-term rate levels post-cut
- Long-term real yield stickiness
- 10-year Treasury yield direction

**Critical Thresholds Identified:**
- Jobs sentiment "plentiful": 28% (down from 57% peak)
- December cut probability: 87%
- Dollar decline: -10% YTD
- CPI target: 2%
```

### Output (Structured JSON with Full API Details)

The output includes **complete data source details** for downstream data fetching:

```json
{
  "variables": [
    {
      "raw_name": "TGA",
      "normalized_name": "tga",
      "category": "direct",
      "type": "needs_registration",
      "data_id": "FRED:WTREGEN",
      "source": "FRED",
      "description": "Treasury General Account - U.S. Treasury deposits held at Federal Reserve Banks...",
      "api_url": "https://api.stlouisfed.org/fred/series/observations?series_id=WTREGEN&api_key=YOUR_API_KEY&file_type=json",
      "frequency": "weekly",
      "notes": "Free API but requires registration for API key...",
      "registration_url": "https://fred.stlouisfed.org/docs/api/api_key.html",
      "validated": true
    },
    {
      "raw_name": "VIX",
      "normalized_name": "vix",
      "type": "api",
      "data_id": "FRED:VIXCLS",
      "source": "FRED",
      "description": "CBOE Volatility Index (VIX) - measures market expectation of near-term volatility...",
      "api_url": "https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key=YOUR_API_KEY&file_type=json",
      "frequency": "daily",
      "validated": true
    },
    {
      "raw_name": "WDI",
      "normalized_name": "wdi",
      "type": "api",
      "data_id": "WorldBank:WDI",
      "source": "WorldBank",
      "api_url": "https://api.worldbank.org/v2/country/all/indicator/{INDICATOR_CODE}?format=json",
      "example_indicators": {
        "gdp": "NY.GDP.MKTP.CD",
        "population": "SP.POP.TOTL"
      }
    }
  ],
  "unmapped_variables": ["unknown_metric"],
  "missing_variables": ["fci", "yield_curve"],
  "dependencies": [
    {"from": "tga", "to": "liquidity", "relationship": "causes"}
  ]
}
```

**Key fields for data fetching:**
- `api_url` - Ready-to-use endpoint (replace YOUR_API_KEY with actual key)
- `description` - What this metric measures
- `notes` - Usage notes, units, data availability
- `frequency` - daily/weekly/monthly/annual
- `example_indicators` - For collection-type sources (e.g., World Bank WDI)

---

## Variable to Data ID Mapping

### Known Mappings (Initial Set)

| Variable | Data ID | Source | Description |
|----------|---------|--------|-------------|
| TGA | `FRED:WTREGEN` | FRED | Treasury General Account |
| RRP | `FRED:RRPONTSYD` | FRED | Overnight Reverse Repo |
| Fed Balance Sheet | `FRED:WALCL` | FRED | Total Assets |
| Reserves | `FRED:TOTRESNS` | FRED | Total Reserves |
| US02Y | `FRED:DGS2` | FRED | 2-Year Treasury |
| US10Y | `FRED:DGS10` | FRED | 10-Year Treasury |
| FCI | `BLOOMBERG:GSFCI` | Bloomberg | Goldman Financial Conditions Index |
| SOFR | `FRED:SOFR` | FRED | Secured Overnight Financing Rate |
| VIX | `CBOE:VIX` | CBOE | Volatility Index |
| DXY | `ICE:DXY` | ICE | US Dollar Index |

*This mapping will grow as we encounter more variables in logic chains.*

---

## Architecture

```
subproject_variable_mapper/
├── variable_mapper_orchestrator.py  # MAIN - LangGraph orchestration
├── states.py                        # LangGraph state definitions
├── config.py                        # Configuration (AUTO_DISCOVER=True)
│
│  # 4-Step Pipeline
├── variable_extraction.py           # Step 1: Extract variables from text
├── variable_extraction_prompts.py
├── normalization.py                 # Step 2: Normalize to canonical names
├── normalization_prompts.py
├── missing_variable_detection.py    # Step 3: Find missing chain variables
├── missing_variable_detection_prompts.py
├── data_id_mapping.py               # Step 4: Map to Data IDs (auto-discovers)
│
│  # Data ID Discovery
├── data_id_discovery.py             # Claude Agent SDK discovery
├── data_id_discovery_prompts.py
├── data_id_validation.py            # API ping validation
│
├── mappings/
│   └── discovered_data_ids.json     # Cached data ID mappings
├── logs/                            # Debug logs (timestamped)
│   └── discovery_YYYYMMDD_HHMMSS.log
└── tests/                           # Test files
```

---

## Workflow

```
Input (Retriever Synthesis)
    │
    ▼
┌─────────────────────────┐
│  Step 1: Extraction     │  ← Extract variable mentions from text
│  (variable_extraction)  │     "TGA", "FCI", "short rates", etc.
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 2: Normalization  │  ← Match to canonical names
│  (normalization)        │     "Treasury General Account" → "tga"
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 3: Missing Vars   │  ← Find chain variables not provided
│  (missing_variable_det) │     Chain needs FCI but user didn't provide
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 4: Data ID Map    │  ← Look up or discover data sources
│  (data_id_mapping)      │     TGA → FRED:WTREGEN + full API details
└──────────┬──────────────┘
           │
           ├── If unmapped variables exist:
           │   ┌─────────────────────────┐
           │   │  AUTO-DISCOVERY         │  ← Claude Agent SDK
           │   │  (data_id_discovery)    │     Web search → API validation
           │   └─────────────────────────┘
           │
           ▼
Output (Structured JSON with Full API Details)
```

---

## TODO / Next Steps

### Priority 0: Clean Up Liquidity Metrics Mapping (BLOCKER)

- [ ] **Review and clean `liquidity_metrics_mapping.csv`** (in `subproject_database_manager`)
- [ ] Add missing common metrics (Fed funds rate, yield curve terms, VIX, DXY, etc.)
- [ ] Improve variant coverage (Korean/English aliases)
- [ ] Add "measurable" flag for data-fetchable metrics
- [ ] Validate categories (direct/indirect classification)

> **Why blocker?** Step 2 (Normalization) depends on this CSV as the canonical reference dictionary. Without a clean mapping file, variable normalization will fail.

---

### Phase 1: Foundation & Step 1 (DONE)

- [x] Create CLAUDE.md
- [x] Create STATUS.md
- [x] Create `states.py` with basic state definitions
- [x] Create `config.py` with environment setup
- [x] Implement `variable_mapper_orchestrator.py` skeleton
- [x] Implement `variable_extraction.py` - Extract variables from text
- [x] Create `variable_extraction_prompts.py`
- [ ] Test extraction on sample retriever output (`query_result.md`)

### Phase 2: Normalization (Step 2) (DONE)

- [x] Implement variable normalization using `liquidity_metrics_mapping.csv`
- [x] Handle variants (Korean + English aliases)
- [x] Flag new/unknown variables

### Phase 3: Missing Variable Detection (Step 3) (DONE)

- [x] Implement `missing_variable_detection.py`
- [x] Analyze logic chain dependencies
- [x] Identify variables required but not provided by user

### Phase 4: Data ID Mapping (Step 4) - IMPLEMENTED + AUTO-DISCOVERY

**Implementation:** Claude Agent SDK-based discovery with auto-trigger.

- [x] `data_id_discovery.py` - Discovery function using Claude Agent SDK
- [x] `data_id_discovery_prompts.py` - Agent prompts for data source discovery
- [x] `data_id_validation.py` - API ping validation (FRED, World Bank, BLS)
- [x] `data_id_mapping.py` - Maps variables, auto-triggers discovery for unmapped
- [x] `mappings/discovered_data_ids.json` - Stores discovery results (cached)
- [x] `logs/` - Full debug logs with timestamps
- [x] Full mapping details in output (api_url, description, notes, etc.)

**Auto-Discovery (Default):**
When pipeline runs with unmapped variables, discovery triggers automatically.
Set `AUTO_DISCOVER = False` in config.py to disable.

**Manual Discovery:**
```bash
python data_id_discovery.py -v tga,vix,cpi
```

**Discovery Outcomes:**
- `api` - Found in known API (e.g., FRED:WTREGEN)
- `needs_registration` - Found API but requires registration
- `scrape` - No API, but web scrapable
- `not_found` - No public data source found

**Performance:** ~30-45s per variable, ~$0.10-0.15 cost, cached after first discovery

### Phase 5: Query Builder & Integration

- [ ] Implement `query_builder.py`
- [ ] Generate structured JSON output
- [ ] Connect to database_retriever output
- [ ] End-to-end test with real synthesis data

---

## Dependency: Improve Liquidity Metrics Extraction

**Location:** `subproject_database_manager`

**Issue:** The `liquidity_metrics_mapping.csv` is the reference dictionary for variable normalization. Quality of variable extraction in this subproject depends on:

1. **Coverage** - Does the CSV contain all common financial metrics?
2. **Variants** - Are Korean/English aliases comprehensive?
3. **Categories** - Is direct/indirect classification accurate?

**TODO (in database_manager):**
- [ ] Review and clean up `liquidity_metrics_mapping.csv`
- [ ] Add missing common metrics (Fed funds rate, yield curve terms, etc.)
- [ ] Improve variant coverage for better matching
- [ ] Consider adding a "measurable" flag (can this metric be fetched as data?)

---

## Reminders

### Critical Design Decisions

1. **Variable normalization** - Same variable may appear as "TGA", "Treasury General Account", "treasury balance"
   - Use LLM to normalize to canonical form
   - Reference `liquidity_metrics_mapping.csv` from database_manager for known variants

2. **Data ID sources** - Prioritize free data sources
   - FRED (Federal Reserve Economic Data) - free, comprehensive
   - CBOE (VIX, options) - free quotes available
   - Paid: Bloomberg, Refinitiv (flag these separately)

3. **Missing variable logic** - How to determine if a variable is "required"
   - If variable appears in logic chain but not in user query → required
   - If chain has gap (A → ? → C) → identify missing link

4. **Unknown variables** - Not all variables will have Data ID mappings
   - Output list of unmapped variables for manual resolution
   - Don't fail silently - make gaps visible

### Integration Points

- **Sample Input**: `subproject_database_retriever/tests/query_result.md` - Real example of retriever output
- **Input Source**: `subproject_database_retriever/answer_generation.py` → `synthesis` field
- **Reference**: `subproject_database_manager/data/processed/liquidity_metrics/liquidity_metrics_mapping.csv` for known metric variants
- **AI Models**: Use `models.py` from parent directory (GPT-5 Mini for extraction, Claude fallback)

### Patterns to Follow

- All AI calls via parent's `models.py`
- All prompts in `*_prompts.py` files
- States in `states.py` for LangGraph
- Debug prints: FULL for LLM responses (no truncation), truncated for others
- File logging: All discovery logs saved to `logs/discovery_YYYYMMDD_HHMMSS.log`
- Test files in `tests/` folder

---

## Development Timeline

- **2025-12-10** - Project setup, CLAUDE.md, STATUS.md created

---

## Known Limitations (Anticipated)

1. Initial Data ID mapping will be incomplete - requires iterative expansion
2. Some variables may be qualitative (e.g., "risk sentiment") with no Data ID
3. Bloomberg/Refinitiv data requires paid subscriptions
4. Logic chain analysis for missing variables may need tuning
