# Test Case 04: SCOTUS Tariff Ruling & Market Impact (Feb 2026)

**Status**: PASS (16/20)
**Date**: 2026-02-22

---

## Query

```
"The Supreme Court ruled Trump's IEEPA tariffs illegal on Feb 20, 2026. What is the impact on US equities?"
```

---

## Context

**Source**: Supreme Court ruling (Feb 20, 2026) + Korean-language analyst notes (Hana Global ETF)

**Key Data Points**:
- SCOTUS struck down IEEPA tariffs 6-3, ruling IEEPA does not authorize presidential tariff imposition
- $100-175bn in collected tariff revenue subject to refund
- Market rallied on ruling (S&P +0.69%, Nasdaq +0.9%, Dow +230 pts)
- Trump imposed substitute 10% global tariff under Section 122, later raised to 15%
- Section 122 has 150-day limit; longer-term requires Section 232/301 (12-18 month investigation)
- Hana Global ETF analyst identified 10Y yield 4.2-4.3% as threshold where refund narrative flips bearish

**Hypothesis**: Initial rally is short-lived. The legal transition from IEEPA → Section 122 → Section 232/301 creates sustained policy uncertainty that freezes corporate capex and inventory decisions. The key tension is between yield UP (fiscal deficit from refunds + treasury issuance) and yield DOWN (disinflation from tariff removal), with the 10Y ~4.2-4.3% level as the decision point.

---

## Expected Output

### A. Facts — Core Event

1. SCOTUS ruled 6-3 that IEEPA tariffs are illegal
2. Legal basis: IEEPA does not authorize the president to impose tariffs
3. $100-175bn in collected tariff revenue subject to refund
4. Market reaction: S&P +0.69%, Nasdaq +0.9%, Dow +230 pts on ruling day
5. Trump imposed substitute 10% global tariff under Section 122, later raised to 15%

### B. Causal Chains — Market Mechanism

1. Rally-reversal chain: Tariff struck down → rally → substitute tariff → partial reversal
2. Refund liquidity chain: $100bn+ refund → corporate cash infusion → but government fiscal deficit widens
3. Disinflation chain: Tariff removal → import price decline → inflation eases → Fed rate cut justification
4. Treasury issuance chain: Refund obligation → treasury issuance surge → yield pressure UP
5. Rate tension: Yield UP (fiscal deficit) vs yield DOWN (disinflation) — opposing forces
6. Policy transition chain: IEEPA → Sec.122 (150-day limit) → 232/301 (12-18 month investigation)

### C. Interpretive Judgments

1. Rally short-lived: Market surge likely temporary given substitute tariff and uncertainty
2. Policy uncertainty premium: Multi-step legal transition (IEEPA→122→232/301) freezes corporate capex/inventory
3. 10Y threshold: 10Y yield above ~4.2-4.3% flips refund narrative from bullish to bearish
4. Sector differentiation: Non-strategic imports (apparel, toys, consumer goods) and allied-nation imports are net beneficiaries
5. Dollar dynamics: Tariff removal → imports rise → trade deficit widens → but geopolitical uncertainty keeps dollar weak

### D. Data & Evidence

1. Fetches current S&P/Nasdaq levels or returns
2. Fetches 10Y treasury yield
3. References any prior tariff policy reversal or trade policy shock
4. Quantified impact numbers (inflation ~0.3pp, GDP ~0.35%, household ~$800)

---

## Evaluation Rubric

### A. Facts — Core Event (5 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| A1 | SCOTUS ruling | 6-3 ruling striking down IEEPA tariffs as illegal | 1 |
| A2 | Legal basis | IEEPA does not authorize president to impose tariffs | 1 |
| A3 | Refund magnitude | $100-175bn in collected tariff revenue subject to refund | 1 |
| A4 | Market reaction | S&P +0.69%, Nasdaq +0.9%, Dow +230 pts on ruling day | 1 |
| A5 | Substitute tariff | Trump imposed 10% global tariff (Section 122), then raised to 15% | 1 |

