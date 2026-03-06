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
    """Format the final output for display — routes by output mode."""
    insight = state.get("insight_output", {})
    output_mode = insight.get("output_mode", "legacy")
    asset_name = get_asset_config(asset_class)["name"]

    if as_json:
        output = {
            "asset_class": asset_class,
            "output_mode": output_mode,
            "insight_output": insight,
            "direction": state.get("direction", "NEUTRAL"),
            "confidence": state.get("confidence", {}),
            "predictions": state.get("predictions", []),
        }
        return json.dumps(output, indent=2, default=str)

    if output_mode == "retrospective":
        return _format_causal_decomposition(insight, asset_name)
    elif output_mode == "prospective":
        return _format_scenario_analysis(insight, state.get("scenario_skeleton", {}), asset_name)
    else:
        return _format_legacy_insight(insight, state, asset_name)


def _format_causal_decomposition(insight: dict, asset_name: str) -> str:
    """Format retrospective causal decomposition."""
    trigger = insight.get("trigger_event", {})
    tracks = insight.get("causal_tracks", [])
    synthesis = insight.get("cross_track_synthesis", "")
    forward = insight.get("residual_forward_view", "")
    gaps = insight.get("key_data_gaps", [])

    lines = [
        "=" * 64,
        f"CAUSAL DECOMPOSITION -- {asset_name.upper()}",
        "=" * 64,
    ]

    trigger_desc = trigger.get("description", "Unknown")
    trigger_date = trigger.get("date", "")
    lines.append(f"TRIGGER: {trigger_desc}" + (f" ({trigger_date})" if trigger_date else ""))
    lines.append("")

    for i, track in enumerate(tracks, 1):
        title = track.get("title", f"Track {i}")
        confidence = track.get("confidence", 0)
        mechanism = track.get("mechanism", "N/A")
        evidence = track.get("evidence_summary", "")

        lines.append(f"TRACK {i}: {title} ({confidence*100:.0f}%)")
        lines.append(f"  {mechanism}")
        if evidence:
            lines.append(f"  Evidence: {evidence}")

        qdata = track.get("quantitative_data", [])
        if qdata:
            data_parts = [f"{d.get('metric', '?')}: {d.get('value', '?')}" for d in qdata]
            lines.append(f"  Data: {' | '.join(data_parts)}")

        lines.append("")

    if synthesis:
        lines.append(f"SYNTHESIS: {synthesis}")
        lines.append("")

    if forward:
        lines.append(f"FORWARD VIEW: {forward}")
        lines.append("")

    if gaps:
        lines.append(f"DATA GAPS: {' | '.join(gaps)}")
        lines.append("")

    lines.append("=" * 64)
    return "\n".join(lines)


