"""Prompts for impact analysis."""

from .asset_configs import get_asset_config

# Legacy belief space system prompt
BELIEF_SPACE_SYSTEM_PROMPT = """You are a quantitative macro analyst mapping the BELIEF SPACE around market events.

Your task is NOT to predict outcomes, but to map what the market WAS or IS pricing — including contradictory beliefs.

## CORE PRINCIPLE: BELIEF SPACE MAPPING

Markets often price MULTIPLE contradictory scenarios simultaneously. Your job is to:
1. Surface ALL plausible causal chains (even if they lead to opposite outcomes)
2. PRESERVE contradictions as first-class objects (do NOT resolve them)
3. Quantify likelihood based on positioning and data, not your opinion
4. Explain WHY contradictions can coexist (different actors, time horizons, assumptions)

## EXAMPLE OF BELIEF SPACE OUTPUT

Good output for "AI CAPEX impact on tech stocks":
```
SCENARIO A: Value Destruction (BEARISH, 55%)
Chain: CAPEX doubles → ROI dilution fears → multiple compression → stocks down

SCENARIO B: AI Leadership Confirmation (BULLISH, 35%)
Chain: CAPEX doubles → AI conviction signal → growth premium → stocks up

CONTRADICTION: Market pricing BOTH simultaneously
- Thesis A: "CAPEX implies value destruction"
- Thesis B: "CAPEX confirms AI leadership"
- Implication: Valuation swings of $57B based purely on ROI assumptions
```

## KNOWLEDGE GAPS
You will receive pre-assessed gaps. Where information is missing:
- Acknowledge the limitation
- Widen your scenario range
- Do NOT claim precision in gap areas

## VARIABLE ACKNOWLEDGMENT
You will receive current market data. Acknowledge ALL variables:
- USED: [variable]: [value] - [how it informed likelihood]
- NOT_USED: [variable]: [value] - [why not relevant]

Be specific, quantitative, and preserve complexity. Reference actual data points."""

# Keep SYSTEM_PROMPT as alias for backward compatibility
SYSTEM_PROMPT = BELIEF_SPACE_SYSTEM_PROMPT

INSIGHT_SYSTEM_PROMPT = """You are a macro research analyst producing INSIGHT REPORTS with independent reasoning TRACKS.

## CORE PRINCIPLE: MULTI-TRACK CAUSAL REASONING

An insight is NOT a trade signal (BULLISH/BEARISH). An insight is a multi-track causal understanding grounded in historical evidence.

CRITICAL DISTINCTION:
- SCENARIOS = different outcomes for the SAME mechanism (BAD: "bullish 60% vs bearish 40%")
- TRACKS = INDEPENDENT reasoning paths, each with its OWN evidence chain (GOOD)

Each track represents a separate causal pathway operating independently. Tracks can reinforce or oppose each other, but they are logically independent.

## TRACK STRUCTURE

Each track MUST contain:
1. **Causal mechanism**: Arrow notation showing the full causal chain (e.g., election → fiscal_expansion → bond_issuance → yen_weakness)
2. **Historical evidence**: How many prior instances followed this pattern (e.g., "4/5 prior fiscal expansions led to currency depreciation")
3. **Asset implications**: Specific directional view per asset with magnitude range and timing
4. **Monitoring variables**: What to watch to confirm/invalidate this track
5. **Confidence**: Based on evidence quality, not opinion

## EXAMPLE OUTPUT

```
Track 1: Historical Contagion Pattern
  Mechanism: contagion → risk_off → forced_liquidation → crypto_selloff
  Evidence: 4/5 prior contagion events bearish for risk assets, median -31%
  Asset Implications: BTC bearish (-20% to -45%, 1-3 months)
  Monitor: VIX > 40 confirms stress escalation

Track 2: Monetary Policy Response
  Mechanism: contagion → central_bank_easing → money_supply_expansion → asset_inflation
  Evidence: 3/4 prior crises led to easing within 60 days
  Asset Implications: BTC bullish (+30% to +100%, 6-12 months)
  Monitor: Fed emergency meeting, rate cut signals

Track 3: Flight to Digital Gold
  Mechanism: contagion → banking_stress → sovereign_risk → crypto_as_hedge
  Evidence: 2/3 banking crises saw crypto rally after initial selloff
  Asset Implications: BTC bullish after initial drop (+50%, 3-6 months)
  Monitor: Bank CDS spreads, stablecoin inflows
```

## KNOWLEDGE GAPS AND DATA
You will receive current market data, historical chain graphs, and precedent analysis. Use ALL of it.
Where information is missing, widen your confidence intervals and note the gap.

Be specific, quantitative, and ground every track in historical evidence."""


