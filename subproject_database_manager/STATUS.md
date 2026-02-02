# Project Status - Telegram Financial Message Processing Workflow

**Last Updated**: 2026-01-27

## Current State: Production-Ready with Vector DB Integration

Complete end-to-end workflow for fetching and processing financial research messages from Telegram channels with AI-powered analysis, categorization, structured data extraction, automated QA sampling, and vector database storage.

---

## Session Summary: 2026-01-27

### Deduplication Gap Identified

**Issue detected**: 133 duplicate entries uploaded to Pinecone due to overlapping date ranges between runs.

| Channel | Overlapping Messages |
|---------|---------------------|
| Fomo CTRINE | 83 |
| Plan G Research | 50 |

**Root cause**:
1. SQLite processing tracker (`processing_state.db`) was empty at workflow start - no prior processing history recorded
2. Previous runs (Jan 20) occurred before the incremental update feature was implemented, so no `telegram_msg_id` tracking existed
3. Dedup check in `message_pipeline.py` found no IDs to skip, resulting in full re-processing of overlapping date range (Jan 1-20)

**Current state**: Pinecone index cleaned - duplicates removed. Final index size: 436 vectors.

**Resolution**: Deleted 278 duplicate vectors from Pinecone. Committed tracking files to git (commit `89fbfa7`).

---

## Future TODO: Data Collection Subproject

### Use Case 1: Institutional Flow News Collection
**Goal:** Collect news/announcements about institutional investors (insurers, pension funds, asset managers) and their portfolio rebalancing decisions.

**Example flow:**
```
News source → "Japanese insurers rebalancing into JGBs" →
Query retriever: "What does this mean for risk assets?" → Actionable insight
```

**Potential sources:** Bloomberg, Reuters, Nikkei, institutional press releases, regulatory filings

### Use Case 2: Historical Data Validation
**Goal:** When retrieval surfaces a claim (e.g., "BTC lags gold by 63-428 days"), fetch actual historical data and validate programmatically.

**Example flow:**
```
Retrieval output: "BTC follows gold with decreasing lag" →
Fetch: Gold prices, BTC prices (historical) →
Validate: Calculate actual correlation/lag →
Confirm or refute the claim
```

**Potential sources:** Yahoo Finance, FRED, CoinGecko API, etc.

### Reference to Check
- [ ] https://github.com/nathanyjleeprojects/global_markets_insight - Review for relevant patterns/data sources

---

## Session Summary: 2026-01-20

### Extraction Accuracy QA Implementation

Added accuracy verification to check if extracted VALUES are correct (not just structure).

**Problem**: Existing QA only validates structure/completeness, not whether extracted values match source.

**Solution**: New accuracy QA module that:
- Samples 10% of extractions (min 3, max 30)
- Uses Claude Haiku to verify each field against source text
- Records all results with full logs
- Tracks error rates with threshold recommendations

**Pipeline integration:**
```
Step 1: JSON → CSV
Step 2: Process messages (extract)
Step 3: QA Validation (structure)
Step 4: Accuracy QA (values) ← NEW
```

**Error types tracked:**
- `variable_wrong` - Wrong variable identified
- `value_wrong` - Incorrect number/amount
- `direction_wrong` - Up/down/stable incorrect
- `cause_wrong` - Logic chain cause not in text
- `effect_wrong` - Logic chain effect not in text
- `evidence_mismatch` - Quote doesn't match source
- `hallucination` - Extracted something not in source

**Files created:**
- `extraction_accuracy_qa.py` - Main accuracy QA module
- `extraction_accuracy_qa_prompts.py` - Verification prompts

**Files updated:**
- `message_pipeline.py` - Added Step 4 accuracy QA integration

---

### Cross-Chunk Chain Linkage Implementation

Added explicit chain connection across chunks using normalized variable names.

**Problem**: Logic chains stored in separate chunks couldn't be explicitly connected.
- Chunk A: "JPY weakness → carry trade unwind"
- Chunk B: "carry trade unwind → EM equity selling"
- Connection relied purely on LLM inference during synthesis

**Solution**: Added `cause_normalized` and `effect_normalized` fields to each logic chain step.

**New logic chain step structure:**
```json
{
  "cause": "TGA drawdown",
  "cause_normalized": "tga",
  "effect": "bank reserves increase",
  "effect_normalized": "bank_reserves",
  "mechanism": "Treasury spending releases TGA funds",
  "evidence_quote": "TGA 잔고가 750B로..."
}
```

**Normalization Rules:**
- Use existing names from `liquidity_metrics_mapping.csv` if available
- Create snake_case version for new concepts (max 30 chars)
- Common patterns: `tga`, `rrp`, `sofr`, `fed_funds`, `bank_reserves`, `carry_trade`, `risk_off`

**Files updated:**
- `data_opinion_prompts.py` - Added cause_normalized, effect_normalized to logic chain steps
- `interview_meeting_prompts.py` - Same

---

## Session Summary: 2026-01-17

### Logic Flaw Issue 1: Evidence Anchors

**Problem**: Logic chains could be hallucinated by LLM during extraction - no way to verify claims.

**Solution**: Added `evidence_quote` field to logic chain steps.

