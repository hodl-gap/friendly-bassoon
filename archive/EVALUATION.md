# Snapshot Evaluation -- 4 Runs

## Run 1: RDE Liquidity (Simple Query)

### Query Expansion
- **Query**: "What does rising RDE indicate about liquidity conditions?"
- **Type**: research_question
- **Dimensions** (3):
  1. Direct RDE-Liquidity Link -- "RDE rising liquidity conditions market"
  2. RDE as Liquidity Indicator -- "RDE liquidity indicator financial stress"
  3. RDE and Money Market Conditions -- "RDE money market liquidity tightening"

### Chain Extraction (first 2 groups)

**Group 1 -- Direct Liquidity Indicators:**
- rising Primary Credit usage [primary_credit] -> banking system liquidity stress [liquidity_stress]. Mechanism: Banks only use the discount window when unable to obtain liquidity elsewhere at market rates.
- large repo usage detected [repo_usage] -> sign of funding demand/stress [funding_stress]. Mechanism: Elevated repo usage signals banks need short-term cash.
- reserve balances decline [reserve_balances] -> tightening liquidity conditions [liquidity_tightening]. Mechanism: ~$400-500B decline reduces available liquidity through QT effects.

**Group 2 -- Multi-Hop Liquidity Resolution Chains:**
- bank reserves rebound to $3T [bank_reserves] -> short-term funding liquidity resolved [funding_liquidity] -> shift to long-biased futures positioning [futures_bias]. Mechanism: Higher reserves ease funding stress -> reduces risk-off pressure.
- TGA being released [tga] -> bank reserves increase [bank_reserves] -> SOFR/REPO/HIBOR stabilize [sofr]. Mechanism: Treasury drawdown releases cash into banking system.

### Confidence
```
overall_score: 0.85
chain_count: 6
source_diversity: 10
confidence_level: High
strongest_chain: "Primary Credit spikes -> precede/coincide with major financial crises (2008: $100B+, 2020: $60B, 2023: $90B, current: $9.87B +26.72%)"
```

### Gap Detection
- **Coverage**: PARTIAL, 3 gaps detected (out of 7 categories evaluated; 4 were COVERED)

| Category | Status | Fill Method | Instruments / Indicator |
|---|---|---|---|
| topic_not_covered | COVERED | web_chain_extraction | -- |
| historical_precedent_depth | UNFILLABLE (no_dates_found) | historical_analog | indicator: Primary Credit |
| quantified_relationships | FILLED (corr=0.85, 62 pts) | data_fetch | spy, qqq, vix |
| monitoring_thresholds | COVERED | web_search | -- |
| event_calendar | FILLED (FOMC schedule) | web_search | -- |
| mechanism_conditions | COVERED | web_search | -- |
| exit_criteria | COVERED | web_search | -- |

---

## Run 2: Global Macro (Complex Query)

### Query Expansion
- **Query**: "What is the impact on global liquidity and fiat currency from: (1) global stockpiling demand, (2) AI investment cycle, (3) global fiscal spending expansion, (4) defense and public investment increase, (5) China domestic demand policy pivot, and (6) China demand recovery from deeply negative to neutral levels?"
- **Type**: research_question
- **Dimensions** (6):
  1. Monetary Base Expansion & Reserve Accumulation -- "Central bank balance sheet expansion, reserve accumulation, and monetary base growth..."
  2. Commodity & FX Pressure from Demand Surge -- "Commodity price inflation, currency appreciation pressures..."
  3. Real Rates & Liquidity Conditions -- "Real interest rates, liquidity conditions, and inflation expectations..."
  4. Capital Flows & Cross-Border Liquidity -- "Cross-border capital flows, emerging market liquidity..."
  5. Fiat Currency Debasement & Purchasing Power -- "Fiat currency debasement, purchasing power erosion..."
  6. Debt Issuance & Credit Expansion -- "Government debt issuance, credit expansion..."

### Chain Extraction (first 2 groups)

**Group 1 -- Global Liquidity Expansion Mechanisms:**
- fiscal_expansion -> bank_reserves -> funding_conditions -> asset_price_rally. Mechanism: Government spending increases banking system reserves -> eased funding conditions reduce short-term premia -> lower yields support risk-taking.
- qe -> fed_balance_sheet -> bank_reserves -> funding_conditions. Mechanism: Fed asset purchases ($105B since Dec 2025, $1.26T projected 2026 scale) -> increases reserves and system liquidity.
- global_rate_cut_count -> fed_rate_cut_possibility -> policy_risk_ease. Mechanism: 64 rate cuts YTD raises odds of Fed alignment.
- global_policy_easing -> asset_price_rally. Mechanism: Policy rate cuts (4.8% -> 4.4% -> 3.9% path) lower yields, increase present value of assets.

