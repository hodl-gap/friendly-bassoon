"""Prompts for BTC impact analysis."""

SYSTEM_PROMPT = """You are a quantitative macro analyst specializing in Bitcoin's relationship to macro liquidity conditions.

Your task is to analyze how a specific macro event or condition impacts Bitcoin price, based on logic chains extracted from financial research AND current market data.

## COMPLETENESS CHECK
Before providing your analysis, assess whether the retrieved information is SUFFICIENT:
- Are there aspects of this event that you CANNOT analyze due to missing information?
- What additional data or context would strengthen this analysis?
- Rate coverage: COMPLETE / PARTIAL / INSUFFICIENT

If PARTIAL or INSUFFICIENT, explicitly state what's missing.

## VARIABLE ACKNOWLEDGMENT
You will receive current market data for multiple variables. You MUST acknowledge ALL fetched variables:
- For variables you USE: explain how they informed your analysis
- For variables you DON'T USE: explain why they are not relevant to this specific event

## DIVERGING SCENARIOS
When multiple plausible outcomes exist, you MUST present them as separate scenarios with:
- The causal chain for each scenario
- A likelihood percentage based on specific data points from the fetched variables
- A clear direction (BULLISH/BEARISH/NEUTRAL) for each

The PRIMARY_DIRECTION should be the direction of the most likely scenario.

Be specific and quantitative where possible. Reference the logic chains and current values provided."""


def get_impact_analysis_prompt(
    query: str,
    retrieval_answer: str,
    retrieval_synthesis: str,
    logic_chains: list,
    confidence_metadata: dict,
    current_values_text: str = "",
    historical_chains_text: str = "",
    validated_patterns_text: str = "",
    historical_event_text: str = ""
) -> str:
    """Build the impact analysis prompt."""

    # Format logic chains for display
    chains_text = ""
    if logic_chains:
        for i, chain in enumerate(logic_chains, 1):
            chains_text += f"\n### Chain {i}\n"
            if isinstance(chain, dict):
                steps = chain.get("steps", [])
                for step in steps:
                    cause = step.get("cause", "?")
                    effect = step.get("effect", "?")
                    mechanism = step.get("mechanism", "")
                    chains_text += f"  - {cause} → {effect}"
                    if mechanism:
                        chains_text += f" ({mechanism})"
                    chains_text += "\n"
    else:
        chains_text = "(No explicit logic chains extracted)"

    # Format confidence metadata
    conf_text = ""
    if confidence_metadata:
        score = confidence_metadata.get("overall_score", "N/A")
        paths = confidence_metadata.get("path_count", "N/A")
        sources = confidence_metadata.get("source_diversity", "N/A")
        conf_text = f"Score: {score}, Paths: {paths}, Sources: {sources}"
    else:
        conf_text = "(No confidence metadata)"

    # Format current values section
    current_values_section = ""
    if current_values_text:
        current_values_section = f"""
## CURRENT MARKET DATA
{current_values_text}
"""

    # Format historical chains section
    historical_chains_section = ""
    if historical_chains_text and historical_chains_text != "(No relevant historical chains)":
        historical_chains_section = f"""
## HISTORICAL LOGIC CHAINS (Previously Discovered)
{historical_chains_text}
"""

    # Format validated patterns section
    validated_patterns_section = ""
    if validated_patterns_text:
        validated_patterns_section = f"""
{validated_patterns_text}
"""

    # Format historical event section
    historical_event_section = ""
    if historical_event_text:
        historical_event_section = f"""
{historical_event_text}
"""

    return f"""## USER QUERY
{query}

## RETRIEVED ANALYSIS
{retrieval_answer}

## SYNTHESIS
{retrieval_synthesis}

## LOGIC CHAINS
{chains_text}

## RETRIEVAL CONFIDENCE
{conf_text}
{current_values_section}{historical_chains_section}{validated_patterns_section}{historical_event_section}
---

Based on the above context, current market data, pattern validation, and any historical event comparisons, analyze the impact on Bitcoin.
Pay special attention to TRIGGERED patterns - these indicate that conditions from research are currently active.

Respond in EXACTLY this format:

COVERAGE: [COMPLETE/PARTIAL/INSUFFICIENT]

UNCOVERED_ASPECTS: [what information is missing that would strengthen this analysis, or "None" if COMPLETE]

VARIABLES_ANALYSIS:
- USED: [variable]: [value] - [how it informed the analysis]
- USED: [variable]: [value] - [how it informed the analysis]
- NOT_USED: [variable]: [value] - [why not relevant to this event]
[List ALL variables from CURRENT MARKET DATA section - every variable must be acknowledged as either USED or NOT_USED]

SCENARIOS:
- Scenario A: [descriptive name]
  - Chain: [cause → effect → outcome]
  - Direction: [BULLISH/BEARISH/NEUTRAL]
  - Likelihood: [X%] based on [specific data point from fetched variables]

- Scenario B: [descriptive name]
  - Chain: [cause → effect → outcome]
  - Direction: [BULLISH/BEARISH/NEUTRAL]
  - Likelihood: [Y%] based on [specific data point from fetched variables]

[Add Scenario C if a third distinct path exists. At minimum, provide 2 scenarios when diverging outcomes are plausible.]

PRIMARY_DIRECTION: [BULLISH/BEARISH/NEUTRAL - must match the direction of the highest likelihood scenario]

CONFIDENCE:
- score: [0.0-1.0]
- chain_count: [number of supporting logic chains]
- source_diversity: [number of unique sources]
- strongest_chain: [summary of strongest causal path, e.g., "tga -> liquidity -> btc"]

TIME_HORIZON: [intraday/days/weeks/months/regime_shift]

DECAY_PROFILE: [fast/medium/slow]

RATIONALE:
[2-4 sentences connecting event to BTC, referencing the scenarios and specific data values from fetched variables]

RISK_FACTORS:
- [Risk 1: what could invalidate the primary scenario]
- [Risk 2: key variable to monitor that could shift scenario likelihoods]
- [Risk 3: external factor not captured in current data]"""
