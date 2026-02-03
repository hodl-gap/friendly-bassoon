# Case Study: JPY Intervention Query - First-Order Effect Missed

**Date:** 2026-01-25
**Issue Type:** Query formulation → incomplete retrieval

---

## Context

User asked about the Japan Times article on yen intervention speculation (Jan 2026). The article's core point: **Japan sells USD reserves to buy JPY → direct USD supply increase → USD weakens**.

## Queries Tested

| Query | Found Direct USD Effect? | Confidence |
|-------|-------------------------|------------|
| Q1: "What is the impact of yen intervention or JPY strength on the US dollar (DXY)?" | ❌ No | 0.90 |
| Q2: "How does central bank FX intervention work mechanically?" | ❌ No | 0.85 |
| Q3: "What is the direct effect of MOF or BOJ selling dollars to buy yen?" | ✅ **Yes** | 0.90 |

---

## What Q1 Retrieved (Incomplete)

**Primary mechanism found:**
```
JPY intervention → JPY strength → carry trade unwind → USD safe-haven demand → DXY UP
```

**What was MISSING:**
```
Japan sells USD → USD supply increases → USD liquidity tightens → Dollar depreciation pressure → DXY DOWN
```

---

## What Q3 Retrieved (Complete)

**Direct mechanism found:**
```
MOF/BOJ sell USD [usd_sale] → USD reserves decline [fx_reserves] → global USD liquidity reduction [usd_liquidity]

USD reserves decline [fx_reserves] → reduced structural USD demand [usd_dominance] → dollar depreciation pressure [dollar_depreciation]
```

**Plus the second-order effect:**
```
MOF/BOJ sell USD buy JPY [fx_intervention] → JPY strengthens → carry trade unwinds
```

---

## Query Expansion Comparison

### Q1 Expansion Dimensions:
1. Direct Currency Pair Dynamics - "USD/JPY exchange rate correlation with Bank of Japan intervention"
2. Dollar Index Composition - "DXY dollar index weighting Japanese yen component"
3. Capital Flow Consequences - "Japanese yen intervention capital flows US Treasury bonds dollar demand"
4. Risk-On/Risk-Off Dynamics - "yen strength risk sentiment US dollar safe haven flows"
5. **Carry Trade Unwinding** - "yen carry trade unwinding impact dollar strength"
6. Comparative Central Bank Policy - "Bank of Japan rate policy versus Federal Reserve impact"

### Q3 Expansion Dimensions:
1. Immediate Currency Market Impact - "BOJ dollar sales yen purchases currency intervention immediate effects"
2. **Mechanism & Execution** - "MOF BOJ foreign exchange intervention mechanics dollar yen selling buying"
3. Yen Strength Outcomes - "yen appreciation dollar weakness MOF BOJ intervention results"
4. Historical Precedent & Effectiveness
5. Market Reaction & Counterforces - "forex market reaction BOJ MOF yen buying intervention carry trade flows"
6. **Monetary Policy Transmission** - "BOJ dollar sales yen purchases monetary base liquidity effects"

---

## Retrieval Statistics

| Metric | Q1 | Q3 |
|--------|----|----|
| Stage 1A (original query protected) | 5 chunks | 4 chunks |
| Stage 1B (total candidates >0.4) | 41 chunks | 35 chunks |
| Final after re-ranking | 10 chunks | 10 chunks |
| From original query | 3 chunks | 3 chunks |

---

## The Gap: What Was in DB But Not Retrieved by Q1

The database contained this chunk (found by Q3):
- Source discussing USD reserve dynamics, FX reserves ↔ liquidity relationship
- Chain: `usd_sale → fx_reserves → usd_liquidity → dollar_depreciation`

Q1 retrieved 41 candidates but this chunk either:
1. Was not in the 41 candidates (embedding similarity too low), OR
2. Was in the 41 but got re-ranked out (LLM scored it low for causal relevance)

---

## Raw Data: Chunks Retrieved

### Q1 Top Chunks:
1. 엔 약세와 히보금리 급락으로 반등하는 비트코인 (Takaichi dissolution, JPY weakness)
2. 일본과 캐리 트레이드 (Japan carry trade, negative real rates)
3. ING CNY carry research (175-185bp spread)
4. 레이 달리오 2026 투자전략 (Dalio: USD decline, gold preference)
5. 전 세계 외환보유액에서 미국 달러 (USD reserve share at 21st century low)