**Evidence Quote Rules:**
- Must be VERBATIM text from the source message (Korean or English OK)
- Must contain the causal/threshold claim EXPLICITLY
- Do NOT paraphrase - use exact wording from the message

**Files updated:**
- `data_opinion_prompts.py` - Added evidence_quote requirement to logic_chains schema
- `interview_meeting_prompts.py` - Same
- `qa_validation_prompts.py` - Added validation for evidence_quote field

---

## Session Summary: 2026-01-16

### Evaluation Response Implementation - Issues 1 & 5

Implemented enhancements from external architecture evaluation.

**Issue 1: Temporal & Regime Awareness**

Added `temporal_context` field to extraction schema for regime-aware retrieval:

```json
"temporal_context": {
  "policy_regime": "QE" | "QT" | "hold" | "transition",
  "liquidity_regime": "reserve_scarce" | "reserve_abundant" | "transitional",
  "valid_from": "2022-06",
  "valid_until": null,
  "is_forward_looking": false
}
```

**Key decision:** Empty object `{}` if regime context not clearly discernible. Do NOT infer from date alone.

**Files updated:**
- `data_opinion_prompts.py` - Added temporal_context field to extraction schema
- `interview_meeting_prompts.py` - Same temporal_context changes
- `qa_validation_prompts.py` - Added temporal_context validation to Completeness dimension

**Issue 5: Metrics Dictionary Governance**

Added lifecycle tracking columns to prevent dictionary drift:

| Column | Purpose |
|--------|---------|
| `first_seen` | Date metric was first discovered |
| `last_seen` | Date metric was last referenced |
| `deprecated` | Marks inactive metrics |
| `superseded_by` | Canonical name of replacement |

**Key decision:** Leave first_seen/last_seen empty for legacy metrics (no backfill).

**Files updated:**
- `metrics_mapping_utils.py` - Added lifecycle columns, auto-update logic
- `tests/cleanup_metrics.py` - Added `deprecate_metric()`, `find_stale_metrics()`, `list_deprecated_metrics()`

---

## Session Summary: 2026-01-01

### Trade Opinion Categorization + Post-Mortem Enrichment

Added capability to capture trading signals buried in casual content and enrich them with exact numbers from recent data.

**Problem**: Messages like "레포가 이렇게 튀었는데도 숏 안칠 거면 레포를 왜 봐요" (repo spiked → went short) were categorized as `other` and lost.

**Solution: Two-phase approach**

| Phase | Change | Purpose |
|-------|--------|---------|
| 1. Prompt tweak | `categorization_prompts.py` | Capture trade opinions in casual content |
| 2. Post-mortem enrichment | `tests/enrich_data_opinions.py` | Fill exact numbers from data_updates |

**Phase 1: Categorization Update**

Updated `data_opinion` definition to include:
- Implicit data references (spike, jump, crash)
- Trading actions (short, long, buy, sell)
- **IMPORTANT**: Include even if buried in greetings or casual content

**Result**: Messages with trade signals now categorize as `data_opinion` instead of `other`.

**Phase 2: Enrichment Script**

New script `tests/enrich_data_opinions.py`:
- Finds `data_opinion` entries with empty `liquidity_metrics` or `used_data`
- Collects `data_update` messages from last 7 days as context
- Calls LLM to fill in exact numbers/direction
- Adds new metrics to dictionary via `append_new_metrics()`

**Usage:**
```bash
# Dry run (preview)
python3 tests/enrich_data_opinions.py --input data/processed/processed_xxx.csv

# Execute enrichment
python3 tests/enrich_data_opinions.py --input data/processed/processed_xxx.csv --execute
```

**Example flow:**
```
data_update: "Repo $3.00B" (Dec 30)
data_update: "Repo $74.60B" (Dec 31)  ← 25x spike
data_opinion: "레포 튀었다 → 숏" (extracted but empty metrics)
    ↓ enrichment
data_opinion: liquidity_metrics: [{repo_spike_amount: 74.6B, direction: up}]
    ↓ append_new_metrics
liquidity_metrics_mapping.csv: repo_spike_amount added
```

**Files created/updated:**
- `categorization_prompts.py` - Expanded data_opinion to include trade opinions
- `tests/enrich_data_opinions.py` - NEW: Post-mortem enrichment script
- `tests/test_single_message.py` - NEW: Quick categorization test

---

## Session Summary: 2025-12-30

### Metrics Cleanup Validation and Enhancement

Extended the cleanup script with additional fixes and validation testing.

**Cleanup Results:**
| Metric | Before | After |
|--------|--------|-------|
| Total entries | 410 | 401 |
| Entries merged | - | 9 |
| Category errors | 8 | 0 |
| Cluster coverage | 34.7% | **100%** |
| Known duplicates | 7 pairs | 0 |
| Non-liquidity flagged | 50 | 55 |
| Direct liquidity | ~30 | 32 |
| Indirect liquidity | ~380 | 369 |

**New canonical mappings added:**
- `carry_trade_unwind` ← `carry_trade_unwinding_risk`
- `eurozone_banks_upside` ← `eurozone_banks_upside_potential`
- `ndx_spx_vol_spread` ← `ndx_spx_vol_spread_3m25d`
- `corporate_bond_price_yield` ← `corporate_bond_priceyield_core_weave`
- `ny_fed_balance_sheet` ← `ny_fed_balance_sheet_rebalancing`
- `spx_option_notional` ← `spx_option_notional_daily`
- `pension_fund_flows` ← `pension_fund_net_buy_kospi`, `pension_fund_net_buy_kosdaq`
- `policy_rate_cuts` ← `policy_rate_cut_expectations`

