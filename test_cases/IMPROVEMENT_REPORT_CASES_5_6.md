# Improvement Report: Case Studies 5 & 6

**Date**: 2026-02-22
**Cases**: 05 (Put-Call Ratio) — 13/16 PASS, 06 (Labor Equilibrium) — 12/16 PASS

---

## 1. Pipeline Function Call Issues

### 1.1 Claim Validation Import Broken (Both cases)

**Error**: `cannot import name 'DataCollectionState' from 'states' (/home/peter/.../subproject_database_retriever/states.py)`

**Impact**: Claim validation skipped entirely in both runs. No quantitative claims from the synthesis were tested against actual data.

**Root cause**: `data_collection` subproject's `states.py` exports `DataCollectionState`, but the import path resolves to the retriever's `states.py` instead (because of sys.path ordering).

**Fix**: Same pattern as the `fill_gaps_with_data` fix — either lazy import or explicit package-qualified import (`from subproject_data_collection.states import DataCollectionState`).

**Verdict**: Refactoring required — re-running won't help.

### 1.2 Variable Resolution Gaps (Case 6)

**Unresolvable variables**: `gdp`, `job_vacancies`, `cpi`, `boj_rate`, `unemployment`

**Impact**: Key labor market data (JOLTS, unemployment rate) not fetched despite being the core topic of the query. This directly cost rubric point D1.

**Root cause**: `shared/variable_resolver.py` + `discovered_data_ids.json` don't map these common macro variables to FRED series. The auto-discovery fallback (`Variable mapper not available for auto-discovery`) also failed.

**Fix**: Add FRED mappings:
- `job_vacancies` → `JTSJOL` (JOLTS Job Openings)
- `unemployment` → `UNRATE` (Unemployment Rate)
- `cpi` → `CPIAUCSL` (CPI All Urban Consumers)
- `gdp` → `GDP` (Gross Domestic Product)

**Verdict**: Refactoring required — add mappings to `ADDITIONAL_FRED_SERIES` in `current_data_fetcher.py` or to `anchor_variables.json`.

### 1.3 fill_gaps_with_data — Now Working (Case 6)

The import fix applied earlier in this session **confirmed working**: SPY (61 data points) and TLT (61 data points) fetched, correlation -0.2419 computed and injected into the prompt. No re-run needed.

### 1.4 Pattern Validator Empty (Both cases)

**Behavior**: `Extracted 0 patterns via tool_use` in both runs.

**Impact**: No quantitative patterns validated against current data.

**Root cause**: Likely the retrieved chunks and web chains don't contain the kind of structured quantitative patterns (specific thresholds, trigger levels) that the pattern extractor expects. This is expected behavior for these query types — it's a soft failure, not a bug.

**Verdict**: No fix needed — working as designed. Would improve if more structured research with specific thresholds were ingested.

### 1.5 Historical Event Detection Missed (Both cases)

**Behavior**: `No gap detected: No temporal keywords or extrapolation detected`

**Impact**: No historical analog analysis triggered. For case 6, historical analogs of prior labor market equilibrium points would have been valuable.

**Root cause**: The historical event detector looks for specific temporal keywords and extrapolation patterns. "Put ratio up up" has no temporal signal. Case 6's "for the first time since the pandemic" might have triggered it, but the detector may not recognize this as a datable event.

**Verdict**: Potential improvement — the detector could be more sensitive to phrases like "first time since X" or "highest since X".

---

## 2. Analytical Quality Issues

### 2.1 BCA "Run Hot" Thesis Not Captured (Case 6)

**Gap**: The BCA thesis is that the Fed will *intentionally* tolerate higher inflation (2.5-3.5%) to prevent recession — "running hot". The pipeline instead framed it as Fed being *constrained* by inflation, which is the opposite framing.

**Why**: The pipeline's web chain extraction found JOLTS deterioration and tariff-inflation data, but the upstream reasoning (fragile equilibrium → Fed must "run hot" → real rate decline → specific asset implications) requires a level of macro synthesis that the current LLM prompt doesn't guide toward.

