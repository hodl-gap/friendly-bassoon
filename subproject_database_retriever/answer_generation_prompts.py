"""
Prompts for Answer Generation Module
"""

# Stage 1: Extract and organize logic chains
LOGIC_CHAIN_PROMPT = """You are analyzing financial research to extract logic chains relevant to a query.

Query: {query}

Research Context:
{context}

Instructions:
1. Identify logic chains (cause → effect relationships) relevant to the query
2. **CRITICAL: Use [normalized] variable names to connect chains across sources**
   - If Source 1 has: cause [A] → effect [B]
   - And Source 2 has: cause [B] → effect [C]
   - Then connect: A → B → C (multi-hop chain)
3. The ## CHAIN CONNECTIONS section lists which normalized variables appear as both causes and effects across chunks - USE THESE to build longer chains
4. Prioritize longer chains (3+ steps) over shorter ones - they capture more complete mechanisms
5. Group chains by theme/category (e.g., "Direct Effects", "Conditional Chains", "Risk/Reversal Chains")
6. Use the interpretation/what_happened context to supplement chain understanding
7. Output as structured list only - no narrative summary

**TEMPORAL AWARENESS (CRITICAL):**
- Check the ## TEMPORAL GUIDANCE section for data timeframe information
- If there's a TEMPORAL MISMATCH (query year differs from data years):
  - **PRIORITIZE LOGIC CHAINS** (cause → effect relationships) - these are timeless and transferable
  - **DE-EMPHASIZE ABSOLUTE VALUES** (specific numbers like "$1.26T", "83.4%") - these are time-bound
  - Present specific numbers as "in [data year] context" rather than current facts
  - Example: Instead of "Fed will inject $1.26T", say "The mechanism (QE → liquidity expansion) was projected at $1.26T scale in 2026 context"
- Structural patterns like "QE → balance sheet expansion → liquidity increase" remain valid across time periods
- The LOGIC CHAIN is the durable insight; the specific numbers are illustrative examples

**Chain Connection Priority:**
1. Multi-hop chains (3+ steps) connected via matching [normalized] variables
2. Chains with explicit connections listed in CHAIN CONNECTIONS section
3. Single-source chains if no connections available

Output Format:
## [Group Name]

**CHAIN:** cause [normalized] → effect [normalized] → [next effect if connected]
**MECHANISM:** mechanism for each step
**SOURCE:** which source(s) support this chain
**CONNECTION:** [if multi-source] "Connected via [normalized_var] from Source X to Source Y"

## Examples
<!-- [FEW-SHOT v1] Source: run_20260211_075133 (RDE) + run_20260211_081108 (JPY). Review & improve with more diverse examples. -->

### Example 1: Single-concept query with direct + multi-hop chains

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

### Example 2: Mechanical operation with cross-market analogies

Query: What is the direct effect of MOF or BOJ selling dollars to buy yen?

## Direct FX Intervention Effects

**CHAIN:** MOF/BOJ dollar sell orders [fx_intervention_volume] → USD/JPY exchange rate falls [usd_jpy] → yen strengthens [jpy_strength]
**MECHANISM:** Large USD sell supply from authorities increases yen demand, directly pushing USD/JPY lower. Parallel: Korean intervention ($5B+ → 30+ won intraday move)
**SOURCE:** Source 1, Source 3
**CONNECTION:** Single mechanism across multiple sources

## Multi-Hop: Intervention → Carry Unwind → Global Liquidity

**CHAIN:** JPY surge [jpy_intervention_risk] → USD strength shaken [usd_strength_shaken] → yen carry unwind and global liquidity contraction [carry_trade_unwind] → BTC short-term adjustment and higher volatility [btc_volatility]
**MECHANISM:** Intervention risk limits USD appreciation → carry positions unwind → reduced liquidity triggers corrections
**SOURCE:** Source 2 (all steps), Source 4 (intervention context)
**CONNECTION:** Multi-step chain within single source, supported by intervention context from Source 4"""