**New NON_LIQUIDITY_PATTERNS:**
```python
r'_op_krw$',      # Operating profit KRW
r'_op_yo_y$',     # Operating profit YoY
r'_opm$',         # Operating profit margin
r'_arr$',         # Annual recurring revenue
r'^ai_arr',       # AI ARR
r'^adjusted_opm', # Adjusted operating margin
r'^2026_op_',     # 2026 OP estimates
r'^4q25f_op',     # 4Q25F OP estimates
```

**New cleanup features:**
1. `fix_category_contamination()` - Fixes cluster names in category column
2. `assign_missing_clusters()` - Auto-assigns clusters via LLM (integrated into --execute)

**New test file:** `tests/test_metrics_cleanup.py`
- 6 validation tests (category, cluster coverage, duplicates, extraction structure, is_liquidity, direct classification)
- All tests passing

**Updated cluster distribution (15 clusters, 346 liquidity metrics):**
| Cluster | Count |
|---------|-------|
| equity_flows | 56 |
| macro_indicators | 46 |
| corporate_fundamentals | 45 |
| fx_liquidity | 33 |
| rate_expectations | 30 |
| credit_spreads | 23 |
| positioning_leverage | 23 |
| volatility_metrics | 18 |
| market_microstructure | 15 |
| option_flows | 12 |
| sovereign_flows | 12 |
| etf_flows | 11 |
| money_markets | 9 |
| fed_balance_sheet | 9 |
| cta_positioning | 4 |

**Files updated:**
- `tests/cleanup_metrics.py` - Extended with new mappings, patterns, and functions
- `tests/test_metrics_cleanup.py` - Created (validation test script)
- `CLAUDE.md` - Updated technology stack, development guidelines, cluster examples
- `STATUS.md` - Added session summary

---

## Session Summary: 2025-12-29

### 1. Metrics Data Quality Overhaul

Fixed severe data quality issues in `liquidity_metrics_mapping.csv`:
- **352 → 285 entries** (67 duplicates merged)
- **50 non-liquidity entries flagged** (substrate pricing, daily returns, company fundamentals)
- **All names standardized** to snake_case

**Root cause analysis:**
- Extraction prompts had weak INCLUDE/EXCLUDE rules
- No fuzzy duplicate detection in `append_new_metrics()`
- Variants column never used for matching
- Trust-based `is_new` flag relied entirely on LLM accuracy

### 2. Prevention: Stricter Extraction Prompts

Updated `data_opinion_prompts.py` and `interview_meeting_prompts.py` with:

**Strict exclusions:**
```
- Substrate/materials: BT price, ABF demand, T-glass, PCB share
- Daily returns: SPY return, QQQ return, individual ETF returns
- Company fundamentals: revenue, net loss, IPO proceeds, PSR, EPS
- Battery/EV, election probabilities, hiring metrics
```

**Variant checking instructions:**
```
Before marking is_new=true:
1. Check BOTH "normalized" AND "variants" columns
2. If ANY variant matches, use that normalized name
3. Only mark is_new=true if ZERO match
```

**Naming conventions:**
```
- Use snake_case: "cta_net_flow" NOT "CTA net flow"
- No values in names: "fed_cut_probability" NOT "Dec cut prob 80%"
- No temporal specifics: "etf_net_flows" NOT "ETF_Nov_inflows"
- Keep under 30 characters
```

### 3. Prevention: Validation Functions in metrics_mapping_utils.py

Added three validation functions to `append_new_metrics()`:

| Function | Purpose |
|----------|---------|
| `validate_metric_name()` | Normalize to snake_case, truncate to 40 chars |
| `is_liquidity_metric()` | Pattern/keyword blocklist filter |
| `fuzzy_match_metric()` | Catch duplicates via variants/word overlap/Levenshtein |

**Validation flow in `append_new_metrics()`:**
```
1. Check is_liquidity_metric() → skip if non-liquidity
2. Check fuzzy_match_metric() → merge if similar exists
3. Apply validate_metric_name() → standardize format
4. Then add as new metric
```

### 4. Post-Mortem Cleanup Script

Created `tests/cleanup_metrics.py` for batch deduplication:

**Features:**
- Canonical name mappings (20 mapping rules for common duplicates)
- Non-liquidity pattern detection (50+ regex patterns)
- Automatic backup before modification
- Dry-run mode by default

**Canonical mappings:**
| Canonical | Merges |
|-----------|--------|
| `cta_net_flow` | CTA net flow, CTA flows, CTA net flow (1m model) |
| `cta_trigger_levels` | 11 variants (thresholds, baselines, etc.) |
| `etf_net_flows` | 10 variants (monthly, YTD, VOO, etc.) |
| `foreign_equity_flows` | 9 variants |
| `fed_cut_probability` | 4 variants |

**Usage:**
```bash
python3 tests/cleanup_metrics.py           # Dry run
python3 tests/cleanup_metrics.py --execute # Apply changes
```

### 5. Integrated into Orchestrator