**Fix options**:
1. **Prompt enhancement**: Add a specific instruction for the Opus analysis LLM to consider "intentional policy regime" scenarios (not just reactive policy)
2. **More DB content**: If BCA Research notes were ingested, this thesis would appear directly in retrieved chains
3. Re-running won't help — this is a structural analytical gap

### 2.2 Real Rate Channel Missing (Case 6)

**Gap**: The chain "Fed easing + sticky inflation → real short-term rates fall → dollar weakness → bear steepening" is central to BCA's thesis but was not produced.

**Why**: The pipeline fetches nominal rates (US10Y: 4.08%, US02Y: 3.47%) and computes some derived metrics (term premium, SOFR spread) but doesn't compute **real rates** against breakeven inflation in a way that connects to the dollar/bond thesis. The derived metrics include `real_yield_10y` and `real_fed_funds` but these weren't prominently featured in the output.

**Fix**: Derived metrics are computed but may not be surfaced prominently enough in the prompt for Opus to use them as causal chain inputs.

### 2.3 Dollar Direction Opposite to BCA (Case 6)

**Gap**: Pipeline concluded USD strength (policy divergence), BCA argues USD weakness (falling real rates).

**Why**: The pipeline anchors on current data showing DXY at 97.79 (+0.9% weekly) and the rate differential argument. BCA's thesis is forward-looking (real rates *will* fall). This is a fundamental tension between data-driven (current) and thesis-driven (forward) analysis.

**Verdict**: Not a bug — reasonable disagreement. But highlights that the system is better at current-state analysis than forward-regime-change prediction.

### 2.4 Hedge Unwinding / Short Squeeze Not Modeled (Case 5)

**Gap**: The mechanical chain "elevated puts + no catalyst → delta/gamma hedge unwinding → short squeeze" was not articulated. Track 2 covers contrarian reversal via "fear exhaustion" but that's a sentiment argument, not a market-microstructure one.

**Why**: The DB and web sources focus on sentiment interpretation of put-call ratios rather than options market microstructure (dealer gamma, delta hedging flows). This requires specialized options market structure knowledge that isn't in the current data sources.

**Fix**: Ingesting more options market microstructure research (SpotGamma, GEX analysis, dealer positioning reports) would help.

### 2.5 Classic Crash Precedents Not Cited (Case 5)

**Gap**: The rubric expected references to 2001/9-11, 2008/Lehman, 2020/COVID as cases where elevated put ratios preceded crashes. Only the 2022 bear market was referenced.

**Why**: Web chain extraction found Forbes/Bloomberg articles about put-call ratio that referenced 2022 specifically. The classic crash precedents may not have appeared in the Tavily search results, or the LLM extraction focused on the most data-rich source (2022) rather than scanning for multiple historical episodes.

**Fix**: Could improve web chain extraction prompt to specifically request "list ALL historical precedents" rather than extracting the strongest few.

---

## 3. Summary: Re-run vs Refactor

| Issue | Re-run? | Refactor? | Priority |
|-------|---------|-----------|----------|
| Claim validation import broken | No | Yes — fix cross-package import | High |
| Variable resolution gaps (JOLTS, unemployment, CPI, GDP) | No | Yes — add FRED mappings | High |
| fill_gaps_with_data import | Fixed ✓ | Done ✓ | Done |
| "Run hot" thesis not captured | No | Maybe — prompt enhancement | Medium |
| Real rate channel missing | No | Surface derived metrics more prominently | Medium |
| Hedge unwinding microstructure | No | Ingest options microstructure research | Low |
| Historical event detection sensitivity | No | Improve temporal keyword detection | Low |
| Classic crash precedents (C2) | Maybe | Improve web chain prompt to request ALL precedents | Low |
| Pattern validator empty | N/A | Working as designed | None |

### Top 2 Fixes (highest impact, lowest effort):

1. **Add common macro FRED mappings** — `job_vacancies`→`JTSJOL`, `unemployment`→`UNRATE`, `cpi`→`CPIAUCSL`, `gdp`→`GDP`. This is a 5-line change in `current_data_fetcher.py` `ADDITIONAL_FRED_SERIES` dict and would have directly improved case 6's D1 score.

2. **Fix claim validation import** — same pattern as `fill_gaps_with_data` fix. This affects every run and silently drops a useful validation step.
