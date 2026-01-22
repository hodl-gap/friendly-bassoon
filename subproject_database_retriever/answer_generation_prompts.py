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

Example:
## Direct Monetary Effects

**CHAIN:** Fed rate cuts [rate_cut] → real rates down [real_rates] → risk asset valuations up [risk_asset_valuation]
**MECHANISM:** rate cuts reduce nominal yields → lower real yields increase present value of future cash flows
**SOURCE:** Goldman Sachs (step 1), UBS (step 2)
**CONNECTION:** Connected via [real_rates] from Goldman Sachs to UBS"""


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

Note: For variables with specific values, indicate these are from historical data context and would need updating for current application."""


# Stage 3: Identify contradicting evidence (Issue 5: Negative Evidence Handling)
CONTRADICTION_PROMPT = """You are analyzing financial research to identify contradicting or weakening evidence.

Query: {query}

Consensus Synthesis:
{synthesis}

Original Research Context:
{context}

Instructions:
1. Identify any evidence that CONTRADICTS or WEAKENS the consensus conclusions
2. Look for:
   - Sources that explicitly disagree with the consensus
   - Conditions where the logic chain breaks down
   - Historical examples where similar logic failed
   - Missing considerations that could invalidate conclusions
   - Alternative interpretations of the same data
3. Be conservative - only flag genuine contradictions, not minor nuances or caveats

Output Format:

## CONTRADICTING EVIDENCE

**CONTRADICTION:** [what contradicts the consensus]
**SOURCE:** [which source/context]
**IMPACT:** [High/Medium/Low - how much this weakens the conclusion]
**REASONING:** [why this is a genuine contradiction, not just a caveat]

(Repeat for each contradiction found)

**OVERALL ASSESSMENT:**
- Number of contradictions found: [count]
- Net impact on confidence: [None/Minor/Moderate/Significant]
- Recommendation: [Proceed with caution / Investigate further / Conclusion still valid]

If no genuine contradictions found, output:

## CONTRADICTING EVIDENCE

No significant contradicting evidence identified in the retrieved context.

**OVERALL ASSESSMENT:**
- Number of contradictions found: 0
- Net impact on confidence: None
- Recommendation: Conclusion supported by available evidence"""
