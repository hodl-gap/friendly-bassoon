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
from .historical_event_detector import detect_historical_gap, identify_instruments, get_date_range
from .historical_data_fetcher import fetch_historical_event_data, compare_to_current
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


def parse_logic_chains_from_answer(answer_text: str) -> List[Dict]:
    """
    Parse logic chains from the Stage 1 answer text (retrieval_answer).

    Stage 1 output format:
        **CHAIN:** cause [cause_norm] → effect [effect_norm] → effect2 [effect2_norm]
        **MECHANISM:** explanation
        **SOURCE:** source name (chunk_id)
        **CONNECTION:** connection info

    Returns list of parsed chain dicts.
    """
    import re

    chains = []

    # Split by **CHAIN:** to get each chain block
    chain_blocks = re.split(r'\*\*CHAIN:\*\*', answer_text)

    for block in chain_blocks[1:]:  # Skip first empty split
        chain_dict = {}

        # Extract the chain line (first line after CHAIN:)
        chain_match = re.match(r'\s*(.+?)(?:\n|$)', block)
        if chain_match:
            chain_line = chain_match.group(1).strip()
            chain_dict["chain_text"] = chain_line

            # Parse steps from chain line: "cause [norm] → effect [norm]"
            # Extract normalized variables in brackets
            normalized_vars = re.findall(r'\[([^\]]+)\]', chain_line)
            chain_dict["normalized_variables"] = normalized_vars

            # Parse arrow-separated steps
            steps = []
            # Split by arrow variants (→ or -> or - >)
            step_parts = re.split(r'\s*(?:→|->|—>)\s*', chain_line)
            for i, part in enumerate(step_parts[:-1]):
                # Extract variable name (text before bracket)
                cause_match = re.match(r'([^\[]+)', part.strip())
                effect_match = re.match(r'([^\[]+)', step_parts[i+1].strip())
                if cause_match and effect_match:
                    steps.append({
                        "cause": cause_match.group(1).strip(),
                        "effect": effect_match.group(1).strip()
                    })
            chain_dict["steps"] = steps

        # Extract MECHANISM
        mechanism_match = re.search(r'\*\*MECHANISM:\*\*\s*(.+?)(?=\*\*|$)', block, re.DOTALL)
        if mechanism_match:
            chain_dict["mechanism"] = mechanism_match.group(1).strip()

        # Extract SOURCE
        source_match = re.search(r'\*\*SOURCE:\*\*\s*(.+?)(?=\*\*|\n|$)', block)
        if source_match:
            chain_dict["source"] = source_match.group(1).strip()

        # Extract CONNECTION
        connection_match = re.search(r'\*\*CONNECTION:\*\*\s*(.+?)(?=\*\*|$)', block, re.DOTALL)
        if connection_match:
            chain_dict["connection"] = connection_match.group(1).strip()

        if chain_dict.get("steps") or chain_dict.get("chain_text"):
            chains.append(chain_dict)

    return chains


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

    # Extract logic chains from chunks (pre-indexed in metadata)
    chunk_chains = extract_logic_chains(state["retrieved_chunks"])

    # Also parse logic chains from Stage 1 answer text (query-time extracted)
    answer_chains = parse_logic_chains_from_answer(state.get("retrieval_answer", ""))

    # Combine both sources
    state["logic_chains"] = chunk_chains + answer_chains

    print(f"\n[Retrieve] Got {len(state['retrieved_chunks'])} chunks")
    print(f"[Retrieve] Extracted {len(chunk_chains)} chains from chunk metadata")
    print(f"[Retrieve] Parsed {len(answer_chains)} chains from Stage 1 answer")
    print(f"[Retrieve] Total logic chains: {len(state['logic_chains'])}")

    # Debug: Print raw retrieved chunks (per CLAUDE.md: print full LLM outputs)
    print(f"\n[Retrieve] === RAW RETRIEVED CHUNKS ===")
    for i, chunk in enumerate(state['retrieved_chunks'], 1):
        print(f"\n--- CHUNK {i} ---")
        print(f"ID: {chunk.get('id', 'N/A')}")
        print(f"Score: {chunk.get('score', 'N/A')}")
        metadata = chunk.get('metadata', {})
        print(f"Source: {metadata.get('source', 'N/A')}")
        print(f"Date: {metadata.get('date', 'N/A')}")
        print(f"What Happened: {metadata.get('what_happened', 'N/A')}")
        print(f"Interpretation: {metadata.get('interpretation', 'N/A')}")
    print(f"[Retrieve] === END RAW CHUNKS ===")

    if config.VERBOSE:
        print(f"\n[Retrieve] Answer:\n{state['retrieval_answer'][:500]}...")
        print(f"\n[Retrieve] Synthesis:\n{state['retrieval_synthesis'][:500]}...")

    return state