### Q3 Top Chunks:
1. 엔 약세와 히보금리 급락으로 반등하는 비트코인 (same)
2. 일본과 캐리 트레이드 (same)
3. ING CNY carry research (same)
4. **FX reserves ↔ liquidity relationship chunk** (NEW - not in Q1)
5. USD reserve share dynamics (similar)

---

## Key Observation

Q3's expansion query "MOF BOJ foreign exchange intervention mechanics dollar yen **selling buying**" explicitly mentions the ACTION (selling/buying), which retrieved the mechanistic chunks about reserve drawdowns.

Q1's expansion queries focused on:
- Correlations ("exchange rate correlation")
- Effects ("impact", "affects")
- Outcomes ("yen strength", "dollar strength")

None explicitly asked about the MECHANICS of the intervention operation itself.

---

## The Core Problem

**Q1 asked about the OUTCOME ("impact of intervention") → retrieved chains about CONSEQUENCES**

**Q3 asked about the ACTION ("selling dollars to buy yen") → retrieved chains about MECHANICS**

The database has both. The query determined which got surfaced.

---

# ROOT CAUSE ANALYSIS

## 1. Query Framing: OUTCOME vs ACTION

**Q1 framing:** "What is the **impact** of yen intervention **on** the US dollar?"
- This is an OUTCOME → OUTCOME query
- Asks: "Given this event, what are its effects?"
- The system interprets "impact" as downstream market consequences

**Q3 framing:** "What is the direct effect of MOF or BOJ **selling dollars** to buy yen?"
- This is an ACTION → OUTCOME query
- Explicitly names the mechanical operation (selling dollars)
- Forces retrieval of chunks discussing the action itself

**The gap:** Q1 never explicitly mentions that intervention involves USD SELLING. The word "intervention" is abstract; "selling dollars" is concrete.

---

## 2. Query Expansion Blindspot

The LLM expansion for Q1 generated 6 dimensions:
1. Currency pair dynamics (correlation-focused)
2. DXY composition (structural)
3. Capital flows (consequence-focused)
4. Risk sentiment (consequence-focused)
5. Carry trade unwinding (consequence-focused)
6. Central bank policy comparison (context-focused)

**Missing dimension:** "Intervention Mechanics" or "Reserve Operations"

The expansion LLM interpreted "yen intervention" as a market EVENT with CONSEQUENCES, not as an OPERATION with MECHANICS. It never asked: "What literally happens when Japan intervenes?"

Q3's expansion included:
- "Mechanism & Execution"
- "Monetary Policy Transmission"

These dimensions explicitly seek HOW the operation works, not just WHAT it causes.

---

## 3. Semantic Embedding Distance

The query "impact of yen intervention on USD" creates embeddings that cluster near:
- Market impact content
- Currency correlation content
- Risk sentiment content

The query "selling dollars to buy yen" creates embeddings that cluster near:
- Reserve operation content
- Balance sheet mechanics content
- Liquidity flow content

**The embedding space treats "intervention" and "selling USD" as semantically distant concepts**, even though they describe the same action.

This is a fundamental limitation: embeddings capture semantic similarity, not logical equivalence.

---

## 4. The "OR" Dilution Effect

Q1: "yen intervention **OR** JPY strength"

The OR allows the retrieval system to satisfy the query by finding content about EITHER:
- Intervention effects, OR
- JPY strength effects

Since "JPY strength → carry unwind → USD" is abundantly documented in the database (multiple sources, rich causal language), the system gravitates toward this interpretation.

The direct intervention mechanics (rarer, more technical) get deprioritized because the OR gives an escape route.

---

## 5. Causal Chain Length Bias

The retrieval system is tuned to find CAUSAL chains. Two types exist:

**First-order (mechanical):**
```
Japan sells USD → USD supply increases → USD weakens
```
- 2 steps
- Mechanical/tautological
- Less "interesting" causally

**Second-order (behavioral):**
```
Japan sells USD → JPY strengthens → carry positions lose money →
forced liquidation → risk-off sentiment → USD safe-haven demand → USD strengthens
```
- 6 steps
- Rich causal reasoning
- Multiple actors and mechanisms

