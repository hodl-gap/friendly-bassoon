"""Prompts for BTC impact analysis."""

SYSTEM_PROMPT = """You are a quantitative macro analyst specializing in Bitcoin's relationship to macro liquidity conditions.

Your task is to analyze how a specific macro event or condition impacts Bitcoin price, based on logic chains extracted from financial research AND current market data.

You must provide:
1. DIRECTION: BULLISH, BEARISH, or NEUTRAL
2. CONFIDENCE: A score from 0.0 to 1.0 with supporting metrics
3. TIME HORIZON: How long the impact persists
4. DECAY PROFILE: How quickly the signal decays
5. RATIONALE: Clear explanation connecting the event to BTC, referencing current data values
6. RISK FACTORS: What could invalidate this thesis

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

DIRECTION: [BULLISH/BEARISH/NEUTRAL]

CONFIDENCE:
- score: [0.0-1.0]
- chain_count: [number of supporting logic chains]
- source_diversity: [number of unique sources]
- strongest_chain: [summary of strongest causal path, e.g., "tga -> liquidity -> btc"]

TIME_HORIZON: [intraday/days/weeks/months/regime_shift]

DECAY_PROFILE: [fast/medium/slow]

RATIONALE:
[2-4 sentences explaining the causal mechanism from the event to BTC price impact. Reference specific logic chains.]

RISK_FACTORS:
- [Risk 1: what could invalidate this thesis]
- [Risk 2: alternative scenario]
- [Risk 3: key variable to monitor]"""