def format_output(state: BTCImpactState, as_json: bool = False) -> str:
    """Format the final output for display."""

    current_values = state.get("current_values", {})
    topic_coverage = state.get("topic_coverage", {})
    historical_event_data = state.get("historical_event_data", {})

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
            "topic_coverage": topic_coverage,
            "historical_event_data": historical_event_data
        }
        return json.dumps(output, indent=2, default=str)

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

    # Add historical event section if available
    if historical_event_data.get("event_detected"):
        lines.append("")
        lines.append("-" * 60)
        lines.append("HISTORICAL EVENT COMPARISON:")
        lines.append(f"  Event: {historical_event_data.get('event_name', 'Unknown')}")
        period = historical_event_data.get("period", {})
        lines.append(f"  Period: {period.get('start', '?')} to {period.get('end', '?')}")

        instruments = historical_event_data.get("instruments", {})
        if instruments:
            lines.append("  Market Impact:")
            for name, data in instruments.items():
                metrics = data.get("metrics", {})
                change = metrics.get("peak_to_trough_pct", 0)
                lines.append(f"    - {name}: {change:+.1f}%")

        correlations = historical_event_data.get("correlations", {})
        if correlations:
            lines.append("  Correlations:")
            for pair, corr in correlations.items():
                lines.append(f"    - {pair.replace('_', ' ')}: {corr:.2f}")

        comparisons = historical_event_data.get("comparison_to_current", {}).get("comparisons", {})
        if comparisons:
            lines.append("  Then vs Now:")
            for name, comp in comparisons.items():
                lines.append(f"    - {name}: {comp.get('note', '')}")

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

    # Step 5.5: Historical event data enrichment
    if not skip_data_fetch:
        state = enrich_with_historical_event(state)

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


def enrich_with_historical_event(state: BTCImpactState) -> BTCImpactState:
    """
    Step 5.5: Detect and fetch historical event data if needed.

    Detects if the user query references a historical event not covered
    by the retrieved research, and if so, fetches actual market data
    for that event.

    Updates state with:
    - historical_event_data: Contains event details, instruments, metrics, correlations
    """
    if not config.ENABLE_HISTORICAL_EVENT_DETECTION:
        state["historical_event_data"] = {}
        return state

    query = state.get("query", "")
    synthesis = state.get("retrieval_synthesis", "")
    topic_coverage = state.get("topic_coverage", {})
    logic_chains = state.get("logic_chains", [])

    # Step 1: Detect historical event gap
    print("\n[Historical Event] Checking for historical event gap...")
    gap_result = detect_historical_gap(query, topic_coverage, synthesis)

    if not gap_result.get("gap_detected"):
        print(f"[Historical Event] No gap detected: {gap_result.get('reasoning', '')}")
        state["historical_event_data"] = {"event_detected": False}
        return state

    event_description = gap_result.get("event_description", "Unknown event")
    date_search_query = gap_result.get("date_search_query", "")

    print(f"[Historical Event] Gap detected: {event_description}")

    # Step 2: Identify instruments from research context
    print("[Historical Event] Identifying instruments...")
    instruments = identify_instruments(
        event_description=event_description,
        query=query,
        synthesis=synthesis,
        logic_chains=logic_chains
    )
    print(f"[Historical Event] Instruments: {[i.get('ticker') for i in instruments]}")

    # Step 3: Get date range via web search
    print("[Historical Event] Determining date range...")
    if date_search_query:
        date_range = get_date_range(event_description, date_search_query)
    else:
        # Fallback if no search query provided
        from .historical_event_detector import _fallback_date_range
        date_range = _fallback_date_range(event_description)

    print(f"[Historical Event] Period: {date_range.get('start_date')} to {date_range.get('end_date')} (confidence: {date_range.get('confidence')})")

    # Step 4: Fetch historical data
    print("[Historical Event] Fetching historical data...")
    historical_data = fetch_historical_event_data(
        instruments=instruments,
        start_date=date_range.get("start_date"),
        end_date=date_range.get("end_date")
    )

    # Step 5: Compare to current values
    current_values = state.get("current_values", {})
    if current_values and historical_data.get("instruments"):
        comparison = compare_to_current(historical_data, current_values)
    else:
        comparison = {"comparisons": {}}

    # Build historical event data
    state["historical_event_data"] = {
        "event_detected": True,
        "event_name": event_description,
        "period": {
            "start": date_range.get("start_date"),
            "end": date_range.get("end_date"),
            "peak_date": date_range.get("peak_date"),
            "date_confidence": date_range.get("confidence")
        },
        "instruments": historical_data.get("instruments", {}),
        "correlations": historical_data.get("correlations", {}),
        "comparison_to_current": comparison
    }

    instr_count = len(historical_data.get("instruments", {}))
    print(f"[Historical Event] Fetched data for {instr_count} instruments")

    return state


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