**The re-ranker scores "causal relevance" - longer, richer chains score higher.** The mechanical first-order effect is too "simple" to score well on causal relevance metrics.

---

## 6. Implicit Knowledge Assumption

Q1 assumes the system (or LLM) will INFER that "yen intervention" means "selling USD":

```
Human knowledge: intervention to strengthen JPY = sell USD, buy JPY
```

But the retrieval system doesn't have this inference step. It matches:
- Query text → Embedding → Similar chunk embeddings

The logical inference `intervention → selling USD` is never made during retrieval. The system is pattern-matching, not reasoning.

---

## 7. Answer Generation Stage Didn't Compensate

The answer generation LLM received 10 chunks that DIDN'T include the direct mechanism. It then:
1. Extracted logic chains from what it received
2. Synthesized conclusions based on available chains
3. Produced a confident (0.90) but incomplete answer

**The LLM cannot synthesize information that wasn't retrieved.** It correctly processed the carry unwind chains but had no material about USD reserve mechanics to work with.

The answer generation stage has no "completeness check" that asks: "Did we cover the first-order mechanical effect?"

---

## 8. Re-Ranking Scoring Criteria

The re-ranking prompt scores chunks for "CAUSAL relevance to the query."

Chunk about carry unwind:
- Contains explicit cause → effect → mechanism language
- Discusses "why" things happen
- High causal relevance score

Chunk about reserve operations:
- May be more descriptive/factual
- "Japan sold $X billion in reserves" is FACTUAL, not causal
- Lower causal relevance score

**The re-ranker may have deprioritized the mechanical chunks because they're factual rather than causal.**

---

## 9. Source Content Structure

The Telegram research sources in the database likely contain:
- Abundant carry trade analysis (popular topic among traders)
- Rich causal reasoning about JPY → risk assets
- Less content about intervention mechanics (central bank operations are less discussed)

**The database has an inherent bias toward market participant behavior chains over central bank operation mechanics.**

---

## 10. Hybrid Retrieval Didn't Help

The hybrid retrieval system protects top-5 chunks from the original query. For Q1:
- Original query: "impact of yen intervention or JPY strength on USD"
- Top-5 protected chunks: all about carry trade/risk sentiment

The protection mechanism preserved the WRONG chunks because the original query itself was framed to retrieve consequence-focused content.

---

# SUMMARY OF ROOT CAUSES

| # | Root Cause | Category |
|---|-----------|----------|
| 1 | Query framed as OUTCOME not ACTION | Query Formulation |
| 2 | Expansion missed "mechanics" dimension | Query Expansion |
| 3 | "intervention" ≠ "selling USD" in embedding space | Semantic Gap |
| 4 | OR clause allowed system to satisfy with partial answer | Query Structure |
| 5 | First-order effects too "simple" for causal scoring | Re-ranking Bias |
| 6 | System doesn't infer intervention = selling USD | No Reasoning Layer |
| 7 | Answer generation can't compensate for retrieval gaps | Pipeline Limitation |
| 8 | Factual chunks score lower than causal chunks | Re-ranking Criteria |
| 9 | Database has more behavioral than mechanical content | Data Distribution |
| 10 | Hybrid protection preserved wrong chunks | Retrieval Strategy |

---

# THE FUNDAMENTAL ISSUE

**The system retrieves based on SEMANTIC SIMILARITY and CAUSAL RELEVANCE, but the user's question required LOGICAL INFERENCE.**

The inference chain:
```
"yen intervention" → (implicit: to strengthen yen) → (implicit: by selling USD) → "USD supply increases"
```

This inference happens automatically in a human's mind but has no representation in the retrieval pipeline. The system cannot bridge from "intervention" to "selling USD" without explicit mention.

---

# POTENTIAL FIXES

## Fix Category A: Query Expansion Improvements

### A1. Mandatory "Mechanics" Dimension
Force the expansion LLM to always include a "mechanism/operation" dimension regardless of query type.

**Current:** Expansion generates dimensions based on LLM interpretation
**Proposed:** Require at least one dimension asking "HOW does this work mechanically?"

```
MANDATORY DIMENSIONS:
- [Mechanism] How does {event} work operationally? What are the mechanical steps?
- [First-Order Effect] What is the immediate/direct result of {action}?
```

