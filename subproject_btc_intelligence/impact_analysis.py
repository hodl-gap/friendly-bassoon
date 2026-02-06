"""Impact analysis module - LLM-based BTC impact assessment."""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List

# Add parent to path for models import
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_sonnet

from .impact_analysis_prompts import SYSTEM_PROMPT, get_impact_analysis_prompt
from .current_data_fetcher import format_current_values_for_prompt
from .relationship_store import get_relevant_historical_chains, format_historical_chains_for_prompt
from .pattern_validator import format_validated_patterns_for_prompt
from .historical_data_fetcher import format_historical_data_for_prompt
from .states import BTCImpactState


def analyze_impact(state: BTCImpactState) -> BTCImpactState:
    """
    Analyze the impact of a macro event on BTC using retrieved context.

    Input state requires:
        - query
        - retrieval_answer
        - retrieval_synthesis
        - logic_chains
        - confidence_metadata
        - current_values (optional, from Phase 2)
        - historical_chains (optional, from Phase 3)

    Updates state with:
        - direction
        - confidence
        - time_horizon
        - decay_profile
        - rationale
        - risk_factors
    """
    # Format current values if available
    current_values = state.get("current_values", {})
    current_values_text = format_current_values_for_prompt(current_values) if current_values else ""

    # Get relevant historical chains (Phase 3)
    historical_chains = state.get("historical_chains", [])
    query = state.get("query", "")
    relevant_chains = get_relevant_historical_chains(query, historical_chains, limit=5)
    historical_chains_text = format_historical_chains_for_prompt(relevant_chains)

    # Format validated patterns (Phase 2 - Pattern Validation)
    validated_patterns = state.get("validated_patterns", [])
    validated_patterns_text = format_validated_patterns_for_prompt(validated_patterns)

    # Format historical event data (Phase 4)
    historical_event_data = state.get("historical_event_data", {})
    historical_event_text = format_historical_data_for_prompt(historical_event_data)

    # Get pre-assessed knowledge gaps (Phase 5 - separate LLM call)
    knowledge_gaps = state.get("knowledge_gaps", {})
    gap_enrichment_text = state.get("gap_enrichment_text", "")

    # Build prompt
    prompt = get_impact_analysis_prompt(
        query=query,
        retrieval_answer=state.get("retrieval_answer", ""),
        retrieval_synthesis=state.get("retrieval_synthesis", ""),
        logic_chains=state.get("logic_chains", []),
        confidence_metadata=state.get("confidence_metadata", {}),
        current_values_text=current_values_text,
        historical_chains_text=historical_chains_text,
        validated_patterns_text=validated_patterns_text,
        historical_event_text=historical_event_text,
        knowledge_gaps=knowledge_gaps,
        gap_enrichment_text=gap_enrichment_text
    )

    # Call LLM
    messages = [
        {"role": "user", "content": prompt}
    ]

    print("\n[Impact Analysis] Calling Claude Sonnet...")
    response = call_claude_sonnet(messages, temperature=0.3, max_tokens=2000)

    print("\n[Impact Analysis] Raw LLM Response:")
    print("-" * 40)
    print(response)
    print("-" * 40)

    # Parse response
    parsed = parse_impact_response(response)

    # Update state - Belief Space (Multi-Scenario)
    state["scenarios"] = parsed.get("scenarios", [])
    state["belief_space"] = parsed.get("belief_space", {})

    # Primary direction (for backward compatibility)
    state["direction"] = parsed.get("direction", "NEUTRAL")
    state["confidence"] = parsed.get("confidence", {})
    state["time_horizon"] = parsed.get("time_horizon", "unknown")
    state["decay_profile"] = parsed.get("decay_profile", "unknown")
    state["rationale"] = parsed.get("rationale", "")
    state["risk_factors"] = parsed.get("risk_factors", [])

    return state


