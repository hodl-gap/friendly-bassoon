"""
Insight Orchestrator - Main Entry Point

Phase 1 (MVP): query → retrieve → analyze → output
Phase 2: query → retrieve → extract_variables → fetch_data → analyze → output
No LangGraph yet - simple sequential workflow.

Architecture: Risk Intelligence now receives ENRICHED context from retrieval layer.
Gap detection and web chain extraction are handled by the retrieval layer.
Risk Intelligence focuses on multi-asset impact analysis.
"""

import sys
import json
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List

# Add sibling subprojects to path
# Note: retriever goes at index 0, data_collection appended at end to avoid shadowing states.py
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))
# data_collection path is added by current_data_fetcher when needed

from .states import RiskImpactState
from .impact_analysis import analyze_impact
from .variable_extraction import extract_variables
from .current_data_fetcher import fetch_current_data, format_current_values_for_prompt
from shared.snapshot import snapshot_state, start_run as _start_run, ENABLE_SNAPSHOTS
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
from .historical_event_detector import detect_historical_gap, identify_instruments, get_date_range, detect_historical_analogs
from .historical_data_fetcher import fetch_historical_event_data, compare_to_current
from .historical_aggregator import fetch_multiple_analogs, aggregate_analogs, format_analogs_for_prompt
from .asset_configs import get_asset_config
from .prediction_tracker import extract_predictions, log_predictions
from shared.chain_graph import ChainGraph
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


def retrieve_context(query: str, image_path: str = None) -> RiskImpactState:
    """
    Step 1: Call database_retriever to get enriched context.

    The retrieval layer now handles:
    - Query expansion
    - Vector search
    - Answer generation
    - Gap detection & filling (moved from BTC Intelligence)
    - Web chain extraction

    Args:
        query: User's question or search query
        image_path: Optional path to indicator chart image for vision-based extraction

    Returns state populated with retrieval results including merged logic chains.
    """
    print(f"\n[Retrieve] Querying: {query}")
    print("-" * 50)

    # Import retriever
    from retrieval_orchestrator import run_retrieval

    # Run retrieval (now includes gap detection and filling)
    result = run_retrieval(query, image_path=image_path)

    # Extract relevant fields - retriever now provides enriched context
    state = RiskImpactState(
        query=query,
        retrieved_chunks=result.get("retrieved_chunks", []),
        retrieval_answer=result.get("answer", ""),
        synthesis=result.get("synthesis", ""),
        confidence_metadata=result.get("confidence_metadata", {}),
        topic_coverage=result.get("topic_coverage", {})
    )

    # Log topic coverage warning if extrapolation detected
    topic_coverage = state.get("topic_coverage", {})
    if topic_coverage.get("extrapolation_note"):
        print(f"\n[Retrieve] ⚠️ {topic_coverage['extrapolation_note']}")

    # Use logic chains from retriever (already merged DB + web chains)
    # The retriever now handles gap detection and web chain extraction
    logic_chains = result.get("logic_chains", [])

    if logic_chains:
        state["logic_chains"] = logic_chains
        web_chain_count = sum(1 for c in logic_chains if c.get("source_type") == "web")
        db_chain_count = len(logic_chains) - web_chain_count
        print(f"\n[Retrieve] Got {len(logic_chains)} merged chains ({db_chain_count} DB, {web_chain_count} web)")
    else:
        # Fallback: extract from chunks if not provided by retriever
        chunk_chains = extract_logic_chains(state["retrieved_chunks"])
        answer_chains = parse_logic_chains_from_answer(state.get("retrieval_answer", ""))
        state["logic_chains"] = chunk_chains + answer_chains
        print(f"\n[Retrieve] Extracted {len(state['logic_chains'])} chains from chunks/answer")

    # Copy gap-related fields from retriever result
    state["knowledge_gaps"] = result.get("knowledge_gaps", {})
    state["gap_enrichment_text"] = result.get("gap_enrichment_text", "")
    state["filled_gaps"] = result.get("filled_gaps", [])
    state["partially_filled_gaps"] = result.get("partially_filled_gaps", [])
    state["unfillable_gaps"] = result.get("unfillable_gaps", [])

    # Log gap filling results if any
    filled_count = len(state.get("filled_gaps", []))
    if filled_count > 0:
        print(f"[Retrieve] Gap filling: {filled_count} gaps filled by retriever")

    print(f"\n[Retrieve] Got {len(state['retrieved_chunks'])} chunks")
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
        print(f"\n[Retrieve] Synthesis:\n{state['synthesis'][:500]}...")

    return state