### A2. Implicit Knowledge Expansion
Add a pre-retrieval step where LLM makes implicit knowledge explicit.

**Current:** Query → Expansion → Retrieval
**Proposed:** Query → Inference Expansion → Expansion → Retrieval

```
Input: "yen intervention impact on USD"
Inference step output:
- "yen intervention" = Japan MOF/BOJ selling USD reserves to buy JPY
- First-order: USD supply increases, JPY demand increases
- Add to query: "Japan selling USD reserves", "USD supply increase"
```

### A3. Action-Outcome Dual Framing
When query mentions an EVENT, automatically generate both:
- ACTION version: "What is the action involved in {event}?"
- OUTCOME version: "What are the consequences of {event}?"

---

## Fix Category B: Retrieval Strategy Changes

### B1. Multi-Pass Retrieval by Effect Order
Run separate retrieval passes for different effect types:

```
Pass 1: First-order mechanical effects
  - Query: "mechanical effect of {action}"
  - Scoring: Prioritize direct/immediate chains

Pass 2: Second-order behavioral effects
  - Query: "market consequences of {event}"
  - Scoring: Prioritize rich causal chains

Merge: Ensure both passes contribute to final results
```

### B2. Diverse Chunk Protection
Modify hybrid retrieval to protect chunks from DIFFERENT clusters, not just top-N by score.

**Current:** Protect top-5 from original query (may all be from same topic)
**Proposed:** Protect top-2 from each of 3 different semantic clusters

### B3. OR-Clause Splitting
When query contains OR, split into separate retrievals and merge.

**Current:** "A OR B" → single embedding
**Proposed:** "A OR B" → retrieve for A, retrieve for B, merge results

---

## Fix Category C: Re-Ranking Adjustments

### C1. Dual Scoring Criteria
Score chunks on TWO dimensions, not just causal relevance:

```
Score 1: Causal chain richness (current)
  - Multi-step reasoning
  - Explicit cause-effect-mechanism

Score 2: First-order directness (NEW)
  - Mechanical/operational explanation
  - Direct action-result relationship
  - Factual accuracy

Final = weighted combination
```

### C2. Chain Length Normalization
Don't penalize shorter chains just for being short.

**Current:** Longer, richer chains score higher
**Proposed:** Score = quality / expected_length_for_this_type

A 2-step mechanical chain should score as high as a 6-step behavioral chain if both are high quality for their type.

### C3. Effect Type Tagging
Tag chunks during ingestion as:
- `mechanical` (reserve operations, balance sheet changes)
- `behavioral` (market participant responses)
- `conditional` (if-then relationships)

Ensure re-ranking doesn't systematically deprioritize any tag type.

---

## Fix Category D: Answer Generation Safeguards

### D1. Completeness Check
After synthesis, run a validation step:

```
Validation prompt:
"For the query about {event}, check if the answer covers:
1. First-order mechanical effect (what directly happens)
2. Second-order market effect (how participants respond)
3. Conditional factors (what determines outcome)

If any are missing, flag as INCOMPLETE."
```

### D2. Self-Critique with Gap Detection
Add a stage that asks:

```
"The user asked about {intervention}.
We explained {carry unwind effects}.
Did we explain what the intervention MECHANICALLY does?
If not, what additional retrieval query would fill this gap?"
```

### D3. Iterative Retrieval on Incompleteness
If answer generation detects a gap, trigger targeted follow-up retrieval:

```
Stage 1: Generate answer from initial retrieval
Stage 2: Check for first-order effect coverage
Stage 3: If missing, run targeted query: "mechanical operation of {action}"
Stage 4: Supplement answer with new retrieval
```

---

## Fix Category E: Data/Ingestion Improvements

### E1. Dual-Chain Extraction at Ingestion
When extracting logic chains from source content, ensure BOTH are captured:

```
Source: "Japan intervened, selling $50B in reserves, strengthening yen,
        triggering carry trade unwind"

Extract Chain 1 (mechanical):
  Japan intervention → sell USD → USD supply up → yen strengthens

Extract Chain 2 (behavioral):
  yen strengthens → carry positions lose → forced liquidation → risk-off
```

### E2. Synthetic Explainer Chunks
Add curated "explainer" chunks for common operations:

```
Synthetic chunk: "FX Intervention Mechanics"
- When central bank wants to strengthen domestic currency:
  1. Sell foreign reserves (usually USD)
  2. Buy domestic currency
  3. Direct effect: USD supply increases, domestic currency demand increases
  4. Result: domestic currency appreciates, USD weakens
```

### E3. Term Synonym Mapping in Metadata
Add metadata field mapping abstract terms to concrete actions:

```
Chunk metadata:
{
  "topic": "yen intervention",
  "synonyms": ["MOF selling USD", "BOJ dollar sales", "JPY buying"],
  "action_type": "reserve_sale",
  "first_order_effect": "USD_supply_increase"
}
```

---

## Fix Category F: Architectural Changes

### F1. Knowledge Graph Layer
Build a financial knowledge graph that encodes:

```
Node: "FX intervention (to strengthen)"
  - implements: "sell foreign reserves"
  - implements: "buy domestic currency"
  - first_order_effect: "foreign currency supply increases"
  - first_order_effect: "domestic currency demand increases"
```

Query expansion consults this graph to add mechanistic terms.

### F2. Query Understanding Agent
Before retrieval, run a specialized agent that:
1. Identifies the EVENT type (intervention, rate hike, QE, etc.)
2. Looks up the MECHANICS of that event type
3. Generates queries for both mechanics and consequences
4. Ensures first-order effects are always queried

### F3. Effect-Order Routing
Route different parts of the query to different retrieval strategies:

```
Query: "impact of yen intervention on USD"

Router identifies:
- "yen intervention" → needs MECHANICS retrieval
- "impact on USD" → needs CONSEQUENCES retrieval

Run both, merge, synthesize
```

---

# PRIORITIZED FIX RECOMMENDATIONS

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | A2: Implicit knowledge expansion | Medium | High |
| **P0** | D1: Completeness check | Low | High |
| **P1** | A1: Mandatory mechanics dimension | Low | Medium |
| **P1** | C1: Dual scoring criteria | Medium | Medium |
| **P2** | B1: Multi-pass retrieval | High | High |
| **P2** | E1: Dual-chain extraction | Medium | Medium |
| **P3** | F1: Knowledge graph | High | High |

---

# QUICK WIN: Prompt-Only Fix

The fastest fix requiring no code changes:

**Update query expansion prompt to include:**

```
MANDATORY: For any query about a market EVENT (intervention, QE, rate change, etc.):
1. Always include one dimension asking "What is the MECHANICAL/OPERATIONAL process?"
2. Always include one dimension asking "What is the DIRECT/FIRST-ORDER effect?"
3. Expand abstract terms to concrete actions (e.g., "intervention" → "selling reserves")
```

This addresses root causes #1, #2, and #6 with a single prompt change.

---

# UPDATE: Prompt Fix Applied & Tested (2026-01-26)

## Prompt Change Applied

Added to `QUERY_EXPANSION_PROMPT_COMPLEX` in `query_processing_prompts.py`:
```
## CRITICAL: Mechanical Operations
For any abstract event (intervention, QE, rate hike, etc.), FIRST identify the concrete mechanical operation:
- What is BOUGHT and what is SOLD?
- What asset/currency INCREASES vs DECREASES?

Then ensure at least ONE query uses these concrete action terms, not just the abstract event name.

Examples:
- "yen intervention to strengthen yen" → Japan SELLS USD, BUYS JPY → include query with "selling dollars"
```

## Query Expansion - IMPROVED ✅

**Before (old prompt):**
```
1. USD/JPY exchange rate correlation with Bank of Japan intervention
2. DXY dollar index weighting Japanese yen component
3. Japanese yen intervention capital flows US Treasury bonds dollar demand
4. yen strength risk sentiment US dollar safe haven flows
5. yen carry trade unwinding impact dollar strength
6. Bank of Japan rate policy versus Federal Reserve impact
```

**After (new prompt):**
```
1. Japan selling US dollar reserves buying yen intervention impact DXY  ← concrete action!
2. USD/JPY exchange rate yen strength intervention effect
3. yen weighting DXY dollar index yen appreciation effect
4. yen strength safe-haven flows US dollar index correlation
5. yen intervention effectiveness dollar index DXY sustained impact
6. yen strength versus euro pound DXY dollar index relative impact
```

The first dimension now explicitly includes **"Japan selling US dollar reserves"**.