Post-mortem cleanup now runs automatically as **Step 3** in `telegram_workflow_orchestrator.py`:

```
Step 1: Fetch Telegram Messages
Step 2: Process Messages (categorize, extract, QA validate)
Step 3: Post-Mortem Metrics Cleanup  ← NEW
    - Backup CSV
    - Merge duplicates
    - Flag non-liquidity
    - Standardize names
Step 4: Workflow Complete
```

### 6. New CSV Column: is_liquidity

Added `is_liquidity` column to metrics CSV schema:
- `true` = legitimate liquidity metric
- `false` = non-liquidity entry (flagged but not deleted)

**Updated CSV schema:**
```
normalized, variants, category, description, sources, cluster, raw_data_source, is_liquidity
```

**Files updated:**
- `tests/cleanup_metrics.py` - Created (cleanup script)
- `metrics_mapping_utils.py` - Added validation functions + is_liquidity column
- `data_opinion_prompts.py` - Stricter INCLUDE/EXCLUDE rules
- `interview_meeting_prompts.py` - Stricter INCLUDE/EXCLUDE rules
- `telegram_workflow_orchestrator.py` - Added Step 3 cleanup

### 7. Codebase Cleanup

Moved obsolete files to `tests/` folder:
- `database_management.py` - Empty LangGraph skeleton (never implemented)
- `states.py` - Empty LangGraph state definitions
- `config.py` - Unused config (each module loads .env directly)
- `message_categorization.py` - Superseded by process_messages_v3.py
- `data_opinion_extraction.py` - Superseded by process_messages_v3.py
- `interview_meeting_extraction.py` - Superseded by process_messages_v3.py

Updated `CLAUDE.md` and `STATUS.md` to reflect actual architecture (two orchestrators, procedural Python instead of LangGraph).

### 8. Prompts Extraction

Extracted hardcoded prompts to dedicated prompts files (per CLAUDE.md guidelines):

| New File | Extracted From | Prompts |
|----------|---------------|---------|
| `image_extraction_prompts.py` | `process_messages_v3.py` | Image summary, image structured extraction |
| `metrics_mapping_prompts.py` | `metrics_mapping_utils.py` | Institution normalization |

All modules now follow the pattern: prompts in `*_prompts.py` files, logic in main modules.

### 9. Orchestrator Refactor

Extracted business logic from `telegram_workflow_orchestrator.py` into new `message_pipeline.py`:

| Before | After |
|--------|-------|
| `process_telegram_messages()`: 75 lines mixed logic | `process_telegram_messages()`: 12 lines routing only |
| Path extraction in orchestrator | `_extract_channel_name()` in pipeline |
| JSON→CSV in orchestrator | `_convert_json_to_csv()` in pipeline |
| V3 + QA calls inline | `_run_v3_processor()`, `_run_qa_validation()` in pipeline |

**New module:** `message_pipeline.py`
- `process_single_channel(export_folder, max_messages)` - main entry point
- Handles complete pipeline for one channel: JSON→CSV→V3→QA

Orchestrator now follows CLAUDE.md: **NO business logic, only routing**.

---

## Session Summary: 2025-12-26

### 1. Metrics Clustering for Data Reproduction

Added `cluster` and `raw_data_source` columns to liquidity metrics mapping for easier data reproduction.

**Purpose**: When looking at a cluster of related metrics, know exactly what raw data sources to find.

**New CSV schema**:
```
normalized, variants, category, description, sources, cluster, raw_data_source
```

**New columns**:
| Column | Purpose | Example |
|--------|---------|---------|
| `cluster` | Semantic grouping | `"ETF_flows"`, `"CTA_positioning"` |
| `raw_data_source` | Data feed for reproduction | `"Bloomberg ETF Flow Data"` |

**LLM-assisted cluster assignment**:
- New metrics automatically assigned clusters via GPT-4.1-mini
- Batch assignment for migration of existing metrics

**Migration results** (352 metrics → 14 clusters):
| Cluster | Count |
|---------|-------|
| corporate_fundamentals | 77 |
| equity_flows | 70 |
| etf_flows | 38 |
| macro_indicators | 30 |
| rate_expectations | 25 |
| fx_liquidity | 20 |
| cta_positioning | 18 |
| credit_spreads | 17 |
| positioning_leverage | 16 |
| volatility_metrics | 14 |
| sovereign_flows | 10 |
| option_flows | 6 |
| market_microstructure | 6 |
| fed_balance_sheet | 5 |

**New files**:
- `cluster_assignment_prompts.py` - LLM prompts for cluster assignment
- `tests/migrate_clusters.py` - One-time migration script

**Updated files**:
- `metrics_mapping_utils.py` - Added `get_existing_clusters()`, `assign_cluster_to_metric()`, `assign_clusters_batch()`
- `data_opinion_prompts.py` - Added `suggested_cluster` to extraction schema
- `interview_meeting_prompts.py` - Added `suggested_cluster` to extraction schema

---

## Session Summary: 2025-12-09

### 1. Extraction Quality Improvements - Tags & Topic Tags

Improved extraction prompt quality based on QA feedback analysis.