def _format_scenario_analysis(insight: dict, skeleton: dict, asset_name: str) -> str:
    """Format prospective scenario analysis."""
    situation = insight.get("current_situation", "")
    scenarios = insight.get("scenarios", [])
    dashboard = insight.get("monitoring_dashboard", [])
    synthesis = insight.get("synthesis", "")
    base_rates = skeleton.get("base_rates", {})

    lines = [
        "=" * 64,
        f"SCENARIO ANALYSIS -- {asset_name.upper()}",
        "=" * 64,
    ]

    if situation:
        lines.append(situation)
        lines.append("")

    # Base rates
    total = scenarios[0].get("total_episodes", 0) if scenarios and scenarios[0].get("total_episodes") else 0
    if total:
        dir_pct = base_rates.get("direction_positive_pct")
        mag_med = base_rates.get("magnitude_median")
        mag_range = base_rates.get("magnitude_range")
        br_parts = [f"{total} episodes"]
        if dir_pct is not None:
            br_parts.append(f"{dir_pct}% positive")
        if mag_med is not None:
            br_parts.append(f"median {mag_med:+.1f}%")
        if mag_range:
            br_parts.append(f"range [{mag_range[0]:+.1f}% to {mag_range[1]:+.1f}%]")
        lines.append(f"BASE RATES: {' | '.join(br_parts)}")
    else:
        lines.append("BASE RATES: No historical episodes found")
    lines.append("")

    for i, scenario in enumerate(scenarios, 1):
        title = scenario.get("title", f"Scenario {i}")
        ac = scenario.get("analog_count")
        te = scenario.get("total_episodes")
        analog_str = f" ({ac}/{te} analogs)" if ac is not None and te is not None else ""
        lines.append(f"SCENARIO {i}: {title}{analog_str}")
        lines.append(f"  Condition: {scenario.get('condition', 'N/A')}")
        lines.append(f"  Mechanism: {scenario.get('mechanism', 'N/A')}")
        basis = scenario.get("analog_basis", "")
        if basis:
            lines.append(f"  Basis: {basis}")

        preds = scenario.get("predictions", [])
        if preds:
            lines.append("  Predictions:")
            for pred in preds:
                var = pred.get("variable", "?")
                direction = pred.get("direction", "?")
                days = pred.get("timeframe_days", "?")
                mag_lo = pred.get("magnitude_low")
                mag_hi = pred.get("magnitude_high")
                mag_str = ""
                if mag_lo is not None and mag_hi is not None:
                    mag_str = f" {mag_lo}% to {mag_hi}%"
                lines.append(f"    {var}: {direction}{mag_str} ({days}d)")

        falsification = scenario.get("falsification", "")
        if falsification:
            lines.append(f"  Falsification: {falsification}")
        lines.append("")

    if dashboard:
        lines.append("MONITORING DASHBOARD:")
        for m in dashboard:
            var = m.get("variable", "?")
            cv = m.get("current_value")
            s1 = m.get("scenario_1_threshold", "")
            s2 = m.get("scenario_2_threshold", "")
            parts = [var]
            if cv is not None:
                parts.append(f"current: {cv}")
            if s1:
                parts.append(f"S1: {s1}")
            if s2:
                parts.append(f"S2: {s2}")
            lines.append(f"  {' | '.join(parts)}")
        lines.append("")

    if synthesis:
        lines.append(f"BOTTOM LINE: {synthesis}")
        lines.append("")

    lines.append("=" * 64)
    return "\n".join(lines)


def _format_legacy_insight(insight: dict, state: dict, asset_name: str) -> str:
    """Format legacy track-based insight (backward compat)."""
    tracks = insight.get("tracks", [])
    synthesis = insight.get("synthesis", "")

    lines = [
        "=" * 60,
        f"INSIGHT REPORT -- {asset_name.upper()}",
        "=" * 60,
    ]

    for i, track in enumerate(tracks, 1):
        lines.append("")
        lines.append(f"TRACK {i}: {track.get('title', f'Track {i}')}")
        lines.append(f"  Confidence: {track.get('confidence', 0)*100:.0f}%")
        lines.append(f"  Mechanism: {track.get('causal_mechanism', 'N/A')}")
        lines.append("-" * 40)

    if synthesis:
        lines.append("")
        lines.append(f"SYNTHESIS: {synthesis}")

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

    # Build scenario skeleton from Phase 3 data (mechanical, no LLM)
    from .scenario_builder import build_scenario_skeleton
    state["scenario_skeleton"] = build_scenario_skeleton(state)
    skeleton = state["scenario_skeleton"]
    scenario_count = len(skeleton.get("scenarios", []))
    total_episodes = skeleton.get("scenarios", [{}])[0].get("total_episodes", 0) if skeleton.get("scenarios") else 0
    print(f"[Scenario Builder] Built skeleton: {scenario_count} scenarios from {total_episodes} episodes")

    # Run impact analysis with synthesis self-check
    from .synthesis_phase import run_synthesis_phase
    state = run_synthesis_phase(state, asset_class)
    if ENABLE_SNAPSHOTS:
        snapshot_state(f"analyze_impact_{asset_class}", state, "out")

    # Store predictions from prospective output
    insight_output = state.get("insight_output", {})
    if insight_output.get("output_mode") == "prospective":
        from .prediction_store import store_predictions
        import hashlib
        run_id = hashlib.md5(f"{state.get('query', '')}_{asset_class}".encode()).hexdigest()[:8]
        predictions = store_predictions(insight_output, state.get("query", ""), run_id)
        state["predictions"] = predictions

    # Chain storage deferred — new output format needs separate chain extraction update
    # TODO: Update store_chains() to parse new retrospective/prospective output schemas
    # (see CLAUDE.md TODOs)

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