def format_insight(state: RiskImpactState, as_json: bool = False, asset_class: str = "btc") -> str:
    """Format the final output for display - Insight Report format."""

    insight = state.get("insight_output", {})
    tracks = insight.get("tracks", [])
    synthesis = insight.get("synthesis", "")
    uncertainties = insight.get("key_uncertainties", [])
    current_values = state.get("current_values", {})
    asset_name = get_asset_config(asset_class)["name"]

    if as_json:
        output = {
            "asset_class": asset_class,
            "output_mode": "insight",
            "tracks": tracks,
            "synthesis": synthesis,
            "key_uncertainties": uncertainties,
            "direction": state.get("direction", "NEUTRAL"),
            "confidence": state.get("confidence", {}),
            "current_values": current_values,
        }
        return json.dumps(output, indent=2, default=str)

    lines = [
        "=" * 60,
        f"INSIGHT REPORT -- {asset_name.upper()}",
        "=" * 60,
    ]

    # Sort tracks: sequenced tracks first (by position), then unsequenced
    tracks_sorted = sorted(tracks, key=lambda t: (t.get("sequence_position") or 999, tracks.index(t)))

    for i, track in enumerate(tracks_sorted, 1):
        title = track.get("title", f"Track {i}")
        confidence = track.get("confidence", 0)
        mechanism = track.get("causal_mechanism", "N/A")
        time_horizon = track.get("time_horizon", "unknown")

        lines.append("")
        lines.append(f"TRACK {i}: {title}")
        lines.append(f"  Confidence: {confidence*100:.0f}%")
        lines.append(f"  Mechanism: {mechanism}")
        lines.append(f"  Time Horizon: {time_horizon}")
        seq = track.get("sequence_position")
        if seq:
            lines.append(f"  Phase: {seq}")

        # Historical evidence
        evidence = track.get("historical_evidence", {})
        if evidence:
            precedent_count = evidence.get("precedent_count")
            success_rate = evidence.get("success_rate")
            summary = evidence.get("precedent_summary", "")
            if precedent_count is not None and success_rate is not None:
                lines.append(f"  Evidence: {precedent_count} precedents, {success_rate*100:.0f}% success rate")
            if summary:
                lines.append(f"    {summary}")

            precedents = evidence.get("precedents", [])
            for p in precedents[:3]:
                event = p.get("event", "")
                outcome = p.get("outcome", "")
                magnitude = p.get("magnitude", "")
                line = f"    - {event}"
                if outcome:
                    line += f": {outcome}"
                if magnitude:
                    line += f" ({magnitude})"
                lines.append(line)

        # Asset implications
        implications = track.get("asset_implications", [])
        if implications:
            lines.append("  Asset Implications:")
            for imp in implications:
                asset = imp.get("asset", "?")
                direction = imp.get("direction", "?")
                mag_range = imp.get("magnitude_range", "")
                timing = imp.get("timing", "")
                line = f"    - {asset}: {direction}"
                if mag_range:
                    line += f" ({mag_range}"
                    if timing:
                        line += f", {timing}"
                    line += ")"
                elif timing:
                    line += f" ({timing})"
                lines.append(line)

        # Monitoring variables
        monitors = track.get("monitoring_variables", [])
        if monitors:
            lines.append("  Monitor:")
            for m in monitors:
                variable = m.get("variable", "?")
                condition = m.get("condition", "?")
                meaning = m.get("meaning", "")
                line = f"    - {variable} {condition}"
                if meaning:
                    line += f": {meaning}"
                lines.append(line)

        lines.append("-" * 40)

    if synthesis:
        lines.append("")
        lines.append("SYNTHESIS:")
        lines.append(synthesis)

    if uncertainties:
        lines.append("")
        lines.append("KEY UNCERTAINTIES:")
        for u in uncertainties:
            lines.append(f"  - {u}")

    # Current values section
    if current_values:
        lines.append("")
        lines.append("CURRENT DATA:")
        current_text = format_current_values_for_prompt(current_values)
        for line in current_text.split("\n"):
            lines.append(f"  {line}")

    lines.append("=" * 60)

    return "\n".join(lines)