**Problems identified:**
- `tags` field had no criteria - just options `direct_liquidity | indirect_liquidity | irrelevant`
- 70%+ entries tagged "irrelevant" blocking semantic discovery
- `liquidity_metrics` captured non-liquidity items (DRAM prices, earnings, stock returns)

**Solution: Two-field approach**

| Field | Purpose | Example |
|-------|---------|---------|
| `tags` | Liquidity classification | `"indirect_liquidity"` |
| `topic_tags` | Topic discovery (ALWAYS populated) | `["US", "central_bank", "rates"]` |

**New `tags` criteria:**
```
- "direct_liquidity": Fed balance sheet (QE, QT, RRP, TGA, reserves), money markets (SOFR, repo, fed funds)
- "indirect_liquidity": Positioning (CTA, gamma), credit (issuance, buybacks), rate expectations, FX
- "irrelevant": Pure company fundamentals, product prices without funding angle (use sparingly)
```

**New `topic_tags` taxonomy:**
```
Asset Class: equities, rates, FX, credit, commodities
Region: US, china, japan, europe, korea, EM
Data Type: macro_data, earnings, central_bank
Mechanics: positioning, flows, volatility
```

**New `liquidity_metrics` guidance:**
```
INCLUDE: TGA, RRP, reserves, QE/QT, SOFR, CTA flows, dealer gamma, repo rates, issuance
EXCLUDE: Company earnings, DRAM prices, stock returns, P/E multiples
```

**Updated files:**
- `data_opinion_prompts.py` - Added tags criteria, topic_tags field, liquidity_metrics INCLUDE/EXCLUDE
- `interview_meeting_prompts.py` - Added tags criteria, topic_tags at statement and message level
- `qa_validation_prompts.py` - Added topic_tags validation (must always be populated)

**Expected outcomes:**
- Reduce "irrelevant" tags from 70%+ to <20%
- All entries discoverable via topic_tags
- liquidity_metrics contains only actual liquidity metrics
- QA retrievability scores improve from 0.67 → 0.85+

---

## Session Summary: 2025-12-07

### 1. Logic Chains Schema Update

Replaced `metric_relationships` with `logic_chains` for better causal chain extraction.

**Problem**: Old `metric_relationships` only captured single-hop links (cause → effect). Need multi-step chains.

**New schema**:
```json
"logic_chains": [
    {
        "steps": [
            {"cause": "Fed rate cuts", "effect": "real rates down", "mechanism": "rate cuts reduce yields"},
            {"cause": "real rates down", "effect": "risk asset valuations up", "mechanism": "lower real yields increase PV of cash flows"}
        ]
    }
]
```

**Updated files**:
- `data_opinion_prompts.py` - Replaced `metric_relationships` with `logic_chains`
- `interview_meeting_prompts.py` - Added `logic_chains` (was missing entirely)
- `qa_validation_prompts.py` - Updated to validate chain structure (connected steps, mechanisms)
- `tests/test_qa_simple.py` - Updated test data

### 2. Extraction Model Cost Reduction

Changed primary extraction model from GPT-5 to GPT-5 Mini for cost savings.

**Configuration** (`process_messages_v3.py`):
```python
EXTRACTION_MODEL = "gpt5_mini"  # Changed from "gpt5"
FALLBACK_MODEL = "claude_sonnet"
```

**Cost impact**: ~10x reduction in extraction costs ($0.05 → ~$0.005 per call)

---

## Session Summary: 2025-11-30

### 1. Embedding Workflow Implemented

Added complete vector embedding pipeline for processed research data.

**New files**:
- `embedding_generation.py` - Generates OpenAI embeddings from processed CSV
- `pinecone_uploader.py` - Upserts vectors to Pinecone
- `vector_db_orchestrator.py` - Main entry point for vector DB workflow

**Added to `models.py`**:
- `call_openai_embedding()` - Single text embedding
- `call_openai_embedding_batch()` - Batch embedding (up to 2048 texts)

**Pinecone index**: `research-papers` (3072 dimensions, cosine metric)

**Usage**:
```bash
python vector_db_orchestrator.py --input data/processed/processed_xxx.csv
```

### 2. Git Repository Setup

Pushed to GitHub for remote server deployment.

**Repository**: https://github.com/hodl-gap/friendly-bassoon

**Setup**:
- Created `.gitignore` (excludes `.env`, `.session`, `data/`, `test_data/`, images)
- Initial commit with 36 files (all code, no data)

**Remote server deployment**:
```bash
git clone https://github.com/hodl-gap/friendly-bassoon.git project_macro_analyst
# Copy .env and telegram_session.session manually
# Run in Zellij for persistent sessions
```

### 3. Source Entity Normalization

Added LLM-based normalization for institution names in metrics dictionary sources.

**Problem solved**: "GS FICC Desk", "Goldman Sachs", "GS FICC" → all normalize to "Goldman Sachs"

**New functions in `metrics_mapping_utils.py`**:
- `normalize_sources_in_csv()` - Batch normalizes all institution names
- `_batch_normalize_institutions()` - LLM call for entity resolution

**Integration**: Runs automatically after `append_new_metrics()` in pipeline

**Standalone cleanup**:
```bash
python metrics_mapping_utils.py
```

---

## Session Summary: 2025-11-29

### 1. Metrics Dictionary Source Tracking

Added `sources` column to `liquidity_metrics_mapping.csv` to track where metrics were first discovered.