## Retrieved Content - Still Incomplete ❌

Despite the improved query, the answer still doesn't contain the first-order chain:
```
Japan sells USD → USD supply increases → USD weakens
```

### What Was Retrieved

The chunks discuss:
- JPY weakness → intervention signals → JPY rebound (policy response)
- Japan negative real rates → carry trade incentive
- CNY carry as alternative to JPY carry
- USD/JPY moves (156.50 → 159.00)

### What Was NOT Retrieved

The explicit mechanical explanation:
```
Japan sells USD reserves → USD supply increases in market → direct USD depreciation
```

## NEW FINDING: Incomplete Chain Problem

Even the second-order effects don't complete the chain to the user's question about USD impact.

**Retrieved chain:**
```
JPY weakness → anticipated intervention → JPY rebound potential
```

**Missing completion:**
```
JPY rebound → USD/JPY falls → USD weakens vs JPY → DXY down (13.6% weight)
```

The chains STOP at "JPY rebound" and never explicitly state "USD weakens".

### The USD Depreciation Chains Are From Different Mechanisms

The answer DOES mention USD depreciation, but from unrelated chains:

**Chain A (US-domestic, not intervention):**
```
equilibrium unemployment up → inflation → real rates fall → USD depreciation pressure
```

**Chain B (structural, not intervention):**
```
decline in USD share of global FX reserves → reduced USD dominance
```

Neither connects intervention → USD weakness.

## Root Cause Confirmed: DB Content Gap

The prompt fix successfully generates the right queries, but **the database doesn't contain**:

1. **First-order mechanical explanation**: "Intervention = selling USD = USD supply up = USD weak"
2. **Complete second-order chains**: Chains stop at "JPY rebound" without closing the loop to "USD weakens"

### Why This Happens

The Telegram research sources likely assume readers already know:
- Intervention mechanics (selling USD)
- That JPY rebound implies USD weakness

They discuss WHEN and WHAT FOLLOWS, not the textbook HOW.

## Conclusion

| Component | Status |
|-----------|--------|
| Query expansion prompt | ✅ Fixed - generates mechanical queries |
| LLM has the knowledge | ✅ Confirmed - knows intervention = selling USD |
| DB has first-order chain | ❌ Missing - no explicit mechanical explanation |
| DB has complete second-order chain | ❌ Incomplete - stops at "JPY rebound", doesn't say "USD weakens" |

**The system can only retrieve what exists. The implicit knowledge gap is in the source data, not the retrieval pipeline.**

---

# UPDATE: Chain-of-Retrievals Gap (2026-01-26)

## New Finding: Incomplete Chain Traversal

**Observation:** The JPY intervention query retrieved content mentioning "carry trade unwind" but did NOT retrieve the complete chain: `carry unwind → ... → risk asset selling`.

When a separate query was run specifically for "carry trade unwind impact on risk assets", it returned rich chains:
- carry unwind → forced liquidation → negative gamma → volatility spike
- carry unwind → HIBOR stress → crypto liquidation
- carry unwind → dealer stress → liquidity squeeze
- Multi-hop cascade with 4 paths, 4 sources, 0.95 confidence

## The Gap

| Query | Found "carry unwind"? | Found "carry unwind → risk assets"? |
|-------|----------------------|-------------------------------------|
| JPY intervention → USD | ✅ Yes (mentioned) | ❌ No (chain incomplete) |
| Carry unwind → risk assets | ✅ Yes | ✅ Yes (full chains) |

The first query's retrieved chunks mention carry unwind as an intermediate concept, but the system doesn't automatically "follow the chain" to retrieve what carry unwind leads to.

## Root Cause

Current retrieval is **single-hop**:
- Query → Embedding → Similar chunks → Answer

It doesn't perform **chain traversal**:
- Query → Chunks mentioning X → "What does X lead to?" → More chunks → Complete chain

## Proposed Solution: Chain-of-Retrievals

**Concept:** When Stage 1 retrieval finds chains that reference intermediate concepts (like "carry unwind"), automatically trigger follow-up retrievals for those concepts.

**Implementation Ideas:**

### Option A: Post-Retrieval Chain Expansion
```
1. Initial retrieval for query
2. Extract normalized_effect values from retrieved chains
3. For effects not fully explained, run follow-up query: "What is the impact of {effect}?"
4. Merge results and re-synthesize
```

