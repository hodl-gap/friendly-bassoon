# Few-Shot Examples for Prompt Review

Extracted from pipeline run `20260211_075133` with query: "What does rising RDE indicate about liquidity conditions?"

Review these examples. Once approved, they get inserted into the corresponding `*_prompts.py` files.

---

## 1. Query Expansion (query_processing_prompts.py → QUERY_EXPANSION_PROMPT_SIMPLE)

**Where it goes:** Add as an example block after the "Output Format" section in `QUERY_EXPANSION_PROMPT_SIMPLE`.

### Example:

```
Original query: What does rising RDE indicate about liquidity conditions?

DIMENSION: Direct RDE-Liquidity Link
REASONING: Targets the core relationship between RDE movements and liquidity assessment in financial markets.
QUERY: RDE rising liquidity conditions market

DIMENSION: RDE as Liquidity Indicator
REASONING: Frames RDE explicitly as a diagnostic tool for understanding systemic liquidity tightness or ease.
QUERY: RDE liquidity indicator financial stress

DIMENSION: RDE and Money Market Conditions
REASONING: Connects RDE signals to the operational liquidity environment where short-term funding occurs.
QUERY: RDE money market liquidity tightening
```

**What this teaches the LLM:**
- 3 dimensions for a simple query (not 6)
- Each dimension rephrases the same core question, not tangential topics
- Reasoning is one sentence explaining *why* this angle matters
- Queries use concrete financial terms, not academic jargon

---

## 2. Logic Chain Extraction (answer_generation_prompts.py → LOGIC_CHAIN_PROMPT)

**Where it goes:** Replace the single small example at the end of `LOGIC_CHAIN_PROMPT` with this richer example.

### Example:

```
Query: What does rising RDE indicate about liquidity conditions?

## Direct Liquidity Indicators

**CHAIN:** rising Primary Credit usage [primary_credit] → banking system liquidity stress [liquidity_stress]
**MECHANISM:** Banks only use the discount window when unable to obtain liquidity elsewhere at market rates, as it carries higher-than-market interest rates and potential stigma; rising usage directly signals inability to access normal funding channels
**SOURCE:** Source 1, Source 2
**CONNECTION:** Single mechanism across multiple sources

**CHAIN:** large repo usage detected [repo_usage] → sign of funding demand/stress [funding_stress]
**MECHANISM:** Elevated repo usage signals banks need short-term cash and are turning to Federal Reserve facilities for emergency overnight liquidity
**SOURCE:** Source 8, Source 3, Source 4
**CONNECTION:** Single mechanism observed across multiple Fed data sources

## Multi-Hop Liquidity Resolution Chains

**CHAIN:** bank reserves rebound to $3T [bank_reserves] → short-term funding liquidity issue largely resolved [funding_liquidity] → shift to long-biased futures positioning [futures_bias]
**MECHANISM:** Higher reserves ease money-market funding stress → eased funding stress reduces risk-off pressure and supports long positioning in futures markets
**SOURCE:** Source 6 (steps 1-2), Source 6 (steps 2-3)
**CONNECTION:** Connected via [funding_liquidity] within Source 6

**CHAIN:** TGA being released [tga] → bank reserves increase [bank_reserves] → SOFR/REPO/HIBOR stabilize [sofr]
**MECHANISM:** Treasury drawdown releases cash into banking system increasing reserves → higher reserves reduce funding pressure and rate volatility in money markets
**SOURCE:** Source 10 (step 1), Source 10 (step 2)
**CONNECTION:** Connected via [bank_reserves] from Source 10 step 1 to step 2

## RRP Buffer and Reserve Impairment Chain

**CHAIN:** sharp increase in T-bills issuance [t_bills_issuance] → full use of RRP buffer [rrp_buffer_use] → reserve impairment $350B [reserve_impairment]
**MECHANISM:** Surge in T-bill issuance draws MMF funds out of RRP into T-bills → depletion of RRP buffer leads to effective reduction in bank reserves (in 2026 context, with RRP at $200B baseline)
**SOURCE:** Source 9
**CONNECTION:** Connected via [rrp_buffer_use] within Source 9
```

**What this teaches the LLM:**
- Group chains by theme (Direct Indicators / Multi-Hop / Buffer chains)
- Use [normalized_variable] brackets on every cause and effect
- Multi-hop chains show 3+ steps connected via intermediate variables
- CONNECTION field explains how sources link (via which normalized var)
- MECHANISM uses → arrows for multi-step explanations
- Numbers are contextualized ("in 2026 context") not stated as facts

---

## 3. Synthesis / Consensus (answer_generation_prompts.py → SYNTHESIS_PROMPT)

**Where it goes:** Add as example after the "Output Format" section in `SYNTHESIS_PROMPT`.

### Example:

```
Query: What does rising RDE indicate about liquidity conditions?

## CONSENSUS CONCLUSIONS

**CONCLUSION:** Rising RDE signals acute banking system liquidity stress
**SUPPORTING PATHS:**
- Path 1: Rising Primary Credit usage → banking system liquidity stress (Source: @FinanceLancelot / FRED)
- Path 2: Primary Credit spikes → precede/coincide with major financial crises (Source: @FinanceLancelot, historical pattern 2008/2020/2023)
- Path 3: Large repo usage → funding demand/stress (Source: FRED, Plan G Research)
**PATH_COUNT:** 3
**SOURCE_DIVERSITY:** 3
**CONFIDENCE:** High
**CONFIDENCE_SCORE:** 0.85
**CONFIDENCE_REASONING:** 3 independent paths from 3+ sources converge on same conclusion; historical pattern validated across 3 crisis episodes

**CONCLUSION:** Liquidity stress cascades to asset markets through two distinct pathways
**SUPPORTING PATHS:**
- Path 1: Fed RMP intervention → funding crisis → liquidity-sensitive assets collapsing → data center/AI financing hit (Source: Plan G Research)
- Path 2: Bank reserves rebound to $3T → funding liquidity resolved → shift to long-biased futures positioning (Source: Plan G Research)
**PATH_COUNT:** 2
**SOURCE_DIVERSITY:** 1
**CONFIDENCE:** Medium
**CONFIDENCE_SCORE:** 0.60
**CONFIDENCE_REASONING:** 2 paths but single source; cascading effects are logical but lack multi-source corroboration

## KEY VARIABLES TO MONITOR

**Immediate Liquidity Indicators:**
- Primary Credit facility usage - critical threshold $50B+ based on crisis precedents; current $9.87B [referenced in: Direct Liquidity]
- Overnight repo facility usage - watch for spikes >$25B [referenced in: Direct Liquidity]
- Bank reserve balances - $3T target for resolution [referenced in: Multi-Hop Resolution]

**Treasury/Fed Operations:**
- TGA drawdown releases [referenced in: Multi-Hop Resolution]
- RRP buffer utilization - baseline $200B, full depletion triggers reserve impairment [referenced in: RRP Buffer]
- T-bill issuance surge patterns [referenced in: RRP Buffer]

**Market Positioning:**
- CTA systematic positioning - potential $250B swing [referenced in: Crisis Escalation]
```

**What this teaches the LLM:**
- Two separate consensus conclusions (primary at 0.85, secondary at 0.60)
- Confidence scoring matches the rubric (3 paths + 3 sources = High)
- Lower confidence when single source despite 2 paths
- Variables grouped by category with specific thresholds
- Each variable references which chain group it comes from

---

## 4. Gap Detection (knowledge_gap_prompts.py → GAP_DETECTION_PROMPT)

**Where it goes:** Add as example at the end of `GAP_DETECTION_PROMPT`, before the "Rules:" section.

### Example:

```
Query: What does rising RDE indicate about liquidity conditions?

{
  "coverage_rating": "PARTIAL",
  "gap_count": 3,
  "gaps": [
    {
      "category": "topic_not_covered",
      "status": "COVERED",
      "found": "Synthesis directly answers the query: rising RDE (Primary Credit usage) indicates banking system liquidity stress through multiple causal chains.",
      "missing": null,
      "fill_method": "web_chain_extraction",
      "search_query": null,
      "instruments": null,
      "indicator_name": null
    },
    {
      "category": "historical_precedent_depth",
      "status": "GAP",
      "found": "Synthesis mentions 2008, 2020, 2023 crises with Primary Credit spikes but provides no specific dates or detailed outcomes.",
      "missing": "Specific dates and Primary Credit levels during 2008, 2020, 2023 crises; what market outcomes followed each spike.",
      "fill_method": "historical_analog",
      "search_query": null,
      "instruments": null,
      "indicator_name": "Primary Credit"
    },
    {
      "category": "quantified_relationships",
      "status": "GAP",
      "found": "Synthesis provides directional relationships but no correlation coefficients or measured strength.",
      "missing": "Correlation between Primary Credit usage and market drawdowns; lag between RDE spike and asset impact.",
      "fill_method": "data_fetch",
      "search_query": null,
      "instruments": ["spy", "qqq", "vix"],
      "instruments": null,
      "indicator_name": null
    },
    {
      "category": "monitoring_thresholds",
      "status": "COVERED",
      "found": "Synthesis specifies thresholds: Primary Credit $50B+ (crisis), overnight repo >$25B, bank reserves $3T target.",
      "missing": null,
      "fill_method": "web_search",
      "search_query": null,
      "instruments": null,
      "indicator_name": null
    },
    {
      "category": "event_calendar",
      "status": "GAP",
      "found": "No upcoming dated events that could trigger RDE changes.",
      "missing": "Upcoming Fed meetings or data releases affecting Primary Credit demand.",
      "fill_method": "web_search",
      "search_query": "Fed FOMC meeting schedule 2025 policy decisions",
      "instruments": null,
      "indicator_name": null
    },
    {
      "category": "mechanism_conditions",
      "status": "COVERED",
      "found": "Preconditions specified: TGA drawdown, RRP depletion, T-bill issuance surges, reserve declines.",
      "missing": null,
      "fill_method": "web_search",
      "search_query": null,
      "instruments": null,
      "indicator_name": null
    },
    {
      "category": "exit_criteria",
      "status": "COVERED",
      "found": "Bank reserves rebound to $3T+ resolves stress and shifts positioning long.",
      "missing": null,
      "fill_method": "web_search",
      "search_query": null,
      "instruments": null,
      "indicator_name": null
    }
  ]
}
```

**What this teaches the LLM:**
- 4 categories COVERED, 3 categories GAP → "PARTIAL" rating
- topic_not_covered is COVERED (synthesis actually answers the question)
- historical_precedent_depth uses `fill_method: "historical_analog"` with `indicator_name`
- quantified_relationships uses `fill_method: "data_fetch"` with `instruments` list
- event_calendar uses `fill_method: "web_search"` with specific `search_query`
- COVERED items have `missing: null` and no search_query
- "found" and "missing" fields are brief (1-2 sentences)

---

## Summary

| # | Prompt | File | What it shows |
|---|--------|------|---------------|
| 1 | Query Expansion | `query_processing_prompts.py` | Simple query → 3 focused dimensions |
| 2 | Chain Extraction | `answer_generation_prompts.py` | Grouped chains with normalized vars and multi-hop connections |
| 3 | Synthesis | `answer_generation_prompts.py` | Confidence scoring with path count + source diversity |
| 4 | Gap Detection | `knowledge_gap_prompts.py` | COVERED vs GAP classification with correct fill_method routing |
