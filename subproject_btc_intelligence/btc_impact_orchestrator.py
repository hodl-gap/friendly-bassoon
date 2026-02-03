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
    format_historical_chains_for_prompt,
    load_regime_state,
    update_regime_from_analysis,
    get_regime_context_for_prompt
)
from . import config


def extract_logic_chains(retrieved_chunks: List[Dict]) -> List[Dict]:
    """
    Extract logic_chains from retrieved chunks.

    Each chunk's metadata.extracted_data may contain a logic_chains field.
    Note: logic_chains may not be present in older data - they are generated
    by answer_generation.py Stage 1 at query time for chunks without them.
    """
    all_chains = []

    for chunk in retrieved_chunks:
        # Get extracted_data from metadata (correct path)
        metadata = chunk.get("metadata", {})
        extracted = metadata.get("extracted_data")

        # Also check direct path for backward compatibility
        if extracted is None:
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
                chain_with_source["source"] = extracted.get("source", metadata.get("source", "Unknown"))
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
        confidence_metadata=result.get("confidence_metadata", {}),
        topic_coverage=result.get("topic_coverage", {})
    )

    # Log topic coverage warning if extrapolation detected
    topic_coverage = state.get("topic_coverage", {})
    if topic_coverage.get("extrapolation_note"):
        print(f"\n[Retrieve] ⚠️ {topic_coverage['extrapolation_note']}")

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
    topic_coverage = state.get("topic_coverage", {})

    if as_json:
        output = {
            "direction": state.get("direction", "NEUTRAL"),
            "confidence": state.get("confidence", {}),
            "time_horizon": state.get("time_horizon", "unknown"),
            "decay_profile": state.get("decay_profile", "unknown"),
            "rationale": state.get("rationale", ""),
            "risk_factors": state.get("risk_factors", []),
            "current_values": current_values,
            "btc_price": state.get("btc_price"),
            "topic_coverage": topic_coverage
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
    ]

    # Add extrapolation warning if topic mismatch detected
    if topic_coverage.get("extrapolation_note"):
        lines.extend([
            "⚠️  DATA SOURCE WARNING:",
            f"    {topic_coverage['extrapolation_note']}",
            f"    Query entities: {topic_coverage.get('query_entities', [])}",
            f"    Found in chunks: {topic_coverage.get('found_entities', [])}",
            "-" * 60,
        ])

    lines.extend([
        f"DIRECTION: {direction}",
        f"CONFIDENCE: {conf_score} ({chain_count} chains, {source_div} sources)",
        f"TIME HORIZON: {time_horizon} ({decay_profile} decay)",
    ])

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
    skip_chain_store: bool = False,
    use_integrated_pipeline: bool = False
) -> Dict[str, Any]:
    """
    Main entry point for BTC impact analysis.

    Args:
        query: User's question about BTC impact
        output_json: If True, return JSON-formatted output
        skip_data_fetch: If True, skip fetching current data (Phase 1 mode)
        skip_chain_store: If True, skip loading/storing logic chains (Phase 3)
        use_integrated_pipeline: If True, use shared/integration.py for
            Variable Mapper → Data Collection wiring instead of standalone fetching

    Returns:
        Final state dict with analysis results
    """
    print("\n" + "=" * 60)
    print("BTC IMPACT ANALYSIS")
    print("=" * 60)

    # Step 0: Load regime state (provides context for analysis)
    regime_state = load_regime_state()
    if regime_state.get("liquidity_regime"):
        print(f"[Regime] Current: {regime_state.get('liquidity_regime')} (driver: {regime_state.get('dominant_driver')})")

    # Step 1: Retrieve context
    state = retrieve_context(query)

    # Add regime context to state for use in analysis
    state["regime_state"] = regime_state

    # Step 2: Load historical chains (Phase 3)
    if not skip_chain_store:
        state = load_chains(state)

    # Step 3 & 4: Variable extraction and data fetching
    if not skip_data_fetch:
        if use_integrated_pipeline:
            # Use integrated Mapper → Collection pipeline
            state = _run_integrated_pipeline(state)
        else:
            # Original standalone approach
            state = extract_variables(state)
            if state.get("extracted_variables"):
                state = fetch_current_data(state)

    # Step 5: Validate research patterns against current data
    if not skip_data_fetch:
        state = validate_patterns(state)

    # Step 6: Analyze impact (LLM call with current data + validated patterns)
    state = analyze_impact(state)

    # Step 7: Store newly discovered chains (Phase 3)
    if not skip_chain_store:
        state = store_chains(state)

    # Step 8: Update regime state based on analysis results
    if not skip_chain_store:
        new_regime = update_regime_from_analysis(dict(state))
        if new_regime:
            state["regime_state"] = new_regime
            print(f"[Regime] Updated to: {new_regime.get('liquidity_regime')}")

    # Format and print output
    output = format_output(state, as_json=output_json)
    print("\n" + output)

    return dict(state)