# Stage 2: Synthesize consensus and extract variables
SYNTHESIS_PROMPT = """You are synthesizing logic chains to identify consensus patterns and key monitoring variables.

Query: {query}

Logic Chains:
{chains}

Instructions:

## Part 1: Consensus Chains
Identify where MULTIPLE chains converge on the same conclusion through different paths.
- Look for different starting points that lead to the same end effect
- These represent higher-conviction conclusions supported by multiple reasoning paths
- Only include if 2+ chains support the same conclusion

## Part 2: Key Variables to Monitor
Extract specific, actionable variables/indicators mentioned across the chains.
- Group by category (e.g., Liquidity, Labor Market, Positioning)
- Include specific thresholds or levels if mentioned
- Note which chains reference each variable

**TEMPORAL NOTE:**
- Focus conclusions on the STRUCTURAL RELATIONSHIPS (the logic chains themselves)
- These patterns are transferable across time periods
- Specific threshold values from the data are contextual examples, not absolute targets
- Frame conclusions around the mechanisms, not the specific historical numbers

Output Format:

## CONSENSUS CONCLUSIONS

**CONCLUSION:** [the common end point - frame as a structural pattern]
**SUPPORTING PATHS:**
- Path 1: A → B → [conclusion] (Source: Institution1)
- Path 2: C → D → [conclusion] (Source: Institution2)
**PATH_COUNT:** [number of supporting paths, e.g., 3]
**SOURCE_DIVERSITY:** [number of unique institutions supporting this, e.g., 2]
**CONFIDENCE:** [High/Medium/Low based on path count AND source diversity]
**CONFIDENCE_SCORE:** [0.0-1.0: High=0.8+, Medium=0.5-0.8, Low=<0.5]
**CONFIDENCE_REASONING:** [Brief explanation: e.g., "3 paths from 2 independent sources converge"]

Confidence Guidelines:
- High (0.8+): 3+ paths from 2+ independent sources
- Medium (0.5-0.8): 2 paths OR single source with strong logic
- Low (<0.5): Single path, weak support, or contradictory evidence

## KEY VARIABLES TO MONITOR

**[Category Name]:**
- Variable 1 - threshold/level if known [referenced in: chain groups]
- Variable 2 - threshold/level if known [referenced in: chain groups]

Note: For variables with specific values, indicate these are from historical data context and would need updating for current application.

## Example
<!-- [FEW-SHOT v1] Source: run_20260211_081110 (JPY Rally BTC). Review & improve — consider adding a lower-confidence example. -->

Query: On 2026-01-24, JPY/USD rallied to 155.90 rising 1.6% daily, and Japan finance minister warned speculators. What is the BTC impact?

## CONSENSUS CONCLUSIONS

**CONCLUSION:** BTC faces downward pressure from JPY intervention risk through carry trade unwind
**SUPPORTING PATHS:**
- Path 1: JPY intervention risk → carry trade unwind → BTC selling pressure (Source: Plan G Research, Macro Jungle)
- Path 2: BOJ tightening events → BTC drawdowns of 20-30% (Source: historical pattern — Mar 2024 -22.28%, Jul 2024 -26.63%, Jan 2025 -30.34%)
- Path 3: BOJ rate expectations → yen strength → global liquidity tightening → carry unwind → BTC pressure (Source: Plan G Research)
- Path 4: BOJ hike + Fed cut expectations → carry profitability compression → risk asset liquidation (Source: Plan G Research)
**PATH_COUNT:** 4
**SOURCE_DIVERSITY:** 3
**CONFIDENCE:** High
**CONFIDENCE_SCORE:** 0.85
**CONFIDENCE_REASONING:** 4 independent paths from 3+ sources converge; historical pattern validated across 3 BOJ tightening episodes

**CONCLUSION:** Carry trade unwind is the primary transmission mechanism
**SUPPORTING PATHS:**
- Path 1: Intervention risk → carry position liquidation → forced USD repurchase → dollar shortage → SOFR spike (Source: Plan G Research)
- Path 2: BOJ rate hike → market liquidity drain → margin calls → forced deleveraging (Source: Macro Jungle)
- Path 3: Yen strength → global liquidity tightening concerns → carry trade compression (Source: Plan G Research)
**PATH_COUNT:** 3
**SOURCE_DIVERSITY:** 2
**CONFIDENCE:** High
**CONFIDENCE_SCORE:** 0.80
**CONFIDENCE_REASONING:** 3 paths from 2 sources with detailed mechanism descriptions

## KEY VARIABLES TO MONITOR

**Immediate Triggers:**
- JPY/USD level (currently 155.90, 1.6% daily rally) [referenced in: Direct Intervention Impact]
- BOJ intervention signals beyond jawboning [referenced in: Direct Intervention Impact]
- NY Fed rate check activity (operational coordination) [referenced in: Direct Intervention Impact]

**Liquidity Indicators:**
- SOFR spikes (carry unwind stress signal) [referenced in: Carry Trade Unwind]
- Global dollar liquidity conditions [referenced in: Multi-Hop chains]

**BTC Technical Levels:**
- Bear market targets: $70,000, $56,000 [referenced in: Historical Pattern]
- Tail risk: 42% market-implied probability for <$60k [referenced in: Historical Pattern]"""