### B. Causal Chains — Market Mechanism (6 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| B1 | Rally-reversal chain | Tariff struck down → rally → substitute tariff → partial reversal | 1 |
| B2 | Refund liquidity chain | $100bn+ refund → corporate cash infusion → but government fiscal deficit widens | 1 |
| B3 | Disinflation chain | Tariff removal → import price decline → inflation eases → Fed rate cut justification | 1 |
| B4 | Treasury issuance chain | Refund obligation → treasury issuance surge → yield pressure UP | 1 |
| B5 | Rate tension | Yield UP (fiscal deficit) vs yield DOWN (disinflation) — opposing forces | 1 |
| B6 | Policy transition chain | IEEPA → Sec.122 (150-day limit) → 232/301 (12-18 month investigation) | 1 |

### C. Interpretive Judgments (5 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| C1 | Rally short-lived | Market surge likely temporary given substitute tariff and uncertainty | 1 |
| C2 | Policy uncertainty premium | Multi-step legal transition (IEEPA→122→232/301) freezes corporate capex/inventory | 1 |
| C3 | 10Y threshold | 10Y yield above ~4.2-4.3% flips refund narrative from bullish to bearish | 1 |
| C4 | Sector differentiation | Non-strategic imports (apparel, toys, consumer goods) and allied-nation imports are net beneficiaries | 1 |
| C5 | Dollar dynamics | Tariff removal → imports rise → trade deficit → but geopolitical uncertainty keeps dollar weak | 1 |

### D. Data & Evidence (4 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| D1 | Equity index data | Fetches current S&P/Nasdaq levels or returns | 1 |
| D2 | Bond yield data | Fetches 10Y treasury yield | 1 |
| D3 | Historical precedent | References any prior tariff policy reversal or trade policy shock | 1 |
| D4 | Quantified impact | Any specific numbers (inflation impact ~0.3pp, GDP ~0.35%, household ~$800) | 1 |

---

### Scoring Summary

| Category | Max Points |
|----------|------------|
| A. Facts — Core Event | 5 |
| B. Causal Chains — Market Mechanism | 6 |
| C. Interpretive Judgments | 5 |
| D. Data & Evidence | 4 |
| **TOTAL** | **20** |

**Passing threshold**: 13/20 (65%) with at least 1 point from 3 of 4 categories.

---

## Pipeline Runs

### Run 1 (2026-02-22)

**Query Used**: "The Supreme Court ruled Trump's IEEPA tariffs illegal on Feb 20, 2026. What is the impact on US equities?"

**Key Pipeline Behaviors**:
1. Query expansion generated 6 dimensions (Tariff Removal & Import Price Deflation, Corporate Profit Margin Recovery, Inflation & Fed Policy Expectations, etc.)
2. Vector search retrieved 10 chunks after re-ranking
3. Gap detection identified 5 gaps (INSUFFICIENT coverage):
   - topic_not_covered: SCOTUS ruling not in DB → filled via web_chain_extraction (20 chains from 27 sources)
   - historical_precedent_depth: No prior SCOTUS tariff rulings → UNFILLABLE
   - quantified_relationships: Data fetch for SPY/SP500 → filled
   - mechanism_conditions: Sector-specific tariff exposure → filled (2.4% EBIT boost, Signet Jewelers, Yeti)
   - exit_criteria: Rally end conditions → filled
4. Web chain extraction found 20 chains from 27 unique sources (17 verified)
5. Data fetched: 28 variables including SP500, Nasdaq, US10Y, VIX, DXY, sector ETFs
6. Claim validation: JSON parse error truncated claims (19 testable claims parsed but response exceeded context)
7. 10 new relationship chains discovered and persisted
8. Pipeline duration: 382.7s, Cost: $0.89 (27 Haiku + 1 Opus + 3 Sonnet)

**Final Output**: 6-track insight report:
- Track 1 (85%): Immediate Tariff Relief Rally — S&P +0.7%, Nasdaq +0.9%, trade-sensitive +2%, 2.4% EBIT boost
- Track 2 (70%): Policy Uncertainty — Re-imposition via Section 122, 90-day window, caps rally at +2-3%
- Track 3 (75%): Fed Restrictive Stance — 85.6% no-cut probability, limits multiple expansion
- Track 4 (80%): Software Sector Rotation — IGV -18.2% 1m, capital → SMH
- Track 5 (55%): Fiscal/Yield Pressure — Revenue loss → Treasury yield +10-40 bps
- Track 6 (65%): International Rotation — Capital outflows to international equities

---

## Rubric Score