**Group 2 -- Fiscal Spending and Currency Debasement:**
- fiscal_spending -> ycc_probability -> bond_yield_control. Mechanism: Large government spending ($7T+) may require yield curve control to manage borrowing costs...

### Confidence
```
overall_score: 0.85
chain_count: 9
source_diversity: 8
confidence_level: High
strongest_chain: "fiscal_expansion -> bank_reserves -> funding_conditions -> asset_price_rally"
```

### Gap Detection
- **Coverage**: PARTIAL, 4 gaps detected

| Category | Status | Fill Method | Instruments / Indicator |
|---|---|---|---|
| topic_not_covered | FILLED (19 chains, 18 verified quotes) | web_chain_extraction | -- |
| quantified_relationships | FILLED (corr=0.85, 62 pts) | data_fetch | spy, qqq, gld, dxy, usdjpy, btc |
| historical_precedent_depth | PARTIALLY_FILLED (conf=0.35) | web_search | -- |
| mechanism_conditions | PARTIALLY_FILLED (conf=0.35) | web_search | -- |

---

## Run 3: JPY Intervention (Mechanical Query)

### Query Expansion
- **Query**: "What is the direct effect of MOF or BOJ selling dollars to buy yen?"
- **Type**: research_question
- **Dimensions** (6):
  1. Mechanical Asset Flows -- "Japan central bank USD reserve drawdown yen purchase mechanics"
  2. Exchange Rate Impact -- "yen appreciation from BOJ dollar sales intervention effect"
  3. Monetary Base & Liquidity -- "BOJ yen injection monetary base expansion dollar sales"
  4. Policy Motivation & Timing -- "BOJ MOF yen weakness intervention when does Japan sell dollars"
  5. Market Spillovers -- "yen strength equity market impact BOJ dollar intervention consequences"
  6. Sterilization & Offsetting Operations -- "BOJ sterilization yen sales offset dollar intervention domestic money supply"

### Chain Extraction (first 2 groups)

**Group 1 -- Direct FX Intervention Effects:**
- MOF/BOJ dollar sell orders [fx_intervention_volume] -> USD/JPY exchange rate falls [usd_jpy] -> yen strengthens [jpy_strength]. Mechanism: Large USD sell supply from authorities increases yen demand, directly pushing USD/JPY lower. Parallel: Korean intervention ($5B+ -> 30+ won intraday move).
- authorities' dollar sell intervention [fx_intervention_volume] -> domestic USD liquidity injection [usd_liquidity_injection]. Mechanism: Sold dollars enter the domestic financial system, temporarily increasing USD availability.

**Group 2 -- Multi-Hop: Intervention -> Carry Unwind -> Global Liquidity:**
- JPY surge [jpy_intervention_risk] -> USD strength shaken [usd_strength_shaken] -> yen carry unwind and global liquidity contraction [carry_trade_unwind] -> BTC short-term adjustment and higher volatility [btc_volatility]. Mechanism: Intervention risk limits USD appreciation -> carry positions unwind -> reduced liquidity triggers corrections.
- JPY strength [jpy_strength] -> global liquidity tightening concerns [global_liquidity_tightening] -> carry trade unwind risk [carry_trade_unwind].

### Confidence
```
overall_score: 0.85
chain_count: 8
source_diversity: 7
confidence_level: High
strongest_chain: "MOF/BOJ dollar sell orders -> USD/JPY exchange rate falls -> yen strengthens"
```

### Gap Detection
- **Coverage**: PARTIAL, 3 gaps detected

| Category | Status | Fill Method | Instruments / Indicator |
|---|---|---|---|
| quantified_relationships | UNFILLABLE (no_relevant_results) | web_search | -- |
| historical_precedent_depth | UNFILLABLE (no_relevant_results) | web_search | -- |
| exit_criteria | PARTIALLY_FILLED (conf=0.30) | web_search | -- |

---

## Run 4: JPY Rally BTC (Event Query)

### Query Expansion
- **Query**: "On 2026-01-24, JPY/USD rallied to 155.90 rising 1.6% daily, and Japan finance minister warned speculators. What is the BTC impact?"
- **Type**: research_question
- **Temporal Reference**: reference_year=2026
- **Dimensions** (6):
  1. Mechanical Currency Operation -- "Japan selling USD buying JPY January 2026 intervention"
  2. Safe-Haven Flow & Risk-Off -- "JPY strength risk-off sentiment Bitcoin correlation January 2026"
  3. Policy Rate & Carry Trade Unwinding -- "BoJ rate hike carry trade unwind BTC impact 2026"
  4. Speculator Warning & Sentiment Shock -- "Japan finance minister speculator warning market reaction Bitcoin 2026"
  5. USD Weakness vs. BTC Denominated Risk -- "USD weakness Bitcoin price January 2026 margin liquidation"
  6. Volatility Spike & Leverage Cascade -- "FX volatility spike Bitcoin liquidations leverage January 2026"