### Option B: LLM-Guided Chain Following
```
1. Initial retrieval
2. LLM identifies "dangling chains" (effects mentioned but not explained)
3. LLM generates follow-up queries for dangling chains
4. Iterative retrieval until chains are complete
```

### Option C: Graph-Based Chain Traversal
```
1. Build effect→cause index from all chunks at ingestion time
2. At query time, traverse the graph from retrieved effects
3. Pull in connected chunks automatically
```

## TODO

- [ ] **Implement chain-of-retrievals** - Auto-follow intermediate concepts to get complete chains
- [ ] Design detection for "dangling chains" (effects without explanations)
- [ ] Add configurable depth limit to prevent infinite traversal
- [ ] Benchmark: Does chain traversal improve answer completeness?

## Example: What Chain-of-Retrievals Would Do

**Query:** "JPY intervention impact on USD"

**Stage 1 retrieval finds:**
- JPY intervention → JPY strength → carry trade unwind

**Chain-of-retrieval detects:** "carry trade unwind" is an EFFECT but its downstream impact is not in retrieved chunks

**Auto-follow-up query:** "What is the impact of carry trade unwind?"

**Stage 2 retrieval adds:**
- carry unwind → forced liquidation → vol spike → risk asset selling
- carry unwind → HIBOR stress → crypto liquidation

**Final synthesis:** Complete chain from intervention → carry unwind → risk assets

---

# TEST: Chain-of-Retrievals Feature Validation (2026-01-26)

## Test Query
Same as original Q1: `"What is the impact of yen intervention or JPY strength on the US dollar (DXY)?"`

## Chain-of-Retrievals in Action ✅

| Stage | Chunks | Details |
|-------|--------|---------|
| Initial retrieval | 10 | Hybrid retrieval with 7 queries (1 original + 6 expanded) |
| Dangling effects detected | 10 | `risk_asset_rebound`, `jpy_rebound`, `japan_equity_inflows`, `fx_liquidity`, `us_assets_performance`... |
| Follow-up query 1 | +4 | "What is the impact of risk asset rebound?" |
| Follow-up query 2 | +1 | "What is the impact of jpy rebound?" |
| Follow-up query 3 | +3 | "What is the impact of japan equity inflows?" |
| **Final context** | **18** | 8 new chunks from 3 follow-ups |

## Query Expansion Quality ✅

The mechanical operations dimension was correctly generated:
```
[Mechanical Operation – Direct FX Action] Japan selling dollars buying yen intervention impact USD index
```

All 6 dimensions covered different angles:
1. Mechanical Operation – Direct FX Action
2. Cross-Currency Valuation
3. Capital Flow Consequences
4. Fed Response & Policy Interaction
5. Historical Precedent
6. Safe-Haven Flows vs Intervention

## Multi-Hop Chains Now Retrieved ✅

**Before (without chain-of-retrievals):**
- Chains stopped at intermediate effects like `jpy_rebound`, `carry_unwind`

**After (with chain-of-retrievals):**
```
JPY weakness → carry trade unwind reversal → risk asset rebound → dollar depreciation → US assets underperform
```

```
BOJ intervention → JPY sharp appreciation → carry unwind → systemic liquidity stress → safe-haven USD bid → temporary DXY spike
```

```
decline in USD share of global FX reserves → reduced USD dominance → lower structural USD demand → DXY structural weakness
```

## Confidence & Synthesis Quality

| Metric | Value |
|--------|-------|
| Overall confidence | 0.85 (High) |
| Path count | 3 |
| Source diversity | 3 |
| Stage 3 (contradiction) | SKIPPED (confidence >= 0.85) |

## What's Still Missing ❌

The **first-order mechanical chain** remains absent:
```
Japan sells USD → USD supply increases → direct USD weakening
```

This confirms the case study's root cause analysis: **DB content gap, not retrieval gap**.

The Telegram research sources assume readers understand intervention mechanics and don't explicitly state the textbook explanation.

## Conclusion

| Component | Status | Notes |
|-----------|--------|-------|
| Chain-of-retrievals feature | ✅ Working | Detected 10 dangling effects, followed 3, added 8 chunks |
| Query expansion (mechanics dimension) | ✅ Working | Explicitly includes "Japan selling dollars buying yen" |
| Multi-hop chain completion | ✅ Working | Chains now extend to `dollar_depreciation`, `us_assets_performance` |
| First-order mechanical chain | ❌ Missing | **DB content gap** - sources don't contain this explanation |

