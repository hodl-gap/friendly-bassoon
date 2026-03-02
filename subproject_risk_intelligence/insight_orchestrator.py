"""
Insight Orchestrator - Main Entry Point

query → retrieve → agentic data grounding → agentic historical context
     → synthesis with self-check → output

Architecture: Risk Intelligence receives ENRICHED context from retrieval layer.
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
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))

from .states import RiskImpactState
from .current_data_fetcher import format_current_values_for_prompt
from shared.snapshot import snapshot_state, start_run as _start_run, ENABLE_SNAPSHOTS
from .relationship_store import (
    load_chains,
    store_chains,
    load_regime_state,
    update_regime_from_analysis,
)
from .regime_characterization import characterize_regime
from .asset_configs import get_asset_config
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

    # Preserve EDF knowledge tree for downstream routing directives (Phase 2/3)
    edf_tree = result.get("_edf_knowledge_tree")
    if edf_tree:
        state["_edf_knowledge_tree"] = edf_tree

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
            "outlook": insight.get("outlook", ""),
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

    outlook = insight.get("outlook", "")
    if outlook:
        lines.append("")
        lines.append("OUTLOOK (Forward Projections):")
        lines.append(outlook)

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

    # Condensed summary
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"CONDENSED SUMMARY -- {asset_name.upper()}")
    lines.append("=" * 60)
    lines.append("")
    for i, track in enumerate(tracks_sorted, 1):
        title = track.get("title", f"Track {i}")
        confidence = track.get("confidence", 0)
        mechanism = track.get("causal_mechanism", "N/A")
        evidence = track.get("historical_evidence", {})
        implications = track.get("asset_implications", [])

        # Line 1: title + confidence → mechanism
        lines.append(f"TRACK {i} ({confidence*100:.0f}%): {title}")

        # Line 2: mechanism (truncated if long)
        mech_str = f"  {mechanism}"
        if len(mech_str) > 120:
            mech_str = mech_str[:117] + "..."
        lines.append(mech_str)

        # Line 3: precedent + asset implications
        parts = []
        precedent_count = evidence.get("precedent_count")
        success_rate = evidence.get("success_rate")
        if precedent_count and success_rate is not None:
            parts.append(f"{precedent_count} precedents ({success_rate*100:.0f}% success)")
        imp_strs = []
        for imp in implications[:3]:
            s = f"{imp.get('asset', '?')}: {imp.get('direction', '?')}"
            mag = imp.get("magnitude_range", "")
            if mag:
                s += f" ({mag})"
            imp_strs.append(s)
        if imp_strs:
            parts.append("; ".join(imp_strs))
        if parts:
            lines.append(f"  {'. '.join(parts)}.")
        lines.append("")

    if synthesis:
        # One-sentence bottom line from synthesis (first sentence or truncated)
        synth_clean = synthesis.replace("\n", " ").strip()
        first_sentence_end = synth_clean.find(". ")
        if first_sentence_end > 0 and first_sentence_end < 200:
            bottom = synth_clean[:first_sentence_end + 1]
        elif len(synth_clean) > 200:
            bottom = synth_clean[:197] + "..."
        else:
            bottom = synth_clean
        lines.append(f"BOTTOM LINE: {bottom}")

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
        # Ensure data_collection's own modules (states.py) resolve before other subprojects.
        # data_collection uses bare `from states import DataCollectionState` which collides
        # with database_retriever's states.py if that's earlier on sys.path.
        dc_path = str(config.DATA_COLLECTION_DIR)
        saved_states = sys.modules.pop("states", None)
        if dc_path not in sys.path:
            sys.path.insert(0, dc_path)
        else:
            sys.path.remove(dc_path)
            sys.path.insert(0, dc_path)

        from subproject_data_collection.data_collection_orchestrator import run_claim_validation

        # Restore previous states module so other subprojects aren't affected
        if saved_states is not None:
            sys.modules["states"] = saved_states

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
        if saved_states is not None:
            sys.modules["states"] = saved_states
    except Exception as e:
        print(f"[Claim Validation] Validation failed: {e}")
        state["claim_validation_results"] = []
        if saved_states is not None:
            sys.modules["states"] = saved_states

    return state


def prepare_shared_context(
    query: str,
    skip_data_fetch: bool = False,
    image_path: str = None,
    asset_class: str = "btc"
) -> RiskImpactState:
    """
    Shared preparation: retrieval + agentic data grounding + agentic historical context.

    This is the expensive part (~$0.30, ~250s) that runs ONCE
    regardless of how many asset classes we analyze.

    Args:
        query: User's question
        skip_data_fetch: If True, skip fetching current data
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

    # Step 2-5: Agentic data grounding (variable extraction, data fetching, claim validation, pattern validation)
    if not skip_data_fetch:
        from .data_grounding_agent import run_data_grounding_agent
        state = run_data_grounding_agent(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state("data_grounding_agent", state, "out")

    # Step 6: Agentic historical context (analog detection, data fetch, aggregation, regime characterization)
    if not skip_data_fetch:
        from .historical_context_agent import run_historical_context_agent
        state = run_historical_context_agent(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state("historical_context_agent", state, "out")

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
    # Skip if Phase 3 already characterized the regime (avoid double Haiku call)
    if config.ENABLE_REGIME_CHARACTERIZATION and not state.get("regime_characterization_text"):
        state = characterize_regime(state)
        if ENABLE_SNAPSHOTS:
            snapshot_state(f"characterize_regime_{asset_class}", state, "out")

    # Run impact analysis with synthesis self-check
    from .synthesis_phase import run_synthesis_phase
    state = run_synthesis_phase(state, asset_class)
    if ENABLE_SNAPSHOTS:
        snapshot_state(f"analyze_impact_{asset_class}", state, "out")

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
    image_path: str = None,
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
        image_path: Optional path to indicator chart image

    Returns:
        Dict mapping asset_class -> result state
    """
    if assets is None:
        assets = ["equity"]

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
        image_path=image_path,
        asset_class=assets[0]
    )
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
        output = format_insight(result, as_json=output_json, asset_class=asset)
        print("\n" + output)

    return results


def run_impact_analysis(
    query: str,
    asset_class: str = "equity",
    output_json: bool = False,
    skip_data_fetch: bool = False,
    skip_chain_store: bool = False,
    image_path: str = None,
) -> Dict[str, Any]:
    """
    Single-asset entry point.

    Args:
        query: User's question about macro event impact
        asset_class: Asset class to analyze (default: "equity")
        output_json: If True, return JSON-formatted output
        skip_data_fetch: If True, skip fetching current data (Phase 1 mode)
        skip_chain_store: If True, skip loading/storing logic chains (Phase 3)
        image_path: Optional path to indicator chart image for vision-based extraction

    Returns:
        Final state dict with analysis results
    """
    results = run_multi_asset_analysis(
        query,
        assets=[asset_class],
        output_json=output_json,
        skip_data_fetch=skip_data_fetch,
        skip_chain_store=skip_chain_store,
        image_path=image_path,
    )
    return results[asset_class]


# Backward-compatible alias
run_btc_impact_analysis = run_impact_analysis


if __name__ == "__main__":
    # Quick test
    test_query = "What is the impact of TGA drawdown on BTC?"
    run_btc_impact_analysis(test_query)
