"""
Retrieval Orchestrator - Main Entry Point

This file contains ONLY:
1. Loading of States
2. Calling other function modules
3. Central router logic
4. NO business logic or implementation details

The retrieval layer handles:
- Agentic retrieval with coverage assessment (default)
- Lightweight retrieval for theme refresh (skip_gap_filling=True)
"""

from states import RetrieverState
from config import (
    ENABLE_GAP_DETECTION,
    ENABLE_GAP_FILLING,
    MAX_GAP_SEARCHES,
    MAX_ATTEMPTS_PER_GAP
)
from shared.snapshot import snapshot_state, ENABLE_SNAPSHOTS

# Import function modules
from query_processing import process_query
from vector_search import search_vectors
from answer_generation import generate_answer, regenerate_synthesis


def detect_and_fill_gaps(state: RetrieverState) -> RetrieverState:
    """
    Step 4: Detect knowledge gaps and fill them.

    This step runs after answer generation to identify missing information
    and attempt to fill gaps via web search or data fetching.

    Moved from BTC Intelligence to make retrieval layer topic-agnostic.
    """
    if state.get("skip_gap_filling", False):
        print("[retrieval] Gap filling skipped (skip_gap_filling=True)")
        return state

    if not ENABLE_GAP_DETECTION:
        print("[retrieval] Gap detection disabled")
        return state

    from knowledge_gap_detector import detect_and_fill_gaps as run_gap_detection

    query = state.get("query", "")
    synthesis = state.get("synthesis", "")
    topic_coverage = state.get("topic_coverage", {})

    # Extract logic chains from chunks for gap detection
    logic_chains = _extract_logic_chains_from_chunks(state.get("retrieved_chunks", []))

    # Also parse chains from answer text
    answer_chains = _parse_logic_chains_from_answer(state.get("answer", ""))
    all_chains = logic_chains + answer_chains

    print(f"[retrieval] Running gap detection with {len(all_chains)} chains...")

    # Run gap detection and filling
    image_path = state.get("image_path")
    gap_result = run_gap_detection(
        query=query,
        synthesis=synthesis,
        logic_chains=all_chains,
        topic_coverage=topic_coverage,
        enable_gap_filling=ENABLE_GAP_FILLING,
        max_searches=MAX_GAP_SEARCHES,
        max_attempts_per_gap=MAX_ATTEMPTS_PER_GAP,
        image_path=image_path
    )

    # Update state with gap results
    return {
        **state,
        "knowledge_gaps": gap_result.get("knowledge_gaps", {}),
        "gap_enrichment_text": gap_result.get("gap_enrichment_text", ""),
        "filled_gaps": gap_result.get("filled_gaps", []),
        "partially_filled_gaps": gap_result.get("partially_filled_gaps", []),
        "unfillable_gaps": gap_result.get("unfillable_gaps", []),
        "extracted_web_chains": gap_result.get("extracted_web_chains", []),
        "logic_chains": gap_result.get("merged_logic_chains", all_chains)
    }


def persist_learning(state: RetrieverState) -> RetrieverState:
    """
    Step 6: Persist verified web chains to Pinecone for future retrieval.

    Also records variables in the frequency tracker.
    """
    web_chains = state.get("extracted_web_chains", [])
    if not web_chains:
        return state

    try:
        from web_chain_persistence import persist_web_chains
        count = persist_web_chains(web_chains, state.get("query", ""))
        print(f"[retrieval] Persisted {count} web chains to Pinecone")
    except Exception as e:
        print(f"[retrieval] Web chain persistence failed: {e}")

    # Update variable frequency tracker with web chains
    try:
        from pathlib import Path
        from shared.variable_frequency import VariableFrequencyTracker
        freq_path = Path(__file__).parent.parent / "subproject_risk_intelligence" / "data" / "variable_frequency.json"
        tracker = VariableFrequencyTracker.load(freq_path)
        for chain in web_chains:
            # Convert flat web chain to structure expected by record_variables
            tracker.record_variables({
                "logic_chain": {
                    "steps": [{
                        "cause_normalized": chain.get("cause", "").lower().replace(" ", "_")[:50],
                        "effect_normalized": chain.get("effect", "").lower().replace(" ", "_")[:50],
                    }]
                },
                "source_attribution": chain.get("source_name", "web"),
            })
        tracker.save(freq_path)
    except Exception as e:
        print(f"[retrieval] Variable frequency update failed: {e}")

    return state


