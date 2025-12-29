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
2. Connect chains where one chain's effect matches another's cause to form longer sequences
3. Prioritize longer chains (3+ steps) over shorter ones - they capture more complete mechanisms
4. Group chains by theme/category (e.g., "Direct Effects", "Conditional Chains", "Risk/Reversal Chains")
5. Use the interpretation/what_happened context to supplement chain understanding
6. Output as structured list only - no narrative summary

Output Format:
## [Group Name]

**CHAIN:** cause → effect → [next effect if connected]
**MECHANISM:** mechanism for each step
**SOURCE:** which source(s) support this chain

Example:
## Direct Monetary Effects

**CHAIN:** Fed rate cuts → real rates down → discount rates fall → risk asset valuations up
**MECHANISM:** rate cuts reduce nominal yields → lower real yields increase present value of future cash flows → equity multiples expand
**SOURCE:** Goldman Sachs, UBS"""


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

Output Format:

## CONSENSUS CONCLUSIONS

**CONCLUSION:** [the common end point]
**SUPPORTING PATHS:**
- Path 1: A → B → [conclusion]
- Path 2: C → D → [conclusion]
**CONFIDENCE:** [High/Medium based on number of supporting paths]

## KEY VARIABLES TO MONITOR

**[Category Name]:**
- Variable 1 - threshold/level if known [referenced in: chain groups]
- Variable 2 - threshold/level if known [referenced in: chain groups]"""
