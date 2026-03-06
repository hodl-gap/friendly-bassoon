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

SYSTEM_PROMPT_RETROSPECTIVE = """You are a macro research analyst producing CAUSAL DECOMPOSITIONS that explain what happened and why.

## CORE TASK
Explain the event's causes through independent causal tracks. Each track is a separate pathway that contributed to the event.

## RULES
- Max 4 tracks. If you have more, merge the weaker ones.
- Each track MUST have quantitative data from the evidence (specific numbers, dollar amounts, percentages).
- Arrow notation for mechanisms: A → B → C
- Do NOT make forward predictions in causal tracks. Put those in residual_forward_view.
- Confidence is based on evidence quality (how many data points support this track), not opinion.

## SOURCING DISCIPLINE
- ONLY cite events, data points, statistics that appear in the evidence sections.
- For episode dates without narrative context, describe by regime conditions — do NOT assign event labels.
- Note data gaps in key_data_gaps rather than inventing data.
- General labels for well-known dates (e.g., "COVID period" for March 2020) are acceptable as context, not evidence.

## LENGTH
Keep it concise. The maxLength constraints on each field are hard limits — stay well within them."""


SYSTEM_PROMPT_PROSPECTIVE = """You are a macro research analyst producing SCENARIO ANALYSES grounded in historical data.

## CORE TASK
Fill in a scenario analysis skeleton with causal mechanisms and human-readable names. The scenario STRUCTURE (how many scenarios, which analogs support each) is pre-computed from historical data.

## RULES
- Do NOT change the number of scenarios from the skeleton.
- Name each scenario descriptively (e.g., "Risk-On Continuation" not "Scenario 1").
- Write the condition (what must be true), mechanism (arrow notation), and analog basis.
- Write a falsification criterion for each scenario (what would prove it wrong).
- Keep predictions grounded in the forward return data from the scenario skeleton.
- Do NOT assign probabilities — the analog counts ARE the probability signal.
- Each prediction needs: variable, direction (bullish/bearish/neutral), and timeframe_days.
- magnitude_low and magnitude_high should come from the skeleton's forward return data.

## SOURCING DISCIPLINE
- ONLY cite events, data points, statistics that appear in the evidence sections.
- For episode dates without narrative context, describe by regime conditions — do NOT assign event labels.
- Note any gaps explicitly rather than inventing data.

## LENGTH
Keep it concise. The maxLength constraints on each field are hard limits — stay well within them."""


# Keep legacy prompt for reference — only used if somehow called directly
SYSTEM_PROMPT = SYSTEM_PROMPT_PROSPECTIVE


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


def get_retrospective_prompt(
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
    regime_characterization_text: str = "",
) -> str:
    """Build the retrospective causal decomposition prompt."""

    data_sections = _format_data_sections(
        query=query, synthesis=synthesis, logic_chains=logic_chains,
        confidence_metadata=confidence_metadata, current_values_text=current_values_text,
        historical_chains_text=historical_chains_text, historical_event_text=historical_event_text,
        knowledge_gaps=knowledge_gaps, gap_enrichment_text=gap_enrichment_text,
        theme_states=theme_states, chain_graph_text=chain_graph_text,
        historical_analogs_text=historical_analogs_text, claim_validation_text=claim_validation_text,
        regime_characterization_text=regime_characterization_text,
    )

    return f"""{data_sections}

Produce a CAUSAL DECOMPOSITION for {get_asset_config(asset_class)["prompt_asset_line"]}.

Explain what happened and why through independent causal tracks:
- Each track is a separate causal pathway (arrow notation: A → B → C)
- Include specific quantitative data from the evidence (dollar amounts, percentages, dates)
- Max 4 tracks — merge weaker ones if needed
- Put forward-looking views ONLY in residual_forward_view, NOT in causal tracks

Use the MULTI-HOP CAUSAL PATHS and HISTORICAL PRECEDENT sections to identify tracks."""


def get_prospective_prompt(
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
    regime_characterization_text: str = "",
    scenario_skeleton: dict = None,
) -> str:
    """Build the prospective scenario analysis prompt."""
    from .scenario_builder import format_skeleton_for_prompt

    data_sections = _format_data_sections(
        query=query, synthesis=synthesis, logic_chains=logic_chains,
        confidence_metadata=confidence_metadata, current_values_text=current_values_text,
        historical_chains_text=historical_chains_text, historical_event_text=historical_event_text,
        knowledge_gaps=knowledge_gaps, gap_enrichment_text=gap_enrichment_text,
        theme_states=theme_states, chain_graph_text=chain_graph_text,
        historical_analogs_text=historical_analogs_text, claim_validation_text=claim_validation_text,
        regime_characterization_text=regime_characterization_text,
    )

    skeleton_text = format_skeleton_for_prompt(scenario_skeleton or {})

    return f"""{data_sections}

{skeleton_text}

Produce a SCENARIO ANALYSIS for {get_asset_config(asset_class)["prompt_asset_line"]}.

Fill in the scenario skeleton above with:
- A descriptive title for each scenario (not "Scenario 1")
- The condition (what must be true)
- The causal mechanism (arrow notation)
- Which historical analogs support it (reference dates/clusters from skeleton)
- Predictions: variable, direction, magnitude range (from skeleton forward return data), timeframe
- A falsification criterion (what would prove this wrong)

Also provide a monitoring dashboard (key variables with thresholds) and synthesis (3-4 sentences).

Do NOT assign probabilities — the analog count/total IS the probability signal.
Ground magnitude estimates in the skeleton's forward return data."""


# Keep legacy alias for any remaining callers
def get_insight_prompt(**kwargs) -> str:
    """Legacy alias — routes to prospective prompt."""
    return get_prospective_prompt(**kwargs)