### Chain Extraction (first 2 groups)

**Group 1 -- Direct JPY Intervention Impact on BTC:**
- JPY intervention risk [jpy_intervention_risk] -> yen carry unwind [carry_trade_unwind] -> BTC downward pressure [btc_price_down]. Mechanism: Intervention risk triggers unwinding of yen-funded carry positions -> forced liquidation reduces demand/liquidity for risk assets.
- JPY intervention risk [jpy_intervention_risk] -> USD strength shaken [usd_strength_shaken] -> carry unwind [carry_trade_unwind] -> BTC short-term correction & higher volatility. Mechanism: Intervention risk limits USD appreciation -> carry positions deleverage -> BTC volatility spikes.
- operational FX intervention possibility [operational_signalling] -> FX volatility spill to equities and crypto [fx_vol_spill]. Mechanism: PM's direct warning and NY Fed rate checks move beyond jawboning.

**Group 2 -- Historical Pattern-Based BTC Impact:**
- Japan rate hike events [boj_recent_hikes] -> Bitcoin fell 20-30% [btc_drawdown]. Precedents: Mar 2024 -22.28%, Jul 2024 -26.63%, Jan 2025 -30.34%.

### Confidence
```
overall_score: 0.85
chain_count: 8
source_diversity: 7
confidence_level: High
strongest_chain: "JPY intervention risk -> carry trade unwind -> BTC downward pressure"
```

### Gap Detection
- **Coverage**: PARTIAL, 3 gaps detected

| Category | Status | Fill Method | Instruments / Indicator |
|---|---|---|---|
| topic_not_covered | GAP (web search attempted, no trackable result) | web_search | -- |
| quantified_relationships | FILLED (corr=0.077, 65 pts) | data_fetch | usdjpy, btc |
| event_calendar | GAP (web search attempted, no trackable result) | web_search | -- |

---

## Cross-Run Comparison

### Query Expansion

| Run | Type | Dims | Notes |
|---|---|---|---|
| 1 (RDE Liquidity) | research_question | 3 | Simple single-concept query generates tight, focused dimensions all circling the same indicator. No temporal reference. |
| 2 (Global Macro) | research_question | 6 | Complex 6-factor query generates exactly 6 dimensions, one per factor. Each dimension maps to a distinct macro mechanism. Broadest search surface. |
| 3 (JPY Intervention) | research_question | 6 | Medium-complexity mechanical query generates 6 dimensions covering asset flows, FX impact, liquidity, policy, spillovers, and sterilization -- a well-structured decomposition of a single intervention mechanism. |
| 4 (JPY Rally BTC) | research_question | 6 | Event-specific query with date and data claim generates 6 dimensions. Notably detects temporal_reference (year=2026). Dimensions span mechanical, sentiment, policy, and leverage angles. |

**Observation**: All 4 runs are classified as `research_question`. The simple query (Run 1) generates only 3 dimensions, while all complex/medium queries generate 6. The expansion prompt correctly scales dimensionality to query complexity. Run 4 is the only one that populates `query_temporal_reference` (year: 2026), demonstrating temporal extraction from event-specific queries.

### Confidence Scoring

| Run | Score | Chains | Sources | Level | Strongest Chain |
|---|---|---|---|---|---|
| 1 (RDE) | 0.85 | 6 | 10 | High | Primary Credit spikes -> financial crises |
| 2 (Global Macro) | 0.85 | 9 | 8 | High | fiscal_expansion -> bank_reserves -> funding_conditions -> asset_price_rally |
| 3 (JPY Intervention) | 0.85 | 8 | 7 | High | MOF/BOJ dollar sell orders -> USD/JPY falls -> yen strengthens |
| 4 (JPY Rally BTC) | 0.85 | 8 | 7 | High | JPY intervention risk -> carry trade unwind -> BTC downward pressure |

**Observation**: All 4 runs score 0.85 (the threshold at which contradiction analysis is skipped). The score is invariant despite significant variation in chain count (6-9) and source diversity (7-10). This suggests the confidence scoring may be capped or insufficiently discriminative. Run 2 produces the most chains (9) and Run 1 has the highest source diversity (10), but neither is rewarded with a higher score.

### Gap Detection Patterns