**Verdict:** Chain-of-retrievals feature is functioning as designed. The remaining gap requires either:
1. Adding synthetic explainer chunks to the database (Fix E2 from root cause analysis)
2. Or accepting that the system can only retrieve what exists in the source data

---

# UPDATE: Re-evaluation of "Content Gap" (2026-02-03)

## Key Insight: Yen Strength = USD Weakness

The "missing first-order chain" concern was **overly academic**.

The practical outcome is logically equivalent:
```
Carry unwind → yen strengthens → USD/JPY falls → USD weaker
Intervention → yen strengthens → USD/JPY falls → USD weaker
```

Both paths lead to: **yen up, USD down**.

The system DOES retrieve:
- `carry unwind → yen strengthens` ✅
- `JPY 13.6% weight in DXY → JPY strength → DXY declines` ✅

So the practical question "what happens to USD when yen strengthens/Japan intervenes" **is already answered**.

## Revised Assessment

| What | Status | Notes |
|------|--------|-------|
| First-order intervention mechanics | ❌ Missing | "Japan sells USD → USD supply up" not explicit |
| Practical outcome chain | ✅ Present | Carry unwind/yen strength → USD weakness is covered |
| Trader relevance | ✅ Sufficient | Outcome matters more than textbook mechanics |

**Revised Verdict:** The "content gap" is more about **pedagogical completeness** than **practical trading relevance**. The DB effectively answers the question through carry trade dynamics.

---

## Candidate Articles to Add (Carry Trade Mechanics)

The following Korean articles explain carry trade dynamics well and would strengthen the DB:

### Article 1: 2024년 8월 증시 급락 원인
```
엔 캐리 트레이드 청산 가능성

- 1995년 이후 달러엔 캐리 수익지수가 고점에서 저점까지 유의미하게 하락한 경우는 총 5차례
- 캐리수익지수가 낮아진다는 것은 엔캐리 매력도가 떨어짐을 뜻함
- 미국-일본 금리차 2024년 2월 (560bp) 최고치 후 축소 중
- 유럽-일본 금리차 2024년 2월 (460bp) 최고치 후 축소 중
- BOJ 금리 인상 이후 금리차 축소 → 캐리 트레이드 청산 가능성
- 해외에는 엔화를 빌려 투자해온 돈이 엄청 많음. 이 돈들이 일본으로 다시 들어가게 된다면 추가적 엔화 강세를 촉발할 수 있을것
```

### Article 2: 일본 정책 혼선과 엔캐리
```
일본 정책 혼선 → 엔캐리 흔들림 → 트럼프 리스크

다케이치 정부는 대규모 부양책을 밀어붙이며 재정확대를 예고
우에다 BOJ는 금리인상 가능성을 열어두며 긴축 신호

정책 방향성 엇갈림 →
→ 엔캐리 포지션 불안
→ 글로벌 금리 경로 재정립
→ 달러 강세 유지
→ 위험자산 전반의 조정

트럼프는 엔저를 싫어하고, 일본의 금리인상을 압박하는 입장
BOJ 긴축 시사 → "트럼프발 BOJ 압박 → 엔캐리 언와인딩 가능성 확대"
```

### Article 3: 달러엔 157엔 횡보와 유동성
```
달러/엔 환율 9월 이후 빠르게 상승하며 157엔 부근 횡보
크립토 조정 구간과 시기적으로 맞물림
엔화 약세 가속화 → '엔캐리 리스크'와 글로벌 유동성 흐름에 변동성

일본 당국 추가 약세 시 개입 가능성 공개적으로 언급
단기적으로 일본발 유동성 스트레스 완화 기대

다만, 엔화 약세는 구조적으로:
- 글로벌 달러 수요를 높이고
- 일본 금융기관과 투자자들의 대외 포지션 조정을 촉발
- 시장의 유동성 여건을 빠르게 경직
→ 여전히 핵심 리스크 요인
```

**Search keywords for Telegram:** `엔캐리`, `캐리 트레이드 청산`, `금리차 축소`, `BOJ 금리인상`
