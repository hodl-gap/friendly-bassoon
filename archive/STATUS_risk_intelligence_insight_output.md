# Risk Intelligence - Insight Output Implementation

**Date**: 2026-02-15
**Commit**: `dbf5364 Add insight output, multi-hop chain graph, and N-analog aggregation`
**Branch**: master

## Summary

Implemented 4 phases to transform Risk Intelligence from producing trade signals (BULLISH/BEARISH with confidence scores) to producing multi-track causal insights grounded in historical evidence. This aligns the module with the Bridgewater research team goal: insights, not trade ideas.

## What Changed

### Phase 0: Rename BTC-Specific to Asset-Agnostic

| Action | Detail |
|--------|--------|
| `git mv` | `btc_impact_orchestrator.py` -> `insight_orchestrator.py` |
| `git mv` | `data/btc_relationships.json` -> `data/relationships.json` |
| Updated imports | `__init__.py`, `__main__.py` |
| Updated references | `asset_configs.py`, `relationship_store.py`, `states.py` |
| Updated scripts | `scripts/backfill_theme_index.py`, `scripts/backfill_variable_frequency.py` |
| Updated shared | `shared/theme_index.py` |
| Updated docs | `ARCHITECTURE.md` |
| Backward compat | `run_btc_impact_analysis = run_impact_analysis` alias kept |
| Print prefixes | `[BTC Intelligence]` -> `[Risk Intelligence]` |

### Phase 2: Multi-Hop Chain Graph

**New file**: `shared/chain_graph.py`

`ChainGraph` class — directed graph built at query time from retrieved + historical chains. Dict-of-lists, no external deps.

Key methods:
- `add_chain()` / `add_chains_from_list()` — handles both `{steps}` and `{logic_chain: {steps}}` formats
- `find_paths(start, end, max_depth)` — iterative DFS with cycle detection
- `get_tracks(trigger)` — group paths by terminal effect into reasoning tracks
- `get_trigger_variables(query)` — match query tokens to graph variables, sorted by out-degree
- `format_for_prompt(tracks)` — `## MULTI-HOP CAUSAL PATHS` section for LLM prompt

**Integration in `insight_orchestrator.py`**:
- `build_chain_graph()` function called after `load_chains()`
- Finds trigger variables from query, runs DFS for top 3 triggers
- Stores `chain_tracks` and `chain_graph_text` in state

**Prompt changes**: `chain_graph_text` parameter added to both `get_insight_prompt()` and `get_impact_analysis_prompt()`.

**State changes**: Added `chain_tracks: List[Dict]` and `chain_graph_text: str` to `RiskImpactState`.

### Phase 3: Historical N-Analog Aggregation

**New file**: `subproject_risk_intelligence/historical_aggregator.py`

Three functions:
- `fetch_multiple_analogs()` — parallel fetch via `ThreadPoolExecutor(max_workers=3)`
- `aggregate_analogs()` — direction distribution, magnitude (median/min/max/mean), timing (recovery days)
- `format_analogs_for_prompt()` — `## HISTORICAL PRECEDENT ANALYSIS (Multi-Analog)` section

**New in `historical_event_detector.py`**: `detect_historical_analogs()` — Haiku + tool_use, returns up to 5 analogs with relevance scores.

**New in `historical_event_prompts.py`**: `MULTI_ANALOG_DETECTION_PROMPT` and `MULTI_ANALOG_TOOL` schema.

**Config additions** (`config.py`):
```python
ENABLE_MULTI_ANALOG = True         # env: RISK_MULTI_ANALOG
MAX_HISTORICAL_ANALOGS = 5
ANALOG_RELEVANCE_THRESHOLD = 0.5
```

**Integration**: Multi-analog branch in `enrich_with_historical_event()` runs after existing single-analog logic.

**State changes**: Added `historical_analogs: Dict` and `historical_analogs_text: str` to `RiskImpactState`.

### Phase 1: Insight Output Format

**New types** (`states.py`):
- `InsightTrack` TypedDict — track_id, title, causal_mechanism, causal_steps, historical_evidence, asset_implications, monitoring_variables, confidence, time_horizon

**Prompt changes** (`impact_analysis_prompts.py`):
- `SYSTEM_PROMPT` renamed to `BELIEF_SPACE_SYSTEM_PROMPT` (alias kept)
- Added `INSIGHT_SYSTEM_PROMPT` — instructs LLM to produce independent reasoning TRACKS (not scenarios)
- Added `_format_data_sections()` — shared helper for DRY data formatting between modes
- Added `get_insight_prompt()` — insight-specific instructions with shared data sections

