# Plan: Output Format Refactor — Two-Mode Scenario/Decomposition Output

## Problem Statement

1. **Output isn't fixed** — pipeline produces interpretation (backward-looking) and prediction (forward-looking) under the same schema, making feedback loops impossible
2. **Opus is excessively verbose** — Case 7 output: ~36K chars / 500 lines of JSON. Free-text fields (`magnitude_range`, `precedent_summary`, `condition`) balloon into paragraphs. Synthesis repeats data from tracks.
3. **No scoreability** — no structured predictions with check dates, falsification criteria, or variable-level direction claims

## Design Decisions

- **Two output modes**: `retrospective` (causal decomposition) and `prospective` (scenario analysis), routed by query type classification in EDF Phase 0
- **Hybrid queries forced to one mode** — EDF picks whichever dominates. Default is `prospective` when ambiguous (the harder/more useful mode)
- **Scenarios grounded in analog clusters**, not LLM-assigned probabilities. Each scenario tagged with "N/M analogs followed this path" — auditable base rates, not vibes
- **No minimum episode threshold** — even 1-episode clusters become scenarios. "1/3 analogs" is honest. For 0 episodes (novel event), scenarios are still generated from causal chains with explicit "no historical grounding" label
- **Structured numeric fields** replace free-text to mechanically constrain verbosity. `magnitude_low: number` instead of `magnitude_range: string`
- **Scenario skeletons built mechanically** from Phase 3 regime clusters before Phase 4 LLM sees them
- **Prediction ledger** for scoreable claims extracted from prospective output
- **Per-asset fan-out preserved** — multi-asset runs produce separate scenario analyses per asset (scenarios duplicated, predictions differ per asset)
- **Chain storage deferred** — `store_chains()` / `relationship_store.py` currently parses the old track format. Skip chain storage during this refactor; add back once new format stabilizes (see TODO)
- **Remove condensed summary** — the new format is short enough (~50-80 lines) that a separate condensed summary is redundant
- **Rubrics scored loosely** — existing Case 1-7 rubrics check "is the information present anywhere in output?" rather than expecting specific field locations. Rubric rewrite deferred.

## Scope

Only Phase 4 (synthesis) and output formatting change. Phases 0-3 (retrieval, data grounding, historical context) are untouched.

---

## Implementation Steps

### Step 1: Add `temporal_direction` to EDF output

**Files**: `edf_decomposer_prompts.py`, `edf_decomposer.py`

The EDF already classifies `query_type` as `actor-driven | data-driven | hybrid`. Add a second classification:

```
temporal_direction: "retrospective" | "prospective"
```

- `retrospective`: query uses past tense, asks "what caused/happened/why did"
- `prospective`: query asks about future impact of current/hypothetical event
- For hybrid queries (e.g., "FDIC shows $306B losses... under what conditions could this become systemic?"), pick whichever dominates. Default to `prospective` when ambiguous.

Add to the EDF prompt instructions and parse from the knowledge tree JSON output. Add a `get_temporal_direction(tree)` helper in `edf_decomposer.py` that reads the field (defaulting to `prospective` if absent).

Thread through state: `state["_edf_knowledge_tree"]` already propagates — the temporal direction is read from there in Phase 4.

**Estimated changes**: ~15 lines prompt, ~10 lines code.

---

### Step 2: Build scenario skeletons mechanically from Phase 3 data

**New file**: `subproject_risk_intelligence/scenario_builder.py`

This file builds scenario structures from Phase 3 output (episode clusters + analog aggregation) — **no LLM call**. Pure data transformation.

**Input**: `state` after Phase 3 completes (contains `indicator_extremes_data` with regime-clustered episodes, and/or `historical_analogs` with aggregated analog data)

**Output**: A `scenario_skeleton` dict added to state:

```python
{
    "scenarios": [
        {
            "cluster_label": "expansion_easing",      # from regime_detail.macro
            "analog_count": 4,                         # episodes in this cluster
            "total_episodes": 12,                      # total episodes found
            "representative_dates": ["2019-08-05", "2020-03-23"],
            "forward_returns": {                       # per-asset, per-window stats
                "SPY": {"1mo": {"median": 2.2, "pct_positive": 75, "min": -3.1, "max": 8.3}},
            },
            "regime_similarity_to_current": 0.71,      # avg similarity of cluster episodes
        },
        ...
    ],
    "base_rates": {                                    # aggregate across ALL episodes
        "direction_positive_pct": 75,
        "magnitude_median": 2.2,
        "magnitude_range": [-31.0, 8.3],
        "recovery_median_days": 45,
    },
    "distinguishing_variables": ["vix", "brent_crude", "us10y"],  # variables with highest variance across clusters
}
```

**Logic for `distinguishing_variables`**: For each regime variable, compute the variance of forward returns across clusters. Variables where clusters diverge most are the "what determines which scenario" indicators.

**Three data paths** (use whichever Phase 3 produced):
- Path A: `indicator_extremes_data` exists → use `macro_clusters` from `characterize_episodes`
- Path B: `historical_analogs` exists → use `direction_distribution` from `aggregate_analogs`, cluster by analog similarity
- Path C: Neither exists (novel event, 0 episodes) → return empty skeleton with `total_episodes: 0`. Opus still generates scenarios from causal chains, just without base rate grounding. The absence of data is shown explicitly.

**No minimum threshold.** Even 1-episode clusters become scenarios. "1/3 analogs" is honest — the trader sees the thin data and discounts accordingly. The sample size IS the confidence signal.

**Call site**: In `insight_orchestrator.py`, after Phase 3 completes and before Phase 4. Add:
```python
from .scenario_builder import build_scenario_skeleton
state["scenario_skeleton"] = build_scenario_skeleton(state)
```

**Estimated size**: ~150 lines.

---

### Step 3: Split Phase 4 into two tool schemas

**Files**: `impact_analysis.py`, `impact_analysis_prompts.py`

#### 3a: Retrospective tool schema (`output_causal_decomposition`)

```python
{
    "name": "output_causal_decomposition",
    "input_schema": {
        "type": "object",
        "properties": {
            "trigger_event": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "maxLength": 200},
                    "date": {"type": "string"},
                },
                "required": ["description"]
            },
            "causal_tracks": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 80},
                        "mechanism": {"type": "string", "maxLength": 200,
                                      "description": "Arrow notation: A → B → C"},
                        "evidence_summary": {"type": "string", "maxLength": 300},
                        "quantitative_data": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "metric": {"type": "string"},
                                    "value": {"type": "string"},
                                    "source": {"type": "string"}
                                },
                                "required": ["metric", "value"]
                            }
                        },
                        "confidence": {"type": "number"}
                    },
                    "required": ["title", "mechanism", "evidence_summary", "confidence"]
                }
            },
            "cross_track_synthesis": {"type": "string", "maxLength": 500,
                                      "description": "How tracks interact. 2-3 sentences max."},
            "residual_forward_view": {"type": "string", "maxLength": 300,
                                      "description": "Optional: what to watch going forward. NOT scored."},
            "key_data_gaps": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string", "maxLength": 100}
            }
        },
        "required": ["trigger_event", "causal_tracks", "cross_track_synthesis"]
    }
}
```

#### 3b: Prospective tool schema (`output_scenario_analysis`)

The LLM receives the scenario skeleton from Step 2 and fills in human-readable names + causal mechanisms. It does NOT assign probabilities — those come from the data.

```python
{
    "name": "output_scenario_analysis",
    "input_schema": {
        "type": "object",
        "properties": {
            "current_situation": {"type": "string", "maxLength": 300},
            "scenarios": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 80},
                        "condition": {"type": "string", "maxLength": 200,
                                      "description": "What must be true for this scenario"},
                        "mechanism": {"type": "string", "maxLength": 200,
                                      "description": "Arrow notation causal chain"},
                        "analog_basis": {"type": "string", "maxLength": 200,
                                         "description": "Which historical analogs support this. Reference the base rate data."},
                        "predictions": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "variable": {"type": "string"},
                                    "direction": {"type": "string",
                                                  "enum": ["bullish", "bearish", "neutral"]},
                                    "magnitude_low": {"type": "number"},
                                    "magnitude_high": {"type": "number"},
                                    "timeframe_days": {"type": "integer"},
                                },
                                "required": ["variable", "direction", "timeframe_days"]
                            }
                        },
                        "falsification": {"type": "string", "maxLength": 150,
                                          "description": "What would prove this scenario wrong"}
                    },
                    "required": ["title", "condition", "mechanism", "predictions", "falsification"]
                }
            },
            "monitoring_dashboard": {
                "type": "array",
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "variable": {"type": "string"},
                        "current_value": {"type": "number"},
                        "scenario_1_threshold": {"type": "string", "maxLength": 30},
                        "scenario_2_threshold": {"type": "string", "maxLength": 30},
                    },
                    "required": ["variable"]
                }
            },
            "synthesis": {"type": "string", "maxLength": 500,
                          "description": "3-4 sentence bottom line connecting scenarios"}
        },
        "required": ["current_situation", "scenarios", "monitoring_dashboard", "synthesis"]
    }
}
```