**Format**: `Institution, data_source` (e.g., `UBS, Global equity strategy`)

**Features**:
- Sources are additive - if same metric appears from different sources, they're appended with `|`
- Uses `source` field (institution) + `data_source` field (specific report/data)
- NOT telegram channel names

**Updated files**:
- `metrics_mapping_utils.py` - `collect_new_metrics_from_extractions()` now builds combined source
- `metrics_mapping_utils.py` - `append_new_metrics()` handles additive sources for existing metrics
- `liquidity_metrics_mapping.csv` - Added `sources` column (79 metrics total)

### 2. GPT-5 with Claude Fallback

Switched extraction model from Claude Sonnet to GPT-5 with automatic Claude fallback.

**Configuration** (`process_messages_v3.py`):
```python
EXTRACTION_MODEL = "gpt5"
FALLBACK_MODEL = "claude_sonnet"
```

**Performance comparison** (7 messages, 5 batches):

| Metric | GPT-5 | Claude Sonnet |
|--------|-------|---------------|
| Step 4 Time | 55-132s | 61s |
| Total Time | 101-175s | 92s |
| Cost | ~$0.27 | ~$0.07 |
| Success Rate | 100% | 100% |

GPT-5 extracts more granular metrics but is slower and more expensive.

### 3. QA Sampling Integrated into Orchestrator

QA validation now runs automatically after processing, sampling a subset of extractions.

**Sampling logic**:
- Minimum: 3 samples
- Maximum: 20 samples
- Target: 5% of validatable entries
- Categories: `data_opinion`, `interview_meeting`

**Log output**: `data/qa_logs/qa_sample_{filename}_{timestamp}.txt`

**Test results** (18 entries → 3 sampled):
- PASS: 3/3 (100%)
- Avg Scores: R=0.87, C=0.83, A=0.85

---

## Architecture

```
telegram_workflow_orchestrator.py (MAIN ENTRY POINT)
    │
    ├─→ Step 1: telegram_fetcher.py   → Fetch messages from Telegram API
    │                                  → Download images
    │                                  → Export to ChatExport format
    │
    ├─→ extract_telegram_data.py      → Convert JSON to CSV
    │
    ├─→ Step 2: process_messages_v3.py → Image-first processing
    │       │                           → Categorization (6 types)
    │       │                           → Structured extraction (GPT-5 Mini + Claude fallback)
    │       │                           → Parallel batch processing
    │       │                           → Auto-update metrics dictionary
    │       │
    │       ├─→ models.py              → GPT-5 Mini, Claude 4.5 models
    │       │                           → process_batch_parallel_with_retry()
    │       │
    │       ├─→ metrics_mapping_utils.py → Metric normalization + validation
    │       │                             → Fuzzy duplicate detection
    │       │                             → Source tracking
    │       │
    │       └─→ qa_validation.py       → QA sampling validation (integrated)
    │                                   → 3-dimensional quality check
    │                                   → Logs to data/qa_logs/
    │
    └─→ Step 3: tests/cleanup_metrics.py → Post-mortem deduplication
                                          → Merge duplicates to canonical names
                                          → Flag non-liquidity entries
                                          → Standardize to snake_case

    Optional: tests/enrich_data_opinions.py → Post-mortem enrichment
                                              → Find ambiguous data_opinions
                                              → Use 7-day data_update context
                                              → Fill in exact numbers/direction
                                              → Add new metrics to dictionary

vector_db_orchestrator.py (SEPARATE ENTRY POINT)
    │
    ├─→ embedding_generation.py      → Generate embeddings (OpenAI text-embedding-3-large)
    │                                 → 3072 dimensions
    │
    └─→ pinecone_uploader.py         → Upsert vectors to Pinecone
                                      → Index: research-papers
                                      → Metadata attachment
```

**Note**: Vector DB workflow is separate from Telegram message processing. Run telegram orchestrator first to generate `processed_*.csv`, then run vector DB orchestrator to embed and upsert.

## File Structure

