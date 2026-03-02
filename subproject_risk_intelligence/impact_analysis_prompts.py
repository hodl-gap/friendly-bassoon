"""Prompts for impact analysis."""

from .asset_configs import get_asset_config

REGIME_CHARACTERIZATION_PROMPT = """Given current market conditions and historical analog data, characterize the current macro regime and compare it to historical precedents.

CURRENT MARKET DATA:
{current_values_text}

HISTORICAL ANALOGS:
{historical_analogs_text}

Produce a concise regime characterization that:
1. Names the current regime (e.g., "late-cycle tightening", "early easing", "liquidity injection")
2. Lists 2-3 key similarities to the closest historical analog
3. Lists 2-3 key differences ("this time is different because...")
4. States which analog is most relevant and why
"""

SYSTEM_PROMPT = """You are a macro research analyst producing INSIGHT REPORTS with independent reasoning TRACKS.

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

## TEMPORAL SEQUENCING (when applicable)

If tracks have a temporal dependency (one creates conditions for another), assign sequence_position:
- sequence_position=1: happens first (near-term catalyst)
- sequence_position=2: follows from Track 1's outcome (medium-term)
- sequence_position=3: long-term structural consequence

Example: "Carry unwind selloff (1-3mo)" → "Central bank easing response (3-6mo)" → "Liquidity-driven recovery (6-12mo)"

Only use sequencing when tracks are genuinely sequential. Independent parallel tracks should omit sequence_position.

## KNOWLEDGE GAPS AND DATA
You will receive current market data, historical chain graphs, and precedent analysis. Use ALL of it.
Where information is missing, widen your confidence intervals and note the gap.

## SOURCING DISCIPLINE
- You may ONLY cite specific events, data points, or statistics that appear in the evidence sections above.
- For episode dates where no narrative context is provided, describe them by their regime conditions (e.g., "a low-vol, easy-policy period") — do NOT assign event labels from your own knowledge.
- If you believe additional data would strengthen the analysis (e.g., insider flow data, dark pool activity), note it as a "DATA GAP" in the key_uncertainties section rather than filling it in yourself.
- General labels for well-known dates (e.g., "COVID period" for March 2020) are acceptable ONLY when clearly marked as context, not as evidence.

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


def _format_data_sections(
    query: str,
    synthesis: str,
    logic_chains: list,
    confidence_metadata: dict,
    current_values_text: str = "",
    historical_chains_text: str = "",
    historical_event_text: str = "",
    knowledge_gaps: dict = None,
    gap_enrichment_text: str = "",
    theme_states: dict = None,
    chain_graph_text: str = "",
    historical_analogs_text: str = "",
    claim_validation_text: str = "",
    regime_characterization_text: str = ""
) -> str:
    """Build the data sections for the insight prompt."""

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

    if regime_characterization_text:
        sections.append(f"\n## REGIME CHARACTERIZATION (Then vs Now)\n{regime_characterization_text}")

    if chain_graph_text:
        sections.append(f"\n{chain_graph_text}")

    if historical_analogs_text:
        sections.append(f"\n{historical_analogs_text}")

    if claim_validation_text:
        sections.append(f"\n{claim_validation_text}")

    optional_text = "\n".join(sections)

    # Build main sections — skip retrieval_answer (synthesis subsumes it)
    main_parts = [f"## USER QUERY\n{query}", f"\n## SYNTHESIS\n{synthesis}"]

    # Only include LOGIC CHAINS if there are actual chains
    if logic_chains:
        main_parts.append(f"\n## LOGIC CHAINS\n{chains_text}")

    main_parts.append(f"\n## RETRIEVAL CONFIDENCE\n{conf_text}")
    main_parts.append(optional_text)
    main_parts.append("---")

    return "\n".join(main_parts)


def get_insight_prompt(
    query: str,
    synthesis: str,
    logic_chains: list,
    confidence_metadata: dict,
    current_values_text: str = "",
    historical_chains_text: str = "",
    historical_event_text: str = "",
    knowledge_gaps: dict = None,
    gap_enrichment_text: str = "",
    asset_class: str = "btc",
    theme_states: dict = None,
    chain_graph_text: str = "",
    historical_analogs_text: str = "",
    claim_validation_text: str = "",
    regime_characterization_text: str = ""
) -> str:
    """Build the insight analysis prompt (track-based output)."""

    data_sections = _format_data_sections(
        query=query,
        synthesis=synthesis,
        logic_chains=logic_chains,
        confidence_metadata=confidence_metadata,
        current_values_text=current_values_text,
        historical_chains_text=historical_chains_text,
        historical_event_text=historical_event_text,
        knowledge_gaps=knowledge_gaps,
        gap_enrichment_text=gap_enrichment_text,
        theme_states=theme_states,
        chain_graph_text=chain_graph_text,
        historical_analogs_text=historical_analogs_text,
        claim_validation_text=claim_validation_text,
        regime_characterization_text=regime_characterization_text
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

Pay special attention to TRIGGERED patterns and historical analogs — these provide the strongest evidence basis.

TEMPORAL DISCIPLINE: Separate causal tracks from forward projections.
- **Causal tracks**: Only include events/mechanisms that occurred BEFORE or CONCURRENT with the queried event. These explain what caused it.
- **Outlook section**: Forward projections, seasonal patterns, and predictions about what happens NEXT belong in the synthesis/outlook, NOT as causal tracks. A forecast made after the event is not a cause of the event.
- If a piece of evidence is dated, use its date to determine whether it is a cause or a projection relative to the event in the query.

IMPORTANT: In your synthesis, include ALL specific quantitative data from the retrieved context — dollar amounts ($XB lost), valuation multiples (P/S, P/E compression ratios), index drawdowns (% from peak), and named institutional sources. These concrete numbers are critical for trader decision-making."""
