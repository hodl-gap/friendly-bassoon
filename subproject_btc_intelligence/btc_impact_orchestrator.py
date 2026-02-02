"""
BTC Impact Orchestrator - Main Entry Point

Phase 1 (MVP): query → retrieve → analyze → output
Phase 2: query → retrieve → extract_variables → fetch_data → analyze → output
No LangGraph yet - simple sequential workflow.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

# Add sibling subprojects to path
# Note: retriever goes at index 0, data_collection appended at end to avoid shadowing states.py
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))
# data_collection path is added by current_data_fetcher when needed

from .states import BTCImpactState
from .impact_analysis import analyze_impact
from .variable_extraction import extract_variables
from .current_data_fetcher import fetch_current_data, format_current_values_for_prompt
from .pattern_validator import validate_patterns, format_validated_patterns_for_prompt
from .relationship_store import (
    load_chains,
    store_chains,
    get_relevant_historical_chains,
    format_historical_chains_for_prompt
)
from . import config


def extract_logic_chains(retrieved_chunks: List[Dict]) -> List[Dict]:
    """
    Extract logic_chains from retrieved chunks.

    Each chunk's extracted_data may contain a logic_chains field.
    """
    all_chains = []

    for chunk in retrieved_chunks:
        # Try to get extracted_data (may be string or dict)
        extracted = chunk.get("extracted_data")

        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except json.JSONDecodeError:
                continue

        if isinstance(extracted, dict):
            chains = extracted.get("logic_chains", [])
            for chain in chains:
                # Add source attribution
                chain_with_source = dict(chain)
                chain_with_source["source"] = extracted.get("source", "Unknown")
                all_chains.append(chain_with_source)

    return all_chains


def retrieve_context(query: str) -> BTCImpactState:
    """
    Step 1: Call database_retriever to get relevant context.

    Returns state populated with retrieval results.
    """
    print(f"\n[Retrieve] Querying: {query}")
    print("-" * 50)

    # Import retriever
    from retrieval_orchestrator import run_retrieval

    # Run retrieval
    result = run_retrieval(query)

    # Extract relevant fields
    state = BTCImpactState(
        query=query,
        retrieved_chunks=result.get("retrieved_chunks", []),
        retrieval_answer=result.get("answer", ""),
        retrieval_synthesis=result.get("synthesis", ""),
        confidence_metadata=result.get("confidence_metadata", {})
    )

    # Extract logic chains from chunks
    state["logic_chains"] = extract_logic_chains(state["retrieved_chunks"])

    print(f"\n[Retrieve] Got {len(state['retrieved_chunks'])} chunks")
    print(f"[Retrieve] Extracted {len(state['logic_chains'])} logic chains")

    if config.VERBOSE:
        print(f"\n[Retrieve] Answer:\n{state['retrieval_answer'][:500]}...")
        print(f"\n[Retrieve] Synthesis:\n{state['retrieval_synthesis'][:500]}...")

    return state


def format_output(state: BTCImpactState, as_json: bool = False) -> str:
    """Format the final output for display."""

    current_values = state.get("current_values", {})

    if as_json:
        output = {
            "direction": state.get("direction", "NEUTRAL"),
            "confidence": state.get("confidence", {}),
            "time_horizon": state.get("time_horizon", "unknown"),
            "decay_profile": state.get("decay_profile", "unknown"),
            "rationale": state.get("rationale", ""),
            "risk_factors": state.get("risk_factors", []),
            "current_values": current_values,
            "btc_price": state.get("btc_price")
        }
        return json.dumps(output, indent=2)

    # Human-readable format
    direction = state.get("direction", "NEUTRAL")
    confidence = state.get("confidence", {})
    time_horizon = state.get("time_horizon", "unknown")
    decay_profile = state.get("decay_profile", "unknown")
    rationale = state.get("rationale", "")
    risk_factors = state.get("risk_factors", [])

    conf_score = confidence.get("score", "N/A")
    chain_count = confidence.get("chain_count", "N/A")
    source_div = confidence.get("source_diversity", "N/A")
    strongest = confidence.get("strongest_chain", "N/A")

    lines = [
        "=" * 60,
        f"DIRECTION: {direction}",
        f"CONFIDENCE: {conf_score} ({chain_count} chains, {source_div} sources)",
        f"TIME HORIZON: {time_horizon} ({decay_profile} decay)",
    ]

    # Add current values section if available
    if current_values:
        lines.append("")
        lines.append("CURRENT DATA:")
        current_text = format_current_values_for_prompt(current_values)
        for line in current_text.split("\n"):
            lines.append(f"  {line}")

    lines.extend([
        "",
        "RATIONALE:",
        rationale,
        "",
        f"STRONGEST CHAIN: {strongest}",
        "",
        "RISK FACTORS:"
    ])

    for risk in risk_factors:
        lines.append(f"  - {risk}")

    lines.append("=" * 60)

    return "\n".join(lines)


def run_btc_impact_analysis(
    query: str,
    output_json: bool = False,
    skip_data_fetch: bool = False,
    skip_chain_store: bool = False
) -> Dict[str, Any]:
    """
    Main entry point for BTC impact analysis.

    Args:
        query: User's question about BTC impact
        output_json: If True, return JSON-formatted output
        skip_data_fetch: If True, skip fetching current data (Phase 1 mode)
        skip_chain_store: If True, skip loading/storing logic chains (Phase 3)

    Returns:
        Final state dict with analysis results
    """
    print("\n" + "=" * 60)
    print("BTC IMPACT ANALYSIS")
    print("=" * 60)

    # Step 1: Retrieve context
    state = retrieve_context(query)

    # Step 2: Load historical chains (Phase 3)
    if not skip_chain_store:
        state = load_chains(state)

    # Step 3: Extract variables from retrieved context (Phase 2)
    if not skip_data_fetch:
        state = extract_variables(state)

    # Step 4: Fetch current data for extracted variables (Phase 2)
    if not skip_data_fetch and state.get("extracted_variables"):
        state = fetch_current_data(state)

    # Step 5: Validate research patterns against current data
    if not skip_data_fetch:
        state = validate_patterns(state)

    # Step 6: Analyze impact (LLM call with current data + validated patterns)
    state = analyze_impact(state)

    # Step 7: Store newly discovered chains (Phase 3)
    if not skip_chain_store:
        state = store_chains(state)

    # Format and print output
    output = format_output(state, as_json=output_json)
    print("\n" + output)

    return dict(state)


if __name__ == "__main__":
    # Quick test
    test_query = "What is the impact of TGA drawdown on BTC?"
    run_btc_impact_analysis(test_query)