# Stage 3: Identify contradicting evidence (Issue 5: Negative Evidence Handling)
# NOTE: Works from synthesis only (raw chunk context removed to reduce redundant tokens).
# The synthesis already contains all relevant logic chains, sources, and data points.
CONTRADICTION_PROMPT = """You are analyzing financial research to identify contradicting or weakening evidence.

Query: {query}

Consensus Synthesis:
{synthesis}

Instructions:
1. Identify any evidence WITHIN the synthesis that CONTRADICTS or WEAKENS the consensus conclusions
2. Look for:
   - Sources mentioned in the synthesis that disagree with each other
   - Conditions where the logic chain breaks down or has weak links
   - Historical examples where similar logic failed
   - Missing considerations that could invalidate conclusions
   - Alternative interpretations of the same data points
3. Be conservative - only flag genuine contradictions, not minor nuances or caveats
4. Use the sources, data points, and logic chains referenced in the synthesis as your evidence base

Output Format:

## CONTRADICTING EVIDENCE

**CONTRADICTION:** [what contradicts the consensus]
**SOURCE:** [which source from the synthesis]
**IMPACT:** [High/Medium/Low - how much this weakens the conclusion]
**REASONING:** [why this is a genuine contradiction, not just a caveat]

(Repeat for each contradiction found)

**OVERALL ASSESSMENT:**
- Number of contradictions found: [count]
- Net impact on confidence: [None/Minor/Moderate/Significant]
- Recommendation: [Proceed with caution / Investigate further / Conclusion still valid]

If no genuine contradictions found, output:

## CONTRADICTING EVIDENCE

No significant contradicting evidence identified in the synthesis.

**OVERALL ASSESSMENT:**
- Number of contradictions found: 0
- Net impact on confidence: None
- Recommendation: Conclusion supported by available evidence"""


# Re-synthesis prompt: integrates gap-filling results into existing synthesis
RESYNTHESIS_PROMPT = """You are updating a research synthesis with newly discovered information from web sources and gap-filling.

Query: {query}

## ORIGINAL SYNTHESIS
{original_synthesis}

## NEW INFORMATION (from web chain extraction and gap filling)

### Web-Sourced Logic Chains
{web_chains_text}

### Gap Enrichment
{gap_enrichment}

## Instructions

Produce an UPDATED synthesis that integrates the new information with the original.

Rules:
1. **Preserve** all valid conclusions from the original synthesis
2. **Integrate** new logic chains and data points from web sources
3. **Update confidence** if new evidence strengthens or weakens conclusions
4. **Add new conclusions** if web chains reveal patterns not in the original
5. **Flag contradictions** if new information contradicts original conclusions
6. **Weight appropriately**: Database-sourced chains (weight 1.0) are more authoritative than web-sourced chains (weight 0.7)
7. Keep the same output format as the original synthesis (consensus conclusions + key variables)
8. **Check chain completeness**: For each causal conclusion, verify the full chain is articulated (A → B → C, not just A → C). Common missing intermediate steps: real rates (nominal minus inflation), yield curve dynamics (term premium, bear steepening vs flattening), trade balance effects, fiscal deficit implications. If data for intermediate steps exists in the new information, spell out the full chain.
9. **Consider regime-shift interpretations**: If the data supports a clear directional conclusion, also check whether any web-sourced chains suggest a structural change or regime shift that could alter the trajectory. If credible opposing views from named institutions exist in the new information, present them as a competing scenario alongside the main conclusion. Do NOT force a contrarian view if no evidence supports one.

Output the updated synthesis directly. Do not include meta-commentary about what changed."""


# Structured synthesis prompt (used with tool_use for guaranteed JSON output)
SYNTHESIS_STRUCTURED_PROMPT = """You are synthesizing logic chains to identify consensus patterns and key monitoring variables.

Query: {query}

Logic Chains:
{chains}

Instructions:

## Part 1: Consensus Chains
Identify where MULTIPLE chains converge on the same conclusion through different paths.
- Look for different starting points that lead to the same end effect
- These represent higher-conviction conclusions supported by multiple reasoning paths
- Only include if 2+ chains support the same conclusion

## Part 2: Key Variables to Monitor
Extract specific, actionable variables/indicators mentioned across the chains.
- Group by category (e.g., Liquidity, Labor Market, Positioning)
- Include specific thresholds or levels if mentioned
- Note which chains reference each variable

## Confidence Scoring
Score the overall confidence based on:
- High (0.8+): 3+ paths from 2+ independent sources
- Medium (0.5-0.8): 2 paths OR single source with strong logic
- Low (<0.5): Single path, weak support, or contradictory evidence

Use the submit_synthesis tool to submit your analysis with confidence metadata."""