**Analysis refactor** (`impact_analysis.py`):
- `analyze_impact()` refactored into dual-mode dispatcher
- `_analyze_insight()` — uses `INSIGHT_SYSTEM_PROMPT` + `output_insight` tool, populates legacy fields from best track
- `_analyze_belief_space()` — extracted from original `analyze_impact()` body, unchanged logic
- `_prepare_prompt_data()` — shared data prep for both modes
- `_get_insight_tool()` — tool schema for structured insight output
- `_parse_insight_tool_result()` — converts tool_use output to insight dict

**Output formatting** (`insight_orchestrator.py`):
- Added `format_insight()` — formats tracks with evidence, implications, monitoring variables
- Output dispatch: `format_insight()` when `output_mode == "insight"`, `format_output()` when `belief_space`

**CLI** (`__main__.py`):
- Added `--mode` argument: `choices=["insight", "belief_space"]`, default `"insight"`
- `output_mode` threaded through `run_impact_analysis()` and `run_multi_asset_analysis()`

**State changes**: Added `output_mode: str` and `insight_output: Dict` to `RiskImpactState`.

## Bug Fix

**ChainGraph trigger detection punctuation bug**: `get_trigger_variables()` failed to match `"btc"` from query `"What is the TGA impact on BTC?"` because `"btc?"` (with question mark) didn't match `"btc"`. Fixed by adding `re.sub(r'[^\w\s]', ' ', query_lower)` to strip punctuation from query tokens.

## Files Changed

| File | Change |
|------|--------|
| `shared/chain_graph.py` | **NEW** — ChainGraph class |
| `subproject_risk_intelligence/historical_aggregator.py` | **NEW** — multi-analog fetch/aggregate/format |
| `subproject_risk_intelligence/insight_orchestrator.py` | Renamed from `btc_impact_orchestrator.py`, major additions |
| `subproject_risk_intelligence/impact_analysis.py` | Dual-mode dispatch, insight tool schema |
| `subproject_risk_intelligence/impact_analysis_prompts.py` | INSIGHT_SYSTEM_PROMPT, shared data sections |
| `subproject_risk_intelligence/states.py` | InsightTrack, new state fields |
| `subproject_risk_intelligence/config.py` | Multi-analog config flags |
| `subproject_risk_intelligence/historical_event_detector.py` | detect_historical_analogs() |
| `subproject_risk_intelligence/historical_event_prompts.py` | MULTI_ANALOG_DETECTION_PROMPT + tool |
| `subproject_risk_intelligence/__init__.py` | Import from insight_orchestrator |
| `subproject_risk_intelligence/__main__.py` | --mode flag, output_mode threading |
| `subproject_risk_intelligence/asset_configs.py` | relationships.json |
| `subproject_risk_intelligence/relationship_store.py` | Docstring update |
| `subproject_risk_intelligence/CLAUDE.md` | Full rewrite to match current codebase |
| `scripts/backfill_theme_index.py` | relationships.json |
| `scripts/backfill_variable_frequency.py` | relationships.json |
| `shared/theme_index.py` | Docstring update |
| `ARCHITECTURE.md` | relationships.json |
| `data/btc_relationships.json` | **RENAMED** to `data/relationships.json` |

## Test Runs

All run with `--skip-data --skip-chains` (no live data fetch, no chain persistence).

Query: `"How does the February 2026 Japan snap election (Takaichi) affect risk assets and yen carry trades?"`

### Insight Mode (default)

- **Log**: `logs/run_20260215_110608.log` (1,371 lines)
- **Duration**: 360s
- **Cost**: $0.77 (16 API calls, ~98K tokens)
- **Output**: 5 independent reasoning tracks:
  1. BOJ Tightening Acceleration (72% confidence)
  2. Carry Trade Unwind Liquidity Drain (78% confidence)
  3. Political Contradiction Trap (62% confidence)
  4. Safe Haven Rotation (58% confidence)
  5. Global Liquidity Structural Shift (55% confidence)
- Each track includes: causal mechanism (arrow notation), historical evidence with precedent counts/success rates, asset implications with magnitude ranges and timing, monitoring variables with thresholds
- Synthesis narrative connecting all tracks
- 7 key uncertainties identified

### Belief Space Mode (legacy)

- **Log**: `logs/run_20260215_111217.log` (626 lines)
- **Duration**: 168s
- **Cost**: $0.33 (7 API calls, ~46K tokens)
- **Output**: 4 scenarios:
  1. Carry Trade Unwind Cascade — BEARISH 45%
  2. Fiscal Dominance / Yen Weakness — BULLISH 30%
  3. JGB Crisis Spillover — BEARISH 15%
  4. Volatility Spike — BEARISH 10%
- 1 contradiction detected (BOJ independence vs fiscal dominance)
- Primary direction: BEARISH, confidence 0.55, regime uncertainty high

### Smoke Test

- **Log**: `logs/run_20260215_110527.log` (284 lines)
- **Query**: `"Test query"` — confirmed no import errors, pipeline loads correctly