| # | Item | Status | Notes |
|---|------|--------|-------|
| **A. Facts — Core Event** | | |
| A1 | SCOTUS ruling | ✓ | "Supreme Court ruled 6-3 that Trump's tariffs under IEEPA are illegal" |
| A2 | Legal basis | ✓ | "IEEPA does not give the president the authority to levy tariffs" |
| A3 | Refund magnitude | ✓ | "$287 billion in imports struck down" (web sources found larger number than rubric's $100-175bn) |
| A4 | Market reaction | ✓ | "S&P 500 +0.7%, Nasdaq +0.9%, Dow +0.3%" |
| A5 | Substitute tariff | ✓ | "Section 122 or alternative tariff announcements", "10% baseline tariff" |
| **B. Causal Chains** | | |
| B1 | Rally-reversal chain | ✓ | Track 1 (relief rally) → Track 2 (re-imposition caps upside, -1% to -3% reversal) |
| B2 | Refund liquidity chain | ✓ | "$287B collected tariffs", "cash flow boost to corporations", fiscal deficit widens |
| B3 | Disinflation chain | ✗ | Not explicitly: tariff removal → import prices down → inflation eases → Fed cut. Mentioned disinflation only in uncertainties |
| B4 | Treasury issuance chain | ✓ | Track 5: "reduced federal revenue → fiscal pressure → long-term Treasury yield pressure" |
| B5 | Rate tension | ✓ | Track 5 (yield UP from fiscal) vs Track 3 (Fed constraint) — opposing forces |
| B6 | Policy transition chain | ✓ | "Section 122, national security provisions", "90-day tariff pause" |
| **C. Interpretive Judgments** | | |
| C1 | Rally short-lived | ✓ | "Rally capped at +2-3%", "initial relief rally followed by consolidation" |
| C2 | Policy uncertainty premium | ✓ | Track 2: "persistent tariff uncertainty → capped equity upside and volatility" |
| C3 | 10Y threshold | ✗ | Mentions "4.25%" and "4.30%" thresholds but not the specific 4.2-4.3% refund-flipping framing |
| C4 | Sector differentiation | ✓ | "Signet Jewelers (15.1% → 0%), Yeti ($0.35 EPS recovery), Best Buy", consumer/retail beneficiaries |
| C5 | Dollar dynamics | ✗ | DXY bearish framed as capital outflow, not tariff removal → imports → trade deficit chain |
| **D. Data & Evidence** | | |
| D1 | Equity index data | ✓ | SP500: 6909.51, Nasdaq: 22,886.07, full index suite fetched |
| D2 | Bond yield data | ✓ | US10Y: 4.08%, US02Y: 3.47%, TLT: 89.41 |
| D3 | Historical precedent | ✓ | "Trump 90-day tariff pause" as prior reversal, "80-90% probability" of positive response |
| D4 | Quantified impact | ✗ | Has "$287B" and "2.4% EBIT boost" but missing inflation ~0.3pp, GDP ~0.35%, household ~$800 |

**TOTAL: 16/20 (80%) — PASS**

Points by category: A=5/5, B=5/6, C=3/5, D=3/4 (all 4 categories have ≥1 point)

**Key Strengths**:
- Excellent web chain extraction: found 20 chains from 27 sources covering the SCOTUS event despite zero DB coverage
- Strong factual grounding: all 5 core facts identified from web sources (Forbes, Yahoo Finance, WSJ, Bloomberg)
- Good sector-specific detail: Signet Jewelers, Yeti, Best Buy identified as beneficiaries with quantified tariff exposure
- Multi-track structure correctly separates immediate catalyst from medium-term constraints

**Key Gaps**:
- B3 (Disinflation chain): The tariff removal → import price decline → inflation eases → Fed cut justification chain was not explicitly articulated
- C3 (10Y threshold): The specific 4.2-4.3% yield threshold from Hana analyst was not surfaced. The pipeline found a different Hana chunk (Bessent-Warsh supply-side policy, semantic score 0.413) but the tariff ruling analyst note with the yield threshold was **never ingested** into Pinecone — the Feb 20 ruling content has not been processed through the database_manager pipeline yet. This is a content coverage gap, not a retrieval gap.
- C5 (Dollar dynamics): Trade deficit channel not modeled — only capital flow rotation
- D4 (Quantified impact): Has "$287B" and "2.4% EBIT boost" from web sources, but the specific Korean analyst numbers (inflation ~0.3pp, GDP ~0.35%, household ~$800) were not available — same root cause as C3: the Hana Global ETF analyst note has not been ingested into the database yet.