def conditional_resynthesis(state: RetrieverState) -> RetrieverState:
    """
    Step 5: Conditionally re-synthesize after gap filling.

    Only fires when significant new information was discovered during gap filling
    (web_chains >= 3 or filled_gaps >= 2). Integrates web chains and gap enrichment
    into an updated synthesis using Sonnet.
    """
    web_chains = state.get("extracted_web_chains", [])
    filled_gaps = state.get("filled_gaps", [])

    if len(web_chains) < 3 and len(filled_gaps) < 2:
        print(f"[retrieval] Skipping re-synthesis (web_chains={len(web_chains)}, filled_gaps={len(filled_gaps)})")
        return state

    query = state.get("query", "")
    original_synthesis = state.get("synthesis", "")
    gap_enrichment = state.get("gap_enrichment_text", "")

    if not original_synthesis:
        print("[retrieval] No original synthesis to re-synthesize")
        return state

    print(f"[retrieval] Re-synthesizing with {len(web_chains)} web chains and {len(filled_gaps)} filled gaps...")

    new_synthesis = regenerate_synthesis(
        query=query,
        original_synthesis=original_synthesis,
        web_chains=web_chains,
        gap_enrichment=gap_enrichment
    )

    return {**state, "synthesis": new_synthesis}


def _extract_logic_chains_from_chunks(chunks: list) -> list:
    """Extract logic_chains from retrieved chunks' metadata."""
    import json

    all_chains = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        extracted = metadata.get("extracted_data")

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
                chain_with_source = dict(chain)
                chain_with_source["source"] = extracted.get("source", metadata.get("source", "Unknown"))
                all_chains.append(chain_with_source)

    return all_chains


def _parse_logic_chains_from_answer(answer_text: str) -> list:
    """Parse logic chains from Stage 1 answer text."""
    import re

    chains = []
    chain_blocks = re.split(r'\*\*CHAIN:\*\*', answer_text)

    for block in chain_blocks[1:]:
        chain_dict = {}

        chain_match = re.match(r'\s*(.+?)(?:\n|$)', block)
        if chain_match:
            chain_line = chain_match.group(1).strip()
            chain_dict["chain_text"] = chain_line

            normalized_vars = re.findall(r'\[([^\]]+)\]', chain_line)
            chain_dict["normalized_variables"] = normalized_vars

            steps = []
            step_parts = re.split(r'\s*(?:→|->|—>)\s*', chain_line)
            for i, part in enumerate(step_parts[:-1]):
                cause_match = re.match(r'([^\[]+)', part.strip())
                effect_match = re.match(r'([^\[]+)', step_parts[i+1].strip())
                if cause_match and effect_match:
                    steps.append({
                        "cause": cause_match.group(1).strip(),
                        "effect": effect_match.group(1).strip()
                    })
            chain_dict["steps"] = steps

        mechanism_match = re.search(r'\*\*MECHANISM:\*\*\s*(.+?)(?=\*\*|$)', block, re.DOTALL)
        if mechanism_match:
            chain_dict["mechanism"] = mechanism_match.group(1).strip()

        source_match = re.search(r'\*\*SOURCE:\*\*\s*(.+?)(?=\*\*|\n|$)', block)
        if source_match:
            chain_dict["source"] = source_match.group(1).strip()

        if chain_dict.get("steps") or chain_dict.get("chain_text"):
            chains.append(chain_dict)

    return chains


def _run_lightweight_retrieval(query: str) -> dict:
    """Minimal retrieval for theme refresh: expand -> search -> synthesize. No gaps, no persistence."""
    from vector_search import EXCLUDE_WEB_CHAINS_FILTER

    state = RetrieverState(
        query=query,
        iteration_count=0,
        needs_refinement=False,
        pinecone_filter=EXCLUDE_WEB_CHAINS_FILTER,
        skip_gap_filling=True,
    )
    state = process_query(state)
    state = search_vectors(state)
    state = generate_answer(state)
    return state


def run_retrieval(query: str, image_path: str = None, skip_gap_filling: bool = False) -> dict:
    """
    Main entry point for retrieval workflow.

    Args:
        query: User's question or search query
        image_path: Optional path to indicator chart image for vision-based extraction
        skip_gap_filling: If True, use lightweight retrieval (used by theme refresh)

    Returns:
        Final state containing answer and retrieved context
    """
    if skip_gap_filling:
        return _run_lightweight_retrieval(query)

    from retrieval_agent import run_retrieval_agent
    return run_retrieval_agent(query, image_path=image_path)


if __name__ == "__main__":
    # Simple test
    test_query = "What does rising RDE indicate about liquidity conditions?"
    print(f"Query: {test_query}")
    print("-" * 50)
    result = run_retrieval(test_query)
    print(f"Answer: {result.get('answer', 'No answer generated')}")