def parse_scenarios(response: str) -> List[Dict[str, Any]]:
    """Parse all scenarios from the SCENARIOS section of the LLM response."""
    scenarios = []

    # Find the SCENARIOS section
    scenarios_match = re.search(
        r"SCENARIOS:\s*\n(.+?)(?=\nPRIMARY_DIRECTION:|\nCONTRADICTIONS:|\nDIRECTION:|\Z)",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if not scenarios_match:
        return scenarios

    scenarios_text = scenarios_match.group(1)

    # Split by "- Scenario" to get each scenario block
    scenario_blocks = re.split(r"\n-\s*Scenario\s*", scenarios_text)

    for block in scenario_blocks:
        if not block.strip():
            continue

        scenario = {}

        # Extract scenario name (first line or after letter like "A:")
        # Handle various formats: "A: Name", "A - Name", just "Name"
        first_line = block.strip().split('\n')[0].strip()
        # Remove leading "- Scenario" prefix if present (edge case from split)
        first_line = re.sub(r'^-?\s*Scenario\s*', '', first_line, flags=re.IGNORECASE)
        # Parse "A: Name" or "A - Name" or just "Name"
        name_match = re.match(r"([A-Z])[\s:.-]+(.+?)$", first_line.strip())
        if name_match:
            scenario["name"] = name_match.group(2).strip()
        else:
            scenario["name"] = first_line.strip()

        # Extract Chain
        chain_match = re.search(r"-\s*Chain:\s*(.+?)(?:\n|$)", block)
        if chain_match:
            scenario["chain"] = chain_match.group(1).strip()

        # Extract Direction
        dir_match = re.search(r"-\s*Direction:\s*(BULLISH|BEARISH|NEUTRAL)", block, re.IGNORECASE)
        if dir_match:
            scenario["direction"] = dir_match.group(1).upper()
            scenario["polarity"] = dir_match.group(1).upper()

        # Extract Likelihood
        likelihood_match = re.search(r"-\s*Likelihood:\s*(\d+)%?\s*(?:based on\s*)?(.+)?(?:\n|$)", block, re.IGNORECASE)
        if likelihood_match:
            scenario["likelihood"] = int(likelihood_match.group(1)) / 100.0
            if likelihood_match.group(2):
                scenario["likelihood_basis"] = likelihood_match.group(2).strip()

        # Extract Rationale if present
        rationale_match = re.search(r"-\s*Rationale:\s*(.+?)(?:\n-|\n\n|$)", block, re.DOTALL)
        if rationale_match:
            scenario["rationale"] = rationale_match.group(1).strip()

        if scenario.get("name") or scenario.get("chain"):
            scenarios.append(scenario)

    return scenarios


def parse_contradictions(response: str) -> List[Dict[str, Any]]:
    """Parse contradictions from the CONTRADICTIONS section."""
    contradictions = []

    # Find CONTRADICTIONS section
    contra_match = re.search(
        r"CONTRADICTIONS:\s*\n(.+?)(?=\nPRIMARY_DIRECTION:|\nCONFIDENCE:|\nTIME_HORIZON:|\Z)",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if not contra_match:
        return contradictions

    contra_text = contra_match.group(1)

    # Parse each contradiction block (marked by - or bullet)
    contra_blocks = re.findall(
        r"-\s*(.+?)(?=\n-|\n\n|$)",
        contra_text,
        re.DOTALL
    )

    for block in contra_blocks:
        contradiction = {}

        # Try to parse structured format: "Thesis A vs Thesis B"
        vs_match = re.search(r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\n|$)", block, re.IGNORECASE)
        if vs_match:
            contradiction["thesis_a"] = vs_match.group(1).strip()
            contradiction["thesis_b"] = vs_match.group(2).strip()
        else:
            contradiction["description"] = block.strip()

        # Extract implication if present
        impl_match = re.search(r"(?:Implication|Result|Means):\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
        if impl_match:
            contradiction["implication"] = impl_match.group(1).strip()

        if contradiction:
            contradictions.append(contradiction)

    return contradictions


def parse_impact_response(response: str) -> Dict[str, Any]:
    """Parse the structured LLM response into components."""
    result = {
        "direction": "NEUTRAL",
        "scenarios": [],
        "belief_space": {},
        "confidence": {},
        "time_horizon": "unknown",
        "decay_profile": "unknown",
        "rationale": "",
        "risk_factors": []
    }

    # Parse all scenarios (CRITICAL for belief-space output)
    scenarios = parse_scenarios(response)
    result["scenarios"] = scenarios

    # Parse contradictions
    contradictions = parse_contradictions(response)
    result["belief_space"] = {
        "contradictions": contradictions,
        "narrative_count": len(scenarios),
        "regime_uncertainty": "high" if len(scenarios) > 2 else "medium" if len(scenarios) == 2 else "low"
    }

    # Determine primary direction from highest likelihood scenario
    if scenarios:
        sorted_scenarios = sorted(scenarios, key=lambda s: s.get("likelihood", 0), reverse=True)
        result["direction"] = sorted_scenarios[0].get("direction", "NEUTRAL")
        result["belief_space"]["dominant_narrative"] = sorted_scenarios[0].get("name", "Unknown")
    else:
        # Fallback: Parse PRIMARY_DIRECTION (or DIRECTION for backward compatibility)
        direction_match = re.search(r"PRIMARY_DIRECTION:\s*(BULLISH|BEARISH|NEUTRAL)", response, re.IGNORECASE)
        if not direction_match:
            direction_match = re.search(r"DIRECTION:\s*(BULLISH|BEARISH|NEUTRAL)", response, re.IGNORECASE)
        if direction_match:
            result["direction"] = direction_match.group(1).upper()

    # Parse CONFIDENCE section
    confidence = {}
    score_match = re.search(r"score:\s*([\d.]+)", response, re.IGNORECASE)
    if score_match:
        try:
            confidence["score"] = float(score_match.group(1))
        except ValueError:
            confidence["score"] = 0.5

    chain_count_match = re.search(r"chain_count:\s*(\d+)", response, re.IGNORECASE)
    if chain_count_match:
        confidence["chain_count"] = int(chain_count_match.group(1))

    source_div_match = re.search(r"source_diversity:\s*(\d+)", response, re.IGNORECASE)
    if source_div_match:
        confidence["source_diversity"] = int(source_div_match.group(1))

    strongest_match = re.search(r"strongest_chain:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
    if strongest_match:
        confidence["strongest_chain"] = strongest_match.group(1).strip().strip('"\'')

    result["confidence"] = confidence

    # Parse TIME_HORIZON
    horizon_match = re.search(r"TIME_HORIZON:\s*(intraday|days|weeks|months|regime_shift)", response, re.IGNORECASE)
    if horizon_match:
        result["time_horizon"] = horizon_match.group(1).lower()

    # Parse DECAY_PROFILE
    decay_match = re.search(r"DECAY_PROFILE:\s*(fast|medium|slow)", response, re.IGNORECASE)
    if decay_match:
        result["decay_profile"] = decay_match.group(1).lower()

    # Parse RATIONALE
    rationale_match = re.search(r"RATIONALE:\s*\n(.+?)(?=\nRISK_FACTORS:|\Z)", response, re.DOTALL | re.IGNORECASE)
    if rationale_match:
        result["rationale"] = rationale_match.group(1).strip()

    # Parse RISK_FACTORS
    risks_match = re.search(r"RISK_FACTORS:\s*\n(.+?)(?:\Z)", response, re.DOTALL | re.IGNORECASE)
    if risks_match:
        risks_text = risks_match.group(1)
        # Extract bullet points
        risks = re.findall(r"[-•]\s*(.+?)(?:\n|$)", risks_text)
        result["risk_factors"] = [r.strip() for r in risks if r.strip()]

    return result