Key verbosity controls:
- `maxLength` on all string fields
- `maxItems` on all arrays
- Numeric fields for magnitude (no prose)
- `enum` for direction (no "modestly bullish conditional on recession")

**Estimated changes**: ~200 lines (schemas + parsing).

---

### Step 4: Two system prompts for Phase 4

**File**: `impact_analysis_prompts.py`

Split current `SYSTEM_PROMPT` into:

#### `SYSTEM_PROMPT_RETROSPECTIVE`
- "You are explaining what happened and why"
- "Each track is an independent causal pathway that contributed to the event"
- "Do NOT make forward predictions in causal tracks — put those in residual_forward_view"
- "Quantitative data is MANDATORY per track — cite specific numbers from the evidence"
- "Max 4 tracks. If you have more, merge the weaker ones"

#### `SYSTEM_PROMPT_PROSPECTIVE`
- "You are filling in a scenario analysis skeleton with causal mechanisms and human-readable names"
- "The scenario structure (how many scenarios, which analogs support each) is pre-computed from historical data — do NOT change the structure"
- "Your job: name the scenarios, write the causal mechanism, write the analog basis, write the falsification criterion"
- "Do NOT assign probabilities — the analog counts ARE the probability signal"
- "Keep predictions grounded in the forward return data provided in the scenario skeleton"
- Include the scenario skeleton in the prompt so Opus fills in the blanks

**Also**: update `get_insight_prompt()` to branch on `temporal_direction` and include scenario skeleton for prospective mode.

**Estimated changes**: ~100 lines.

---

### Step 5: Route Phase 4 based on temporal_direction

**Files**: `synthesis_phase.py`, `impact_analysis.py`

In `_analyze_insight()` (or its replacement):

```python
temporal_direction = state.get("_edf_knowledge_tree", {}).get("temporal_direction", "prospective")

if temporal_direction == "retrospective":
    tool = _get_retrospective_tool()
    system = SYSTEM_PROMPT_RETROSPECTIVE
    prompt = get_retrospective_prompt(**data)
else:
    tool = _get_prospective_tool()
    system = SYSTEM_PROMPT_PROSPECTIVE
    prompt = get_prospective_prompt(**data, scenario_skeleton=state.get("scenario_skeleton", {}))
```

Update `_parse_insight_tool_result()` to handle both tool output shapes. Both produce an `insight_output` dict with `output_mode` field set to `"retrospective"` or `"prospective"`.

Update `synthesis_phase.py` verification prompt to match the mode (retrospective checks completeness of causal explanation; prospective checks scenario coverage and falsification criteria).

**Also**: skip `store_chains()` call in `run_asset_impact()` during this refactor. The chain storage logic parses the old track format and needs a separate update once the new format stabilizes. Add TODO in CLAUDE.md.

**Estimated changes**: ~80 lines.

---

### Step 6: Two formatters for human-readable output

**File**: `insight_orchestrator.py` — replace `format_insight()`

Remove the condensed summary section entirely (the new format is already concise enough).

#### `format_causal_decomposition(state)`:
```
CAUSAL DECOMPOSITION: {trigger_event}
================================================================
TRIGGER: {description} ({date})

TRACK 1: {title} ({confidence}%)
  {mechanism}
  Evidence: {evidence_summary}
  Data: {metric}: {value} | {metric}: {value}

TRACK 2: ...

SYNTHESIS: {cross_track_synthesis}

FORWARD VIEW: {residual_forward_view}

DATA GAPS: {gap1} | {gap2}
================================================================
```