```
Main Workflow:
├── telegram_workflow_orchestrator.py  ⭐ MAIN ORCHESTRATOR (routing only)
├── telegram_fetcher.py                  Telegram API fetcher
├── message_pipeline.py                  Single channel processing pipeline
├── extract_telegram_data.py             JSON to CSV converter
├── process_messages_v3.py               V3 message processor
├── categorization_prompts.py            Categorization prompts
├── data_opinion_prompts.py              Data opinion extraction prompts
├── interview_meeting_prompts.py         Interview/meeting extraction prompts
├── qa_validation.py                     QA validation (with sample_qa_validation)
├── qa_validation_prompts.py             QA validation prompts
├── qa_post_processor.py                 QA validation CLI (standalone)
├── metrics_mapping_utils.py             Metric normalization + source tracking + clustering
├── cluster_assignment_prompts.py        Prompts for LLM cluster assignment
├── image_extraction_prompts.py          Prompts for image summarization + extraction
├── metrics_mapping_prompts.py           Prompts for institution normalization

Vector DB Workflow:
├── vector_db_orchestrator.py         ⭐ VECTOR DB ORCHESTRATOR
├── embedding_generation.py              OpenAI embeddings generator
├── pinecone_uploader.py                 Pinecone vector uploader

Tests & Obsolete:
├── tests/
│   ├── enrich_data_opinions.py          Post-mortem enrichment with data_update context
│   ├── cleanup_metrics.py               Post-mortem deduplication + cluster assignment
│   ├── test_single_message.py           Quick categorization test
│   ├── test_metrics_cleanup.py          Validation tests for cleanup results
│   ├── migrate_clusters.py              One-time cluster migration script
│   ├── test_qa_simple.py                QA validation tests
│   ├── test_qa_validation.py            QA validation tests
│   ├── test_single_entry.py             Single entry QA test
│   ├── test_pinecone_query.py           Pinecone query tests
│   ├── database_management.py           (obsolete) Empty LangGraph skeleton
│   ├── states.py                        (obsolete) Empty LangGraph state
│   ├── config.py                        (obsolete) Unused config
│   ├── message_categorization.py        (obsolete) Superseded by process_messages_v3
│   ├── data_opinion_extraction.py       (obsolete) Superseded by process_messages_v3
│   └── interview_meeting_extraction.py  (obsolete) Superseded by process_messages_v3

Parent Directory:
├── models.py                            AI model functions
│                                        - GPT-5 series + Claude 4.5 series
│                                        - process_batch_parallel_with_retry()
└── .env                                 API keys

Data Folders:
├── data/
│   ├── raw/
│   │   ├── ChatExport_{channel}_{date}/
│   │   │   ├── result.json              Raw Telegram export
│   │   │   └── photos/                  Downloaded images
│   │   └── {channel}_{date}_messages.csv   Intermediate CSV (from JSON)
│   │
│   ├── processed/
│   │   ├── processed_{channel}_{date}.csv           ⭐ FINAL OUTPUT
│   │   ├── qa_validated_{...}.csv                   Full QA validated output (standalone)
│   │   ├── qa_validated_{...}_detailed_log.txt     Full QA validation log (standalone)
│   │   └── liquidity_metrics/
│   │       └── liquidity_metrics_mapping.csv        Metrics dictionary (auto-grows)
│   │
│   └── qa_logs/
│       └── qa_sample_{filename}_{timestamp}.txt    QA sampling log (from orchestrator)
```

## Usage

```bash
# Full workflow (fetch + process + QA sampling)
python telegram_workflow_orchestrator.py \
  --channels "hyottchart" \
  --start-date 2025-11-23 \
  --end-date 2025-11-28

# List available channels
python telegram_workflow_orchestrator.py --list-channels

# Fetch only (no processing)
python telegram_workflow_orchestrator.py \
  --channels "hyottchart" \
  --start-date 2025-11-23 \
  --end-date 2025-11-28 \
  --no-process

# Standalone full QA validation (all entries)
python qa_post_processor.py \
  --input data/processed/processed_xxx.csv \
  --categories data_opinion,interview_meeting

# Post-mortem enrichment (fill exact numbers for ambiguous extractions)
python tests/enrich_data_opinions.py --input data/processed/processed_xxx.csv           # Dry run
python tests/enrich_data_opinions.py --input data/processed/processed_xxx.csv --execute # Apply
```

## Configuration

```python
# process_messages_v3.py
EXTRACTION_MODEL = "gpt5_mini"      # Primary model (cost-effective)
FALLBACK_MODEL = "claude_sonnet"    # Fallback if primary fails
MAX_CONCURRENT_REQUESTS = 10        # Parallel API calls
```

## Output Format

**Processed CSV columns:**
- `original_message_num`, `date`, `tg_channel`, `category`
- `entry_type`, `opinion_id`, `raw_text`, `has_photo`
- `extracted_data` - JSON with:
  - `source`, `data_source`, `asset_class`
  - `used_data`, `what_happened`, `interpretation`
  - `tags` (direct_liquidity | indirect_liquidity | irrelevant)
  - `topic_tags[]` - semantic topic tags for discovery (US, rates, equities, etc.)
  - `liquidity_metrics[]` - normalized metrics with values/directions
  - `logic_chains[]` - multi-step causal chains (cause → effect → mechanism)

**Metrics Dictionary CSV columns:**
- `normalized` - Standard metric name (snake_case)
- `variants` - Alternative names/spellings (pipe-delimited)
- `category` - `direct` | `indirect`
- `description` - What the metric measures
- `sources` - Where metric was discovered (Institution, data_source)
- `cluster` - Semantic grouping for data reproduction (15 clusters)
- `raw_data_source` - Raw data feed needed to reproduce
- `is_liquidity` - `true` | `false` - flags non-liquidity entries

**Current metrics stats:** 401 entries (346 liquidity, 55 non-liquidity), 100% cluster coverage

## API Costs

| Model | Per Call | Notes |
|-------|----------|-------|
| Claude Sonnet 4.5 vision | ~$0.015 | Image analysis |
| GPT-4.1 mini | ~$0.0004 | Categorization |
| GPT-5 Mini | ~$0.005 | Extraction (primary) |
| Claude Sonnet 4.5 text | ~$0.01 | Extraction (fallback) |
| GPT-4.1 | ~$0.01 | QA validation |

**Example run (7 messages, GPT-5 Mini):**
- Vision calls: $0.02
- Categorization: $0.003
- Extraction: $0.025
- QA sampling (3): $0.03
- **Total: ~$0.08 USD**

