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

    # Update state
    state["direction"] = parsed.get("direction", "NEUTRAL")
    state["confidence"] = parsed.get("confidence", {})
    state["time_horizon"] = parsed.get("time_horizon", "unknown")
    state["decay_profile"] = parsed.get("decay_profile", "unknown")
    state["rationale"] = parsed.get("rationale", "")
    state["risk_factors"] = parsed.get("risk_factors", [])

    return state


def parse_impact_response(response: str) -> Dict[str, Any]:
    """Parse the structured LLM response into components."""
    result = {
        "direction": "NEUTRAL",
        "confidence": {},
        "time_horizon": "unknown",
        "decay_profile": "unknown",
        "rationale": "",
        "risk_factors": []
    }

    # Parse PRIMARY_DIRECTION (or fallback to DIRECTION for backward compatibility)
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