Target: ~40-60 lines.

#### `format_scenario_analysis(state)`:
```
SCENARIO ANALYSIS: {current_situation}
================================================================
BASE RATES ({total_episodes} episodes):
  Direction: {pct_positive}% positive | Magnitude: median {median}%
  Range: [{min}% to {max}%] | Recovery: median {days} days

SCENARIO 1: {title} ({analog_count}/{total} analogs)
  Condition: {condition}
  Mechanism: {mechanism}
  Basis: {analog_basis}
  Predictions:
    {variable}: {direction} {magnitude_low}% to {magnitude_high}% ({timeframe_days}d)
  Falsification: {falsification}

SCENARIO 2: ...

MONITORING DASHBOARD:
  {variable}: {current_value} | S1: {threshold} | S2: {threshold}

BOTTOM LINE: {synthesis}
================================================================
```

For 0-episode case (novel event):
```
BASE RATES: No historical episodes found
SCENARIOS: Constructed from causal chain analysis (no historical grounding)
```

Target: ~50-80 lines.

Route in `format_insight()` based on `state.get("insight_output", {}).get("output_mode")`.

**Estimated changes**: ~120 lines.

---

### Step 7: Prediction ledger (for future scoring)

**New file**: `subproject_risk_intelligence/prediction_store.py`

Minimal append-only store. After prospective output is generated, extract predictions:

```python
def store_predictions(insight_output: dict, query: str, run_id: str):
    """Extract predictions from scenario output and append to ledger."""
    predictions = []
    for scenario in insight_output.get("scenarios", []):
        for pred in scenario.get("predictions", []):
            predictions.append({
                "prediction_id": f"{run_id}_{pred['variable']}_{scenario['title'][:20]}",
                "query": query,
                "scenario": scenario["title"],
                "scenario_analog_count": scenario.get("analog_count"),
                "variable": pred["variable"],
                "direction": pred["direction"],
                "magnitude_low": pred.get("magnitude_low"),
                "magnitude_high": pred.get("magnitude_high"),
                "timeframe_days": pred["timeframe_days"],
                "falsification": scenario.get("falsification", ""),
                "created_at": datetime.now().isoformat(),
                "check_date": (datetime.now() + timedelta(days=pred["timeframe_days"])).isoformat(),
                # Filled later by scoring:
                "actual_outcome": None,
                "score": None,
            })

    # Append to data/predictions.json
    ...
```

**Call site**: In `run_asset_impact()`, after synthesis phase completes, if output mode is prospective.

Scoring cron (future step, not in this plan): reads `predictions.json`, fetches actual data for expired check_dates, scores.

**Estimated changes**: ~80 lines.

---

### Step 8: Update verification prompt for both modes

**File**: `synthesis_prompts.py`

Split `VERIFICATION_PROMPT` into:

#### `VERIFICATION_PROMPT_RETROSPECTIVE`:
- "Are all causal mechanisms from the evidence addressed?"
- "Is quantitative data cited per track?"
- "Are there unsourced claims?"
- Same structure as current, minus forward-looking checks.

#### `VERIFICATION_PROMPT_PROSPECTIVE`:
- "Does each scenario have a falsification criterion?"
- "Are predictions grounded in the base rate data?"
- "Does the monitoring dashboard cover the distinguishing variables?"
- "Are there unsourced quantitative claims?"

**Estimated changes**: ~60 lines.

---

### Step 9: Update states.py and case runner

**File**: `states.py`

Add:
```python
class Prediction(TypedDict, total=False):
    prediction_id: str
    query: str
    scenario: str
    variable: str
    direction: str
    magnitude_low: float
    magnitude_high: float
    timeframe_days: int
    falsification: str
    created_at: str
    check_date: str
    actual_outcome: Optional[str]
    score: Optional[str]
```

Add to `RiskImpactState`:
```python
scenario_skeleton: Dict[str, Any]   # From scenario_builder.py
predictions: List[Prediction]        # Extracted from prospective output
```

**File**: `run_case_study.py`