def _run_integrated_pipeline(state: BTCImpactState) -> BTCImpactState:
    """
    Run the integrated Variable Mapper → Data Collection pipeline.

    Uses shared/integration.py to:
    1. Run Variable Mapper on synthesis text
    2. Fetch data via appropriate adapters for each mapped variable

    Args:
        state: Current BTC impact state

    Returns:
        Updated state with extracted_variables, current_values, etc.
    """
    print("\n[Integrated] Running Mapper → Collection pipeline...")

    try:
        from shared.integration import map_and_fetch_variables

        synthesis = state.get("retrieval_synthesis", "")
        logic_chains = state.get("logic_chains", [])

        # Run integrated pipeline
        result = map_and_fetch_variables(
            synthesis=synthesis,
            logic_chains=logic_chains,
            temporal_context=None,  # Could pass data_temporal_summary if available
            lookback_days=45
        )

        # Update state with results
        mapped_vars = result.get("mapped_variables", [])
        fetched_data = result.get("fetched_data", {})
        unmapped = result.get("unmapped_variables", [])
        errors = result.get("errors", [])

        print(f"[Integrated] Mapped {len(mapped_vars)} variables")
        print(f"[Integrated] Fetched data for {len(fetched_data)} variables")
        if unmapped:
            print(f"[Integrated] Unmapped: {unmapped}")
        if errors:
            print(f"[Integrated] Errors: {errors}")

        # Convert to expected state format
        state["extracted_variables"] = [
            {"normalized": v["name"], "raw": v.get("raw_name", v["name"])}
            for v in mapped_vars
        ]

        # Convert fetched_data to current_values format
        current_values = {}
        for var_name, data in fetched_data.items():
            history = data.get("data", [])
            if history:
                latest = history[-1]
                current_values[var_name] = {
                    "value": latest[1],
                    "date": latest[0],
                    "source": data.get("source", ""),
                    "series_id": data.get("series_id", ""),
                    "changes": _calculate_changes(history)
                }

        state["current_values"] = current_values
        state["fetch_errors"] = unmapped + [e for e in errors]

        # Set BTC price if available
        if "btc" in current_values:
            state["btc_price"] = current_values["btc"]["value"]

    except ImportError as e:
        print(f"[Integrated] Integration module not available: {e}")
        # Fall back to original approach
        state = extract_variables(state)
        if state.get("extracted_variables"):
            state = fetch_current_data(state)
    except Exception as e:
        print(f"[Integrated] Pipeline error: {e}")
        # Fall back to original approach
        state = extract_variables(state)
        if state.get("extracted_variables"):
            state = fetch_current_data(state)

    return state


def _calculate_changes(history: list) -> dict:
    """Calculate period-over-period changes from history."""
    if not history or len(history) < 2:
        return {}

    from datetime import datetime

    latest_value = history[-1][1]
    latest_date = datetime.strptime(history[-1][0], "%Y-%m-%d")

    changes = {}

    # Find value from ~1 week ago (5-9 days)
    for date_str, value in reversed(history):
        date = datetime.strptime(date_str, "%Y-%m-%d")
        days_diff = (latest_date - date).days
        if 5 <= days_diff <= 10:
            if value != 0:
                abs_change = latest_value - value
                pct_change = (abs_change / value) * 100
                direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
                changes["change_1w"] = {
                    "absolute": abs_change,
                    "percentage": pct_change,
                    "direction": direction
                }
            break

    # Find value from ~1 month ago (25-35 days)
    for date_str, value in reversed(history):
        date = datetime.strptime(date_str, "%Y-%m-%d")
        days_diff = (latest_date - date).days
        if 25 <= days_diff <= 40:
            if value != 0:
                abs_change = latest_value - value
                pct_change = (abs_change / value) * 100
                direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
                changes["change_1m"] = {
                    "absolute": abs_change,
                    "percentage": pct_change,
                    "direction": direction
                }
            break

    return changes


if __name__ == "__main__":
    # Quick test
    test_query = "What is the impact of TGA drawdown on BTC?"
    run_btc_impact_analysis(test_query)