def format_output(state: RiskImpactState, as_json: bool = False, asset_class: str = "btc") -> str:
    """Format the final output for display - Belief Space format."""

    current_values = state.get("current_values", {})
    topic_coverage = state.get("topic_coverage", {})
    historical_event_data = state.get("historical_event_data", {})
    scenarios = state.get("scenarios", [])
    belief_space = state.get("belief_space", {})
    asset_name = get_asset_config(asset_class)["name"]

    if as_json:
        output = {
            # Asset class
            "asset_class": asset_class,
            # Belief Space Output (Primary)
            "scenarios": scenarios,
            "belief_space": belief_space,
            # Legacy fields (backward compatibility)
            "primary_direction": state.get("direction", "NEUTRAL"),
            "direction": state.get("direction", "NEUTRAL"),
            "confidence": state.get("confidence", {}),
            "time_horizon": state.get("time_horizon", "unknown"),
            "decay_profile": state.get("decay_profile", "unknown"),
            "rationale": state.get("rationale", ""),
            "risk_factors": state.get("risk_factors", []),
            "current_values": current_values,
            "asset_price": state.get("asset_price"),
            "btc_price": state.get("btc_price"),
            "topic_coverage": topic_coverage,
            "historical_event_data": historical_event_data
        }
        return json.dumps(output, indent=2, default=str)

    # Human-readable format - Belief Space
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
        f"BELIEF SPACE ANALYSIS — {asset_name.upper()}",
        "=" * 60,
    ]

    # Add extrapolation warning if topic mismatch detected
    if topic_coverage.get("extrapolation_note"):
        lines.extend([
            "",
            "⚠️  DATA SOURCE WARNING:",
            f"    {topic_coverage['extrapolation_note']}",
            f"    Query entities: {topic_coverage.get('query_entities', [])}",
            f"    Found in chunks: {topic_coverage.get('found_entities', [])}",
            "-" * 60,
        ])

    # Display all scenarios (the core belief space output)
    if scenarios:
        lines.append("")
        lines.append("SCENARIOS (Market Belief Paths):")
        lines.append("-" * 40)

        # Sort by likelihood descending
        sorted_scenarios = sorted(scenarios, key=lambda s: s.get("likelihood", 0), reverse=True)

        for i, scenario in enumerate(sorted_scenarios, 1):
            name = scenario.get("name", f"Scenario {i}")
            direction_s = scenario.get("direction", "NEUTRAL")
            likelihood = scenario.get("likelihood", 0)
            chain = scenario.get("chain", "N/A")
            likelihood_basis = scenario.get("likelihood_basis", "")

            # Direction indicator
            dir_symbol = "↑" if direction_s == "BULLISH" else "↓" if direction_s == "BEARISH" else "→"

            lines.append("")
            lines.append(f"  [{i}] {name}")
            lines.append(f"      Direction: {direction_s} {dir_symbol}")
            lines.append(f"      Likelihood: {likelihood*100:.0f}%{' - ' + likelihood_basis if likelihood_basis else ''}")
            lines.append(f"      Chain: {chain}")

            # Key data points if available
            key_data = scenario.get("key_data_points", [])
            if key_data:
                lines.append(f"      Key Data: {', '.join(key_data)}")

            # Rationale if available
            scenario_rationale = scenario.get("rationale", "")
            if scenario_rationale:
                lines.append(f"      Rationale: {scenario_rationale[:150]}...")

    # Display contradictions (critical for belief space)
    contradictions = belief_space.get("contradictions", [])
    if contradictions:
        lines.append("")
        lines.append("-" * 40)
        lines.append("CONTRADICTIONS (Coexisting Beliefs):")

        for contra in contradictions:
            thesis_a = contra.get("thesis_a", "")
            thesis_b = contra.get("thesis_b", "")
            description = contra.get("description", "")
            implication = contra.get("implication", "")

            if thesis_a and thesis_b:
                lines.append(f"  • \"{thesis_a}\" vs \"{thesis_b}\"")
            elif description:
                lines.append(f"  • {description}")

            if implication:
                lines.append(f"    → {implication}")

    lines.append("")
    lines.append("-" * 40)
    lines.append("SUMMARY:")
    lines.extend([
        f"  Primary Direction: {direction}",
        f"  Confidence: {conf_score} ({chain_count} chains, {source_div} sources)",
        f"  Regime Uncertainty: {belief_space.get('regime_uncertainty', 'unknown')}",
        f"  Time Horizon: {time_horizon} ({decay_profile} decay)",
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


def request_additional_context(state: RiskImpactState, topic: str) -> RiskImpactState:
    """
    Request additional context on a specific topic.

    BTC Intelligence can REQUEST more info on a topic if the initial
    retrieval doesn't cover something needed for analysis. This doesn't
    format the query - just passes the topic to retrieval.

    Args:
        state: Current BTC impact state
        topic: Topic to get more information on

    Returns:
        Updated state with additional chains merged
    """
    print(f"\n[Risk Intelligence] Requesting additional context on: {topic}")

    from retrieval_orchestrator import run_retrieval

    additional = run_retrieval(topic)
    additional_chains = additional.get("logic_chains", [])

    if additional_chains:
        existing_chains = state.get("logic_chains", [])
        # Simple merge - could deduplicate in future
        state["logic_chains"] = existing_chains + additional_chains
        print(f"[Risk Intelligence] Added {len(additional_chains)} chains, total: {len(state['logic_chains'])}")

    return state


def validate_claims(state: RiskImpactState) -> RiskImpactState:
    """
    Validate claims from synthesis using data_collection's claim validation pipeline.

    Calls run_claim_validation() which:
    1. Parses quantitative claims from synthesis text
    2. Resolves data IDs for referenced variables
    3. Fetches historical data
    4. Validates claims statistically (correlation, p-value)

    Updates state with:
    - claim_validation_results: List of validated/refuted claims
    """
    synthesis = state.get("synthesis", "")
    if not synthesis:
        state["claim_validation_results"] = []
        return state

    print("\n[Claim Validation] Validating claims from synthesis...")

    try:
        import sys
        # Ensure data_collection is importable
        dc_path = str(config.DATA_COLLECTION_DIR)
        if dc_path not in sys.path:
            sys.path.append(dc_path)

        from subproject_data_collection.data_collection_orchestrator import run_claim_validation

        result = run_claim_validation(synthesis_text=synthesis)

        # Extract validation results from the returned state
        final_output = result.get("final_output", {})
        validation_results = final_output.get("results", [])

        state["claim_validation_results"] = validation_results

        if validation_results:
            confirmed = sum(1 for r in validation_results if "confirmed" in r.get("status", ""))
            refuted = sum(1 for r in validation_results if "refuted" in r.get("status", ""))
            print(f"[Claim Validation] {len(validation_results)} claims validated: {confirmed} confirmed, {refuted} refuted")
        else:
            print("[Claim Validation] No quantitative claims found to validate")

    except ImportError as e:
        print(f"[Claim Validation] data_collection not available: {e}")
        state["claim_validation_results"] = []
    except Exception as e:
        print(f"[Claim Validation] Validation failed: {e}")
        state["claim_validation_results"] = []

    return state


def prepare_shared_context(
    query: str,
    skip_data_fetch: bool = False,
    use_integrated_pipeline: bool = False,
    image_path: str = None,
    asset_class: str = "btc"
) -> RiskImpactState:
    """
    Shared preparation: retrieval + variable extraction + data fetch +
    pattern validation + historical enrichment.

    This is the expensive part (~$0.30, ~250s) that runs ONCE
    regardless of how many asset classes we analyze.

    Args:
        query: User's question
        skip_data_fetch: If True, skip fetching current data
        use_integrated_pipeline: If True, use shared/integration.py
        image_path: Optional path to indicator chart image
        asset_class: Primary asset for variable prioritization

    Returns:
        State with shared context populated
    """
    # Step 1: Retrieve enriched context
    state = retrieve_context(query, image_path=image_path)
    state["asset_class"] = asset_class
    if ENABLE_SNAPSHOTS:
        snapshot_state("retrieve_context", state, "out")

    # Step 2: Variable extraction and data fetching
    if not skip_data_fetch:
        if use_integrated_pipeline:
            state = _run_integrated_pipeline(state)
        else:
            state = extract_variables(state)
            if ENABLE_SNAPSHOTS:
                snapshot_state("extract_variables", state, "out")
            if state.get("extracted_variables"):
                state = fetch_current_data(state)
                if ENABLE_SNAPSHOTS:
                    snapshot_state("fetch_current_data", state, "out")

    # Step 2.5: Validate claims from synthesis using data_collection pipeline
    if not skip_data_fetch and config.ENABLE_CLAIM_VALIDATION:
        state = validate_claims(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state("validate_claims", state, "out")

    # Step 3: Validate research patterns against current data
    if not skip_data_fetch:
        state = validate_patterns(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state("validate_patterns", state, "out")

    # Step 4: Historical event data enrichment
    if not skip_data_fetch:
        state = enrich_with_historical_event(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state("enrich_historical_event", state, "out")

    return state


def build_chain_graph(
    logic_chains: List[Dict],
    historical_chains: List[Dict],
    query: str
) -> ChainGraph:
    """Build a ChainGraph from retrieved + historical chains.

    Returns the graph with all chains added.
    """
    graph = ChainGraph()
    graph.add_chains_from_list(logic_chains, source="retrieved")
    graph.add_chains_from_list(historical_chains, source="historical")

    stats = graph.stats()
    print(f"[Chain Graph] Built: {stats['variables']} variables, {stats['edges']} edges")
    return graph


def run_asset_impact(
    shared_state: RiskImpactState,
    asset_class: str,
    skip_chain_store: bool = False
) -> Dict[str, Any]:
    """
    Asset-specific impact analysis. Runs the LLM call with asset-specific
    prompts and manages asset-specific chain storage.

    Args:
        shared_state: State from prepare_shared_context (read-only)
        asset_class: Asset class to analyze
        skip_chain_store: If True, skip chain loading/storage

    Returns:
        Result state dict for this asset
    """
    # Deep copy state to avoid mutation across parallel runs
    state = copy.deepcopy(shared_state)
    state["asset_class"] = asset_class

    asset_name = get_asset_config(asset_class)["name"]

    # Load asset-specific chains
    if not skip_chain_store:
        state = load_chains(state, asset_class=asset_class)

    # Load asset-specific regime
    regime_state = load_regime_state(asset_class=asset_class)
    state["regime_state"] = regime_state
    if regime_state.get("liquidity_regime"):
        print(f"[Regime/{asset_name}] Current: {regime_state.get('liquidity_regime')} (driver: {regime_state.get('dominant_driver')})")

    # Build chain graph for multi-hop causal paths
    chain_graph = build_chain_graph(
        logic_chains=state.get("logic_chains", []),
        historical_chains=state.get("historical_chains", []),
        query=state.get("query", "")
    )
    triggers = chain_graph.get_trigger_variables(state.get("query", ""))
    all_tracks = []
    for trigger in triggers[:3]:
        all_tracks.extend(chain_graph.get_tracks(trigger))
    state["chain_tracks"] = all_tracks
    convergence = chain_graph.get_convergence_points()
    state["chain_graph_text"] = chain_graph.format_for_prompt(all_tracks, convergence_points=convergence)

    # Regime characterization (Gap 1): compare current regime vs historical analogs
    if config.ENABLE_REGIME_CHARACTERIZATION:
        state = characterize_regime(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state(f"characterize_regime_{asset_class}", state, "out")

    # Run impact analysis with asset-specific prompt
    state = analyze_impact(state, asset_class=asset_class)
    if ENABLE_SNAPSHOTS:
        snapshot_state(f"analyze_impact_{asset_class}", state, "out")

    # Prediction tracking (Gap 5)
    if config.ENABLE_PREDICTION_TRACKING:
        try:
            predictions = extract_predictions(state, asset_class)
            if predictions:
                log_predictions(predictions)
                print(f"[Prediction Tracker] Logged {len(predictions)} predictions")
        except Exception as e:
            print(f"[Prediction Tracker] Logging error: {e}")

    # Store asset-specific chains
    if not skip_chain_store:
        state = store_chains(state, asset_class=asset_class)
        new_regime = update_regime_from_analysis(dict(state), asset_class=asset_class)
        if new_regime:
            state["regime_state"] = new_regime
            print(f"[Regime/{asset_name}] Updated to: {new_regime.get('liquidity_regime')}")

    return dict(state)


def run_multi_asset_analysis(
    query: str,
    assets: List[str] = None,
    output_json: bool = False,
    skip_data_fetch: bool = False,
    skip_chain_store: bool = False,
    use_integrated_pipeline: bool = False,
    image_path: str = None,
    output_mode: str = "insight"
) -> Dict[str, Dict[str, Any]]:
    """
    Main entry point for multi-asset impact analysis.

    Runs shared preparation once, then fans out to per-asset
    impact analysis in parallel.

    Args:
        query: User's question about macro event impact
        assets: List of asset classes (default: ["btc"])
        output_json: If True, format output as JSON
        skip_data_fetch: If True, skip fetching current data
        skip_chain_store: If True, skip chain loading/storage
        use_integrated_pipeline: If True, use integrated pipeline
        image_path: Optional path to indicator chart image
        output_mode: "insight" (default) or "belief_space"

    Returns:
        Dict mapping asset_class -> result state
    """
    if assets is None:
        assets = ["btc"]

    if ENABLE_SNAPSHOTS:
        _start_run()

    print("\n" + "=" * 60)
    asset_names = [get_asset_config(a)["name"] for a in assets]
    print(f"IMPACT ANALYSIS — {', '.join(asset_names)}")
    print("=" * 60)

    # Phase A: Shared preparation (runs once)
    shared_state = prepare_shared_context(
        query,
        skip_data_fetch=skip_data_fetch,
        use_integrated_pipeline=use_integrated_pipeline,
        image_path=image_path,
        asset_class=assets[0]
    )
    shared_state["output_mode"] = output_mode

    # Phase B: Per-asset impact analysis (parallel if multiple)
    results = {}
    if len(assets) == 1:
        results[assets[0]] = run_asset_impact(shared_state, assets[0], skip_chain_store)
    else:
        with ThreadPoolExecutor(max_workers=len(assets)) as executor:
            futures = {
                executor.submit(run_asset_impact, shared_state, asset, skip_chain_store): asset
                for asset in assets
            }
            for future in as_completed(futures):
                asset = futures[future]
                try:
                    results[asset] = future.result()
                except Exception as e:
                    print(f"\n[Error] {get_asset_config(asset)['name']} analysis failed: {e}")
                    results[asset] = {"direction": "ERROR", "error": str(e)}

    # Format and print output per asset
    for asset in assets:
        result = results.get(asset, {})
        if result.get("direction") == "ERROR":
            print(f"\n{'=' * 60}")
            print(f"{get_asset_config(asset)['name'].upper()} IMPACT ANALYSIS — ERROR")
            print(f"{'=' * 60}")
            print(f"Error: {result.get('error', 'Unknown')}")
            continue
        if result.get("output_mode") == "insight":
            output = format_insight(result, as_json=output_json, asset_class=asset)
        else:
            output = format_output(result, as_json=output_json, asset_class=asset)
        print("\n" + output)

    return results


def run_impact_analysis(
    query: str,
    output_json: bool = False,
    skip_data_fetch: bool = False,
    skip_chain_store: bool = False,
    use_integrated_pipeline: bool = False,
    image_path: str = None,
    output_mode: str = "insight"
) -> Dict[str, Any]:
    """
    Single-asset entry point (defaults to BTC).

    Args:
        query: User's question about macro event impact
        output_json: If True, return JSON-formatted output
        skip_data_fetch: If True, skip fetching current data (Phase 1 mode)
        skip_chain_store: If True, skip loading/storing logic chains (Phase 3)
        use_integrated_pipeline: If True, use shared/integration.py for
            Variable Mapper → Data Collection wiring instead of standalone fetching
        image_path: Optional path to indicator chart image for vision-based extraction
        output_mode: "insight" (default) or "belief_space"

    Returns:
        Final state dict with analysis results
    """
    results = run_multi_asset_analysis(
        query,
        assets=["btc"],
        output_json=output_json,
        skip_data_fetch=skip_data_fetch,
        skip_chain_store=skip_chain_store,
        use_integrated_pipeline=use_integrated_pipeline,
        image_path=image_path,
        output_mode=output_mode
    )
    return results["btc"]


# Backward-compatible alias
run_btc_impact_analysis = run_impact_analysis


def _build_condition_variables(extracted_variables: list) -> list:
    """Build condition_variables list for fetch_conditions_at_date().

    Resolves each extracted variable to its ticker and source using
    the same resolution chain as current_data_fetcher.

    Args:
        extracted_variables: List of dicts [{"normalized": str, "source": str}]

    Returns:
        List of dicts [{"normalized": str, "ticker": str, "source": str}]
    """
    from .current_data_fetcher import resolve_variable

    condition_vars = []
    for var in extracted_variables:
        normalized = var.get("normalized", "")
        if not normalized:
            continue
        resolved = resolve_variable(normalized)
        if resolved:
            condition_vars.append({
                "normalized": normalized,
                "ticker": resolved["series_id"],
                "source": resolved["source"]
            })

    return condition_vars


def characterize_regime(state: RiskImpactState) -> RiskImpactState:
    """Characterize current macro regime vs historical analogs (Gap 1)."""
    current_values = state.get("current_values", {})
    historical_analogs_text = state.get("historical_analogs_text", "")

    if not current_values or not historical_analogs_text:
        return state

    current_values_text = format_current_values_for_prompt(current_values)

    from .impact_analysis_prompts import REGIME_CHARACTERIZATION_PROMPT
    prompt = REGIME_CHARACTERIZATION_PROMPT.format(
        current_values_text=current_values_text,
        historical_analogs_text=historical_analogs_text,
    )

    tool = {
        "name": "output_regime",
        "description": "Output regime characterization",
        "input_schema": {
            "type": "object",
            "properties": {
                "regime_name": {"type": "string"},
                "closest_analog": {"type": "string"},
                "similarities": {"type": "array", "items": {"type": "string"}},
                "differences": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"}
            },
            "required": ["regime_name", "summary"]
        }
    }

    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "output_regime"}
        )

        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        regime = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_regime":
                regime = block.input
                break

        if regime is None:
            print("[Regime Characterization] No tool_use block found")
            return state

        text_lines = [f"**Current Regime**: {regime['regime_name']}"]
        if regime.get("closest_analog"):
            text_lines.append(f"**Closest Analog**: {regime['closest_analog']}")
        if regime.get("similarities"):
            text_lines.append("**Similarities**:")
            for s in regime["similarities"]:
                text_lines.append(f"  - {s}")
        if regime.get("differences"):
            text_lines.append("**Key Differences (this time is different)**:")
            for d in regime["differences"]:
                text_lines.append(f"  - {d}")
        text_lines.append(f"\n{regime.get('summary', '')}")

        state["regime_characterization_text"] = "\n".join(text_lines)
        print(f"[Regime Characterization] Regime: {regime['regime_name']}")

    except Exception as e:
        print(f"[Regime Characterization] Failed: {e}")

    return state


def enrich_with_historical_event(state: RiskImpactState) -> RiskImpactState:
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
    synthesis = state.get("synthesis", "")
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

    # Steps 2 & 3: Identify instruments and get date range in parallel
    # These are independent LLM/web calls, so we run them concurrently
    print("[Historical Event] Identifying instruments and determining date range (parallel)...")

    def _get_date_range_wrapper():
        if date_search_query:
            return get_date_range(event_description, date_search_query)
        else:
            from .historical_event_detector import _fallback_date_range
            return _fallback_date_range(event_description)

    asset_class = state.get("asset_class", "btc")

    with ThreadPoolExecutor(max_workers=2) as executor:
        instruments_future = executor.submit(
            identify_instruments,
            event_description=event_description,
            query=query,
            synthesis=synthesis,
            logic_chains=logic_chains,
            asset_class=asset_class
        )
        dates_future = executor.submit(_get_date_range_wrapper)
        instruments = instruments_future.result()
        date_range = dates_future.result()

    print(f"[Historical Event] Instruments: {[i.get('ticker') for i in instruments]}")

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

    # Multi-analog aggregation
    if config.ENABLE_MULTI_ANALOG:
        try:
            analogs = detect_historical_analogs(
                query, synthesis, logic_chains,
                max_analogs=config.MAX_HISTORICAL_ANALOGS,
                relevance_threshold=config.ANALOG_RELEVANCE_THRESHOLD
            )
            if analogs:
                current_values = state.get("current_values", {})
                target_asset_name = get_asset_config(asset_class)["name"]

                # Build condition_variables from extracted variables for Then vs Now
                condition_variables = _build_condition_variables(
                    state.get("extracted_variables", [])
                )

                enriched = fetch_multiple_analogs(
                    analogs, query, synthesis, logic_chains,
                    current_values, asset_class,
                    condition_variables=condition_variables
                )
                aggregated = aggregate_analogs(enriched, target_asset_name)
                state["historical_analogs"] = {
                    "enriched": enriched,
                    "aggregated": aggregated
                }
                state["historical_analogs_text"] = format_analogs_for_prompt(
                    aggregated,
                    enriched_analogs=enriched,
                    current_conditions=current_values
                )
        except Exception as e:
            print(f"[Historical Analogs] Multi-analog enrichment failed: {e}")

    return state


def _run_integrated_pipeline(state: RiskImpactState) -> RiskImpactState:
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

        synthesis = state.get("synthesis", "")
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

        # Set asset_price for the target asset class
        from .asset_configs import get_asset_config as _get_cfg
        _cfg = _get_cfg(state.get("asset_class", "btc"))
        _primary = _cfg["always_include_variable"]
        if _primary in current_values:
            state["asset_price"] = current_values[_primary]["value"]
        # Backwards compat
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