---

## TODO / Next Steps

### High Priority

1. **[x] Implement embedding workflow** ✅ Done 2025-11-30
   - Added `call_openai_embedding()` to models.py
   - Created `embedding_generation.py` function module
   - Created `vector_db_orchestrator.py` with Pinecone integration
   - Tested with processed CSV files (18 vectors upserted)

2. **[x] Source entity normalization** ✅ Done 2025-11-30
   - LLM-based institution name normalization
   - Integrated into pipeline after metrics update
   - Batch processing for efficiency

3. **[x] Fix duplicate entries in processed CSV** ✅ Done 2025-12-04
   - Verified no true duplicates exist when keying by `(tg_channel, original_message_num, date, entry_type)`
   - Multiple rows per message are intentional: separate extractions for text vs image content
   - Example: 73 messages → 139 entries (66 messages have both text + image)

4. **[ ] Benchmark parallel vs sequential**
   - Compare Step 4 times
   - Document speedup factor
   - Identify optimal `MAX_CONCURRENT_REQUESTS` value
   - Note: `MAX_CONCURRENT_REQUESTS=10` already exists in code, but no benchmark comparison done

5. **[ ] Add missing metrics to `liquidity_metrics_mapping.csv`**
   - `fed_funds_rate` - Fed funds rate (missing)
   - `yield_curve_2y10y` - Yield curve spread (missing)
   - Note: CSV structure is clean (155 entries, 100% clusters, 73% Korean variants)

### Medium Priority

3. **[ ] Add categorization for 'individual_stock_research'**
   - Handle company/stock-specific research messages
   - Separate category with appropriate extractor

4. **[x] Implement incremental updates** ✅ Done 2026-01-26
   - SQLite tracker (`data/processing_state.db`) stores `(tg_channel, telegram_msg_id, status)`
   - Dedup check in `message_pipeline.py` skips already-processed messages before LLM extraction
   - `telegram_msg_id` preserved from JSON → CSV → Pinecone metadata
   - Resume capability: tracks `extracted` vs `uploaded` status for mid-run failures

5. **[ ] Add keyword search support**
   - Telethon supports keyword filtering
   - Could reduce messages fetched

### Low Priority

6. **[ ] Handle billing quota limits**
   - Add rate limiting / backoff when hitting API billing quotas
   - Graceful handling of quota exceeded errors

7. **[ ] Blocking QA mode**
   - Halt pipeline on low QA scores
   - Require manual review before proceeding

8. **[ ] Auto-fix mode for QA**
   - LLM suggests fixes → apply automatically → re-validate

9. **[ ] Quality metrics dashboard**
   - Track QA scores over time
   - Identify extraction patterns

10. **[ ] Set up git remote**
   - Create remote repository (GitHub/GitLab)
   - Add origin and push

---

## Development Timeline

- **2025-11-21** - Project setup, basic structure
- **2025-11-22** - V3 processor development
- **2025-11-23** - Telegram fetcher, orchestrator
- **2025-11-25** - QA validation agent
- **2025-11-27** - Liquidity metrics schema enhancement
- **2025-11-28** - GPT-5/Claude 4.5 models, parallel processing
- **2025-11-29** - Source tracking, QA sampling integration, GPT-5 primary model
- **2025-11-30** - Embedding workflow, Pinecone integration, source entity normalization
- **2025-12-07** - Logic chains schema (replaced metric_relationships), GPT-5 Mini extraction
- **2025-12-09** - Extraction quality: tags criteria, topic_tags field, liquidity_metrics guidance
- **2025-12-26** - Metrics clustering for data reproduction
- **2025-12-29** - Metrics data quality overhaul: validation functions, post-mortem cleanup, stricter prompts; Codebase cleanup (obsolete files moved to tests/); Prompts extraction (image_extraction_prompts.py, metrics_mapping_prompts.py); Orchestrator refactor (message_pipeline.py)
- **2025-12-30** - Cleanup validation: extended canonical mappings, NON_LIQUIDITY_PATTERNS, cluster assignment; 100% cluster coverage; test_metrics_cleanup.py validation suite
- **2026-01-01** - Trade opinion categorization (data_opinion captures trading actions); Post-mortem enrichment script (fills exact numbers using 7-day data_update context)
- **2026-01-16** - Evaluation response: Temporal/regime awareness, metrics lifecycle tracking
- **2026-01-17** - Logic Flaw Issue 1: Evidence anchors (evidence_quote field)
- **2026-01-20** - Cross-chunk chain linkage (cause_normalized, effect_normalized fields)
- **2026-01-26** - Incremental updates: SQLite processing tracker, telegram_msg_id preservation, dedup before LLM extraction

---

## Known Limitations

1. GPT-5 Mini may have lower extraction quality than GPT-5 (cost tradeoff)
2. ~~No incremental updates (re-fetches full date range)~~ ✅ **RESOLVED 2026-01-26** - SQLite tracker + dedup check before LLM extraction
3. No keyword search (Telethon supports it)
4. ~~Metrics dictionary can accumulate duplicate metric names~~ ✅ **RESOLVED 2025-12-29** - Added validation functions + post-mortem cleanup
5. Parallel processing requires ThreadPoolExecutor workaround in async context