| Run | Coverage | Gap Count | Fill Methods Used | Filled | Partially Filled | Unfillable |
|---|---|---|---|---|---|---|
| 1 (RDE) | PARTIAL | 3 (of 7 evaluated) | data_fetch, historical_analog, web_search | 2 | 0 | 1 |
| 2 (Global Macro) | PARTIAL | 4 | web_chain_extraction, data_fetch, web_search | 2 | 2 | 0 |
| 3 (JPY Intervention) | PARTIAL | 3 | web_search | 0 | 1 | 2 |
| 4 (JPY Rally BTC) | PARTIAL | 3 | web_search, data_fetch | 1 | 0 | 0 |

**Observation**: All runs are rated PARTIAL coverage. The `data_fetch` method (computing correlations from Yahoo data) is the most reliably successful fill method. `web_search` has mixed results -- it works for well-indexed topics (FOMC schedule in Run 1) but fails for specialized queries (intervention elasticity in Run 3). `historical_analog` failed in Run 1 (no_dates_found). Run 3 has the worst gap-filling outcome (2 unfillable), while Run 2 demonstrates the richest gap-filling pipeline (web_chain_extraction pulled 19 chains from 24 trusted sources).

---

## Assessment: Which examples are best for each prompt?

### 1. Query Expansion Prompt
**Best examples: Run 2 (Global Macro) and Run 4 (JPY Rally BTC)**

Run 2 demonstrates the expansion prompt's ability to decompose a 6-factor complex query into exactly 6 orthogonal dimensions, each with distinct reasoning and a well-crafted search query. The dimensions cover monetary base, commodity/FX, real rates, capital flows, currency debasement, and debt issuance -- showing comprehensive coverage.

Run 4 is the best example of temporal-aware expansion. It correctly extracts the reference year (2026) and generates dimensions that incorporate the specific event context (date, price level, official warning) rather than generic macro themes. The "Speculator Warning & Sentiment Shock" and "Volatility Spike & Leverage Cascade" dimensions show the prompt correctly identifies the query's event-driven nature.

### 2. Chain Extraction Prompt
**Best examples: Run 1 (RDE Liquidity) and Run 3 (JPY Intervention)**

Run 1 produces the cleanest chain extraction with well-separated direct indicators (Primary Credit, repo usage, reserve balances) and multi-hop resolution chains (bank reserves -> funding liquidity -> futures positioning). The chains have clear SOURCE attribution and CONNECTION labels. With 6 chains from 10 sources, the extraction is selective rather than noisy.

Run 3 excels at extracting mechanical chains (direct FX intervention -> USD/JPY -> yen strength) and then correctly linking them to second-order effects (carry unwind -> global liquidity contraction -> BTC volatility). The parallel case study (Korean intervention $5B -> 30+ won move) demonstrates cross-market analogical reasoning.

### 3. Synthesis Prompt
**Best example: Run 2 (Global Macro)**

Run 2's synthesis identifies 3 major consensus conclusions (Global Liquidity Expansion with 4 convergent paths, Currency Debasement with 3 convergent paths, Structural Investment Demand with 2 convergent paths). Each conclusion is supported by multiple independent causal paths that converge on the same outcome. The synthesis correctly separates temporal-specific data (Fed QE $105B, 64 rate cuts) from structural mechanisms. This is the most sophisticated synthesis across all runs because it manages multi-dimensional complexity while maintaining clear path-convergence structure.

Run 4 is the runner-up: its synthesis identifies a Primary Consensus (BTC downward pressure, 4 paths), Secondary Consensus (carry trade unwind mechanism, 3 paths), and includes specific quantified historical precedents (BTC drawdowns: -22.28%, -26.63%, -30.34% around BOJ hikes).

### 4. Gap Detection Prompt
**Best examples: Run 1 (RDE Liquidity) and Run 4 (JPY Rally BTC)**

Run 1 demonstrates the broadest gap taxonomy (7 categories evaluated, 4 pre-covered, 3 as gaps). The gap detection correctly identifies that the synthesis already covers monitoring thresholds, mechanism conditions, and exit criteria (marking them COVERED), while flagging missing historical precedent depth and quantified relationships. The data_fetch fill successfully computed SPY-QQQ correlation (0.85), and the web_search fill found the complete FOMC schedule.

Run 4 is the best example of gap detection on an event-specific query. It correctly identifies that the synthesis fails to validate the specific data claim in the query (JPY/USD 155.90 on 2026-01-24) as a `topic_not_covered` gap, and flags the missing BOJ policy decision date as an `event_calendar` gap. The quantified_relationships fill reveals a low USDJPY-BTC correlation (0.077), which is itself an important finding that challenges the synthesis's strong carry-unwind narrative.
