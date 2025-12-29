# Project Status - Variable Extractor & Mapper

**Last Updated**: 2025-12-11

## Current State: Initial Setup - Step 1 Implementation

New subproject for translating text-based logic chains into data queries with variable extraction, Data ID mapping, and missing variable identification.

---

## Project Purpose

**The Variable Extractor & Mapper** translates text-based logic into data queries.

When the Retriever pulls a chain like `TGA up → Liquidity down`, this module scans the text for measurable entities.

---

## 4-Step Process

### Step 1: Variable Extraction (CURRENT FOCUS)

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

### Step 2: Normalize Variables

**Goal:** Match extracted variables against `liquidity_metrics_mapping.csv` to get canonical names.

**Input:** Raw extracted names
- "Treasury General Account"
- "short rates"

**Output:** Normalized names
- `TGA`
- `fed_funds_rate` or `US02Y`

---

### Step 3: Identify Missing Variables

**Goal:** Analyze the logic chain to find variables required for prediction but not provided by user.

**Example:**
- User asked about: TGA
- Chain says: `TGA down → Liquidity pressure → FCI tightens → Risk-off`
- **FCI is in the chain but user didn't provide it** → Mark as "missing required"

---

### Step 4: Map to Data IDs (LATER)

**Goal:** Only after we know WHAT is needed, figure out WHERE to get it.

**Input:** Normalized variable name `TGA`

**Output:** Data ID `FRED:WTREGEN`

**Note:** This step requires a separate `variable_data_id_mapping.csv` (to be created later).

---

## Core Tasks Summary

1. **Identify key variables** in the chain (e.g., "TGA", "FCI", "Short rates")
2. **Normalize variables** using `liquidity_metrics_mapping.csv`
3. **Identify missing variables** - If user provided "TGA" but the chain requires "FCI" to make a prediction, mark "FCI" as a required data fetch
4. **Map variables to Data IDs** (e.g., TGA = `FRED:WTREGEN`) - LATER PHASE

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

### Output (Structured JSON)

Example output based on the sample input:

```json
{
  "query_group": "Fed_Rate_Cuts_Equity_Impact",
  "variables": [
    {
      "name": "TGA",
      "normalized_name": "Treasury General Account",
      "data_id": "FRED:WTREGEN",
      "threshold": null,
      "status": "identified"
    },
    {
      "name": "FCI",
      "normalized_name": "Financial Conditions Index",
      "data_id": "BLOOMBERG:GSFCI",
      "threshold": null,
      "status": "identified"
    },
    {
      "name": "Short rates",
      "normalized_name": "2-Year Treasury Yield",
      "data_id": "FRED:DGS2",
      "threshold": null,
      "status": "identified"
    },
    {
      "name": "10-year Treasury yield",
      "normalized_name": "10-Year Treasury Yield",
      "data_id": "FRED:DGS10",
      "threshold": null,
      "status": "identified"
    },
    {
      "name": "System reserves",
      "normalized_name": "Total Reserves",
      "data_id": "FRED:TOTRESNS",
      "threshold": null,
      "status": "identified"
    },
    {
      "name": "DXY",
      "normalized_name": "US Dollar Index",
      "data_id": "ICE:DXY",
      "threshold": -10,
      "threshold_unit": "percent_ytd",
      "status": "identified"
    },
    {
      "name": "CPI",
      "normalized_name": "Consumer Price Index",
      "data_id": "FRED:CPIAUCSL",
      "threshold": 2,
      "threshold_unit": "percent",
      "status": "identified"
    },
    {
      "name": "VIX",
      "normalized_name": "Volatility Index",
      "data_id": "CBOE:VIX",
      "threshold": null,
      "status": "identified"
    },
    {
      "name": "Jobs sentiment plentiful",
      "normalized_name": "Conference Board Jobs Plentiful",
      "data_id": null,
      "threshold": 28,
      "threshold_note": "down from 57% peak",
      "status": "unmapped"
    }
  ],
  "logic_chains_parsed": [
    {
      "chain": "Fed rate cuts → short rates down → curve steepening → flows to duration/credit/alternatives",
      "variables_in_chain": ["Fed funds rate", "Short rates", "Yield curve"]
    },
    {
      "chain": "QT reduction + TGA drawdown + Fed cuts → December liquidity surge → year-end risk-on rally",
      "variables_in_chain": ["QT", "TGA", "Fed funds rate", "System reserves"]
    }
  ],
  "unmapped_variables": ["Jobs sentiment plentiful", "QT reduction magnitude"],
  "data_queries": [
    {"data_id": "FRED:WTREGEN", "variable": "TGA"},
    {"data_id": "BLOOMBERG:GSFCI", "variable": "FCI"},
    {"data_id": "FRED:DGS2", "variable": "Short rates"},
    {"data_id": "FRED:DGS10", "variable": "10-year Treasury yield"},
    {"data_id": "FRED:TOTRESNS", "variable": "System reserves"},
    {"data_id": "ICE:DXY", "variable": "DXY"},
    {"data_id": "FRED:CPIAUCSL", "variable": "CPI"},
    {"data_id": "CBOE:VIX", "variable": "VIX"}
  ]
}
```

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
├── variable_mapper_orchestrator.py  # MAIN - orchestration only
├── variable_extraction.py           # Extract variables from text
├── data_id_mapping.py               # Map variables to Data IDs
├── missing_variable_detector.py     # Identify required missing variables
├── query_builder.py                 # Build final structured queries
├── variable_extraction_prompts.py   # Prompts for extraction
├── states.py                        # LangGraph state definitions
├── mappings/
│   └── variable_data_id_mapping.csv # Variable → Data ID lookup table
└── tests/                           # Test files
```

---

## Workflow

```
Input (Retriever Synthesis)
    │
    ▼
┌─────────────────────────┐
│  Variable Extraction    │  ← Extract all variable mentions from text
│  (variable_extraction)  │     "TGA", "FCI", "short rates", etc.
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Data ID Mapping        │  ← Look up Data IDs for each variable
│  (data_id_mapping)      │     TGA → FRED:WTREGEN
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Missing Variable       │  ← Analyze chain completeness
│  Detection              │     Chain needs FCI but user didn't provide it
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Query Builder          │  ← Build structured JSON output
│  (query_builder)        │     List all data queries needed
└──────────┬──────────────┘
           │
           ▼
Output (Structured JSON with Data Queries)
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

### Phase 1: Foundation & Step 1 (CURRENT)

- [x] Create CLAUDE.md
- [x] Create STATUS.md
- [ ] Create `states.py` with basic state definitions
- [ ] Create `config.py` with environment setup
- [ ] Implement `variable_mapper_orchestrator.py` skeleton
- [ ] Implement `variable_extraction.py` - Extract variables from text
- [ ] Create `variable_extraction_prompts.py`
- [ ] Test extraction on sample retriever output (`query_result.md`)

### Phase 2: Normalization (Step 2)

- [ ] Implement variable normalization using `liquidity_metrics_mapping.csv`
- [ ] Handle variants (Korean + English aliases)
- [ ] Flag new/unknown variables

### Phase 3: Missing Variable Detection (Step 3)

- [ ] Implement `missing_variable_detector.py`
- [ ] Analyze logic chain dependencies
- [ ] Identify variables required but not provided by user

### Phase 4: Data ID Mapping (Step 4 - LATER)

- [ ] Create `mappings/variable_data_id_mapping.csv` with initial mappings
- [ ] Implement `data_id_mapping.py` - Variable → Data ID lookup
- [ ] Build initial mapping table (FRED, Bloomberg, etc.)
- [ ] Handle unknown variables (flag for manual mapping)

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
- Debug prints: FULL for LLM responses, truncated for others
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