def format_theme_states_for_prompt(theme_states: dict) -> str:
    """Format per-theme assessments as a MACRO REGIME section for the prompt."""
    if not theme_states:
        return ""

    lines = ["## MACRO REGIME (per-theme assessments)"]
    for theme_name, state in theme_states.items():
        assessment = state.get("assessment", "No assessment")
        active_count = len(state.get("active_chain_ids", []))
        lines.append(f"{theme_name.upper()}: {assessment} [{active_count} active chains]")

    return "\n".join(lines) + "\n"


def get_impact_analysis_prompt(
    query: str,
    retrieval_answer: str,
    synthesis: str,
    logic_chains: list,
    confidence_metadata: dict,
    current_values_text: str = "",
    historical_chains_text: str = "",
    validated_patterns_text: str = "",
    historical_event_text: str = "",
    knowledge_gaps: dict = None,
    gap_enrichment_text: str = "",
    asset_class: str = "btc",
    theme_states: dict = None,
    chain_graph_text: str = "",
    historical_analogs_text: str = "",
    claim_validation_text: str = ""
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
        paths = confidence_metadata.get("chain_count", "N/A")
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

    # Format knowledge gaps section (pre-assessed by separate LLM call)
    knowledge_gaps_section = ""
    if knowledge_gaps:
        coverage = knowledge_gaps.get("coverage_rating", "UNKNOWN")
        gap_count = knowledge_gaps.get("gap_count", 0)
        gaps = knowledge_gaps.get("gaps", [])

        gap_lines = [f"## PRE-ASSESSED KNOWLEDGE GAPS"]
        gap_lines.append(f"Coverage: {coverage} ({gap_count} gaps detected)")
        gap_lines.append("")

        for gap in gaps:
            status = gap.get("status", "UNKNOWN")
            category = gap.get("category", "unknown").replace("_", " ").title()
            found = gap.get("found", "")
            missing = gap.get("missing", "")

            if status == "COVERED":
                gap_lines.append(f"- {category}: COVERED - {found}")
            else:
                gap_lines.append(f"- {category}: GAP - {found}")
                if missing:
                    gap_lines.append(f"  Missing: {missing}")

        knowledge_gaps_section = "\n".join(gap_lines) + "\n"

    # Format gap enrichment section (from web search)
    gap_enrichment_section = ""
    if gap_enrichment_text:
        gap_enrichment_section = f"""
## ADDITIONAL CONTEXT (from web search to fill gaps)
{gap_enrichment_text}
"""

    # Format macro regime section (from theme states)
    regime_section = ""
    if theme_states:
        regime_section = format_theme_states_for_prompt(theme_states) + "\n"

    # Format chain graph section
    chain_graph_section = ""
    if chain_graph_text:
        chain_graph_section = f"\n{chain_graph_text}\n"

    # Format historical analogs section
    historical_analogs_section = ""
    if historical_analogs_text:
        historical_analogs_section = f"\n{historical_analogs_text}\n"

    # Format claim validation section
    claim_validation_section = ""
    if claim_validation_text:
        claim_validation_section = f"\n{claim_validation_text}\n"

    return f"""## USER QUERY
{query}

## RETRIEVED ANALYSIS
{retrieval_answer}

## SYNTHESIS
{synthesis}

## LOGIC CHAINS
{chains_text}

## RETRIEVAL CONFIDENCE
{conf_text}
{current_values_section}{historical_chains_section}{validated_patterns_section}{historical_event_section}
{knowledge_gaps_section}{gap_enrichment_section}{regime_section}{chain_graph_section}{historical_analogs_section}{claim_validation_section}---

Based on the above context, current market data, pattern validation, and any historical event comparisons, {get_asset_config(asset_class)["prompt_asset_line"]}
Pay special attention to TRIGGERED patterns - these indicate that conditions from research are currently active.

**IMPORTANT**: Knowledge gaps have been pre-assessed above. Where gaps exist:
- Acknowledge the limitation in your analysis
- Be appropriately uncertain (lower confidence, wider scenario range)
- Do NOT claim precision in areas flagged as gaps

Respond in EXACTLY this format:

VARIABLES_ANALYSIS:
- USED: [variable]: [value] - [how it informed scenario likelihoods]
- NOT_USED: [variable]: [value] - [why not relevant]
[List ALL variables from CURRENT MARKET DATA]

SCENARIOS:
- Scenario A: [descriptive name]
  - Chain: [cause → interpretation → mechanism → outcome]
  - Direction: [BULLISH/BEARISH/NEUTRAL]
  - Likelihood: [X%] based on [specific data point]
  - Key Data: [list 2-3 data points supporting this scenario]
  - Actors: [who is positioned for this scenario, if known]

- Scenario B: [descriptive name]
  - Chain: [cause → interpretation → mechanism → outcome]
  - Direction: [BULLISH/BEARISH/NEUTRAL]
  - Likelihood: [Y%] based on [specific data point]
  - Key Data: [list 2-3 data points supporting this scenario]
  - Actors: [who is positioned for this scenario, if known]

[Add Scenario C, D if distinct paths exist. Surface ALL plausible narratives, even if opposing.]

CONTRADICTIONS:
[If scenarios lead to opposite outcomes, explicitly document the contradiction]
- [Thesis A] vs [Thesis B]
  - Source A: [who holds this view]
  - Source B: [who holds this view]
  - Implication: [why both can coexist - different time horizons, actors, assumptions]
  - Volatility Impact: [how this uncertainty affects price action]

[If no contradictions exist, write "None - scenarios are complementary"]

PRIMARY_DIRECTION: [BULLISH/BEARISH/NEUTRAL - direction of highest likelihood scenario]

CONFIDENCE:
- score: [0.0-1.0 - LOWER if contradictions exist]
- chain_count: [number of supporting logic chains]
- source_diversity: [number of unique sources]
- strongest_chain: [summary of strongest causal path]
- uncertainty_drivers: [list key unknowns that affect confidence]

TIME_HORIZON: [intraday/days/weeks/months/regime_shift]

DECAY_PROFILE: [fast/medium/slow]

RATIONALE:
[2-4 sentences explaining the BELIEF SPACE - what the market is pricing, why contradictions exist, what would resolve uncertainty]

RISK_FACTORS:
- [Risk 1: what would invalidate the primary scenario]
- [Risk 2: what would shift likelihood toward alternative scenario]
- [Risk 3: external catalyst that could resolve contradictions]"""


def _format_data_sections(
    query: str,
    retrieval_answer: str,
    synthesis: str,
    logic_chains: list,
    confidence_metadata: dict,
    current_values_text: str = "",
    historical_chains_text: str = "",
    validated_patterns_text: str = "",
    historical_event_text: str = "",
    knowledge_gaps: dict = None,
    gap_enrichment_text: str = "",
    theme_states: dict = None,
    chain_graph_text: str = "",
    historical_analogs_text: str = "",
    claim_validation_text: str = ""
) -> str:
    """Build the data sections shared between belief_space and insight prompts."""

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
        paths = confidence_metadata.get("chain_count", "N/A")
        sources = confidence_metadata.get("source_diversity", "N/A")
        conf_text = f"Score: {score}, Paths: {paths}, Sources: {sources}"
    else:
        conf_text = "(No confidence metadata)"

    # Format optional sections
    sections = []

    if current_values_text:
        sections.append(f"\n## CURRENT MARKET DATA\n{current_values_text}")

    if historical_chains_text and historical_chains_text != "(No relevant historical chains)":
        sections.append(f"\n## HISTORICAL LOGIC CHAINS (Previously Discovered)\n{historical_chains_text}")

    if validated_patterns_text:
        sections.append(f"\n{validated_patterns_text}")

    if historical_event_text:
        sections.append(f"\n{historical_event_text}")

    if knowledge_gaps:
        coverage = knowledge_gaps.get("coverage_rating", "UNKNOWN")
        gap_count = knowledge_gaps.get("gap_count", 0)
        gaps = knowledge_gaps.get("gaps", [])
        gap_lines = [f"## PRE-ASSESSED KNOWLEDGE GAPS"]
        gap_lines.append(f"Coverage: {coverage} ({gap_count} gaps detected)")
        gap_lines.append("")
        for gap in gaps:
            status = gap.get("status", "UNKNOWN")
            category = gap.get("category", "unknown").replace("_", " ").title()
            found = gap.get("found", "")
            missing = gap.get("missing", "")
            if status == "COVERED":
                gap_lines.append(f"- {category}: COVERED - {found}")
            else:
                gap_lines.append(f"- {category}: GAP - {found}")
                if missing:
                    gap_lines.append(f"  Missing: {missing}")
        sections.append("\n".join(gap_lines))

    if gap_enrichment_text:
        sections.append(f"\n## ADDITIONAL CONTEXT (from web search to fill gaps)\n{gap_enrichment_text}")

    if theme_states:
        sections.append(format_theme_states_for_prompt(theme_states))

    if chain_graph_text:
        sections.append(f"\n{chain_graph_text}")

    if historical_analogs_text:
        sections.append(f"\n{historical_analogs_text}")

    if claim_validation_text:
        sections.append(f"\n{claim_validation_text}")

    optional_text = "\n".join(sections)

    return f"""## USER QUERY
{query}

## RETRIEVED ANALYSIS
{retrieval_answer}

## SYNTHESIS
{synthesis}

## LOGIC CHAINS
{chains_text}

## RETRIEVAL CONFIDENCE
{conf_text}
{optional_text}
---"""


def get_insight_prompt(
    query: str,
    retrieval_answer: str,
    synthesis: str,
    logic_chains: list,
    confidence_metadata: dict,
    current_values_text: str = "",
    historical_chains_text: str = "",
    validated_patterns_text: str = "",
    historical_event_text: str = "",
    knowledge_gaps: dict = None,
    gap_enrichment_text: str = "",
    asset_class: str = "btc",
    theme_states: dict = None,
    chain_graph_text: str = "",
    historical_analogs_text: str = "",
    claim_validation_text: str = ""
) -> str:
    """Build the insight analysis prompt (track-based output)."""

    data_sections = _format_data_sections(
        query=query,
        retrieval_answer=retrieval_answer,
        synthesis=synthesis,
        logic_chains=logic_chains,
        confidence_metadata=confidence_metadata,
        current_values_text=current_values_text,
        historical_chains_text=historical_chains_text,
        validated_patterns_text=validated_patterns_text,
        historical_event_text=historical_event_text,
        knowledge_gaps=knowledge_gaps,
        gap_enrichment_text=gap_enrichment_text,
        theme_states=theme_states,
        chain_graph_text=chain_graph_text,
        historical_analogs_text=historical_analogs_text,
        claim_validation_text=claim_validation_text
    )

    return f"""{data_sections}

Based on the above context, produce an INSIGHT REPORT for {get_asset_config(asset_class)["prompt_asset_line"]}

Build INDEPENDENT reasoning tracks. Each track must have:
- A distinct causal mechanism (arrow notation)
- Historical evidence grounding (N/M precedents, success rate)
- Specific asset implications with magnitude ranges and timing
- Monitoring variables with trigger conditions

Use the MULTI-HOP CAUSAL PATHS section (if present) to identify independent causal tracks.
Use the HISTORICAL PRECEDENT ANALYSIS section (if present) to ground evidence in each track.

Do NOT produce belief-space scenarios (BULLISH 60% vs BEARISH 40%).
Instead, produce independent tracks that each stand on their own evidence.

Pay special attention to TRIGGERED patterns and historical analogs — these provide the strongest evidence basis."""