Update the `FINAL_RESULT_STATE` debug log to include new fields:
```python
"output_mode": result.get("insight_output", {}).get("output_mode"),
"scenario_count": len(result.get("insight_output", {}).get("scenarios", [])),
"prediction_count": len(result.get("predictions", [])),
```

**Estimated changes**: ~35 lines.

---

### Step 10: Remove legacy fields

**Files**: `impact_analysis.py`, `synthesis_phase.py`, `insight_orchestrator.py`

The backward-compat fields (`direction: BULLISH/BEARISH/NEUTRAL`, `confidence: {score}`, `time_horizon`, `rationale`, `risk_factors`) are artifacts of the old single-direction output. With the new two-mode output, they're meaningless.

However: **defer this to a follow-up PR**. Keep the legacy population logic for now (populate from best scenario/track) so nothing downstream breaks. Remove once the new format is validated.

---

## Execution Order

| # | Step | Depends On | Risk | New Files |
|---|------|------------|------|-----------|
| 1 | EDF temporal_direction | None | Low — additive | — |
| 2 | Scenario builder | None | Low — pure computation | `scenario_builder.py` |
| 3 | Two tool schemas | None | Medium — core schema change | — |
| 4 | Two system prompts | Step 3 | Low — prompt text | — |
| 5 | Route Phase 4 + skip chain store | Steps 1, 3, 4 | Medium — wiring | — |
| 6 | Two formatters + remove condensed summary | Steps 3, 5 | Low — display only | — |
| 7 | Prediction ledger | Step 3 | Low — append-only store | `prediction_store.py` |
| 8 | Verification prompts | Steps 3, 5 | Low — prompt text | — |
| 9 | States + case runner | Step 7 | Low — additive | — |
| 10 | Legacy cleanup | All above validated | Low — defer | — |

**Steps 1, 2, 3, 4, 9 can be done in parallel** (no dependencies).
**Steps 5, 6, 7, 8 require steps above.**

## Validation

Run Case 1 (retrospective — "What caused the SaaS meltdown?") and Case 5 (prospective — "Equity put-call ratio surging") through the pipeline. Compare:

| Metric | Current | Target |
|--------|---------|--------|
| Output length (chars) | ~36K | <8K |
| Human read time | 10-15 min | 2-3 min |
| Scoreable predictions | 0 | 3-8 per prospective run |
| Analog grounding | Free-text "4/5 precedents" | Structured `analog_count/total_episodes` |

Rubric scoring: check "is the information present anywhere?" against existing Case 1/5 rubrics. No rubric rewrite needed for validation.

## New TODOs (add to CLAUDE.md after implementation)

- [ ] **Update chain storage for new output format** — `store_chains()` / `relationship_store.py` parses the old `InsightTrack` format to extract and persist logic chains. Skipped during output refactor. Needs update to extract chains from both `output_causal_decomposition` (retrospective) and `output_scenario_analysis` (prospective) schemas.
- [ ] **Rewrite case study rubrics** — Existing rubrics in `test_cases/` check for specific fields in the old track format. Rewrite to match new retrospective/prospective output structures.
- [ ] **Prediction scoring cron** — Read `data/predictions.json`, fetch actual data for expired `check_date` entries, score against `direction` + `magnitude_low`/`magnitude_high` + `falsification`.

## Files Changed Summary

| File | Change Type |
|------|-------------|
| `edf_decomposer_prompts.py` | Edit — add temporal_direction |
| `edf_decomposer.py` | Edit — add `get_temporal_direction()` |
| `scenario_builder.py` | **New** — build scenario skeletons from Phase 3 data |
| `impact_analysis.py` | Edit — two tool schemas, route by mode |
| `impact_analysis_prompts.py` | Edit — two system prompts, two prompt builders |
| `synthesis_phase.py` | Edit — route verification by mode, skip chain store |
| `synthesis_prompts.py` | Edit — two verification prompts |
| `insight_orchestrator.py` | Edit — call scenario_builder, two formatters, remove condensed summary |
| `states.py` | Edit — add Prediction, scenario_skeleton |
| `run_case_study.py` | Edit — log output_mode, scenario_count, prediction_count |
| `prediction_store.py` | **New** — append-only prediction ledger |
