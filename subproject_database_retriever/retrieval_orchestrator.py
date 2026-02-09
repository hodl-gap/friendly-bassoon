"""
Retrieval Orchestrator - Main Entry Point

This file contains ONLY:
1. Loading of States
2. Calling other function modules
3. Central router logic
4. NO business logic or implementation details

The retrieval layer now handles:
- Query processing & expansion
- Vector search
- Answer generation (logic chains + synthesis)
- Gap detection & filling (moved from BTC Intelligence)
- Returns enriched context with merged DB + web chains
"""

from langgraph.graph import StateGraph, END
from states import RetrieverState
from config import (
    MAX_ITERATIONS,
    ENABLE_GAP_DETECTION,
    ENABLE_GAP_FILLING,
    MAX_GAP_SEARCHES,
    MAX_ATTEMPTS_PER_GAP
)

# Import function modules
from query_processing import process_query
from vector_search import search_vectors
from answer_generation import generate_answer


def route_after_retrieval(state: RetrieverState) -> str:
    """Router: Decide whether to refine query or generate answer."""
    if state.get("needs_refinement", False) and state.get("iteration_count", 0) < MAX_ITERATIONS:
        return "refine"
    return "generate"


def detect_and_fill_gaps(state: RetrieverState) -> RetrieverState:
    """
    Step 4: Detect knowledge gaps and fill them.

    This step runs after answer generation to identify missing information
    and attempt to fill gaps via web search or data fetching.

    Moved from BTC Intelligence to make retrieval layer topic-agnostic.
    """
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
    gap_result = run_gap_detection(
        query=query,
        synthesis=synthesis,
        logic_chains=all_chains,
        topic_coverage=topic_coverage,
        enable_gap_filling=ENABLE_GAP_FILLING,
        max_searches=MAX_GAP_SEARCHES,
        max_attempts_per_gap=MAX_ATTEMPTS_PER_GAP
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


def build_graph() -> StateGraph:
    """Build the LangGraph workflow."""
    graph = StateGraph(RetrieverState)

    # Add nodes (function modules)
    graph.add_node("process_query", process_query)
    graph.add_node("search", search_vectors)
    graph.add_node("generate", generate_answer)
    graph.add_node("fill_gaps", detect_and_fill_gaps)

    # Define edges
    graph.set_entry_point("process_query")
    graph.add_edge("process_query", "search")
    graph.add_conditional_edges(
        "search",
        route_after_retrieval,
        {
            "refine": "process_query",
            "generate": "generate"
        }
    )
    # After generation, detect and fill gaps
    graph.add_edge("generate", "fill_gaps")
    graph.add_edge("fill_gaps", END)

    return graph.compile()


def run_retrieval(query: str) -> dict:
    """
    Main entry point for retrieval workflow.

    Args:
        query: User's question or search query

    Returns:
        Final state containing answer and retrieved context
    """
    graph = build_graph()

    initial_state = RetrieverState(
        query=query,
        iteration_count=0,
        needs_refinement=False
    )

    final_state = graph.invoke(initial_state)
    return final_state


if __name__ == "__main__":
    # Simple test
    test_query = "What does rising RDE indicate about liquidity conditions?"
    print(f"Query: {test_query}")
    print("-" * 50)
    result = run_retrieval(test_query)
    print(f"Answer: {result.get('answer', 'No answer generated')}")
