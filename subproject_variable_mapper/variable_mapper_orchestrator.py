"""
Variable Mapper Orchestrator

This file contains ONLY:
1. Loading of States
2. Calling other function modules
3. Central router logic
4. NO business logic or implementation details

Optimization: When USE_COMBINED_EXTRACTION=True, Step 3 is skipped because
Step 1 already extracts both explicit and implicit variables.
"""

import json
from langgraph.graph import StateGraph, END
from states import VariableMapperState
from config import SAMPLE_INPUT_FILE, USE_COMBINED_EXTRACTION

# Import function modules
from variable_extraction import extract_variables
from normalization import normalize_variables
from missing_variable_detection import detect_missing_variables
from data_id_mapping import map_to_data_ids


def should_skip_step3(state: VariableMapperState) -> str:
    """
    Router: decide whether to skip Step 3 (missing_variable_detection).

    If combined extraction was used, Step 3 is redundant.
    """
    if state.get("skip_step3", False):
        print("[orchestrator] Skipping Step 3 - combined extraction already parsed chains")
        return "map_data_ids"
    else:
        return "detect_missing"


def build_graph() -> StateGraph:
    """Build the LangGraph workflow with conditional Step 3."""
    graph = StateGraph(VariableMapperState)

    # Add nodes (function modules)
    graph.add_node("extract_variables", extract_variables)
    graph.add_node("normalize_variables", normalize_variables)
    graph.add_node("detect_missing", detect_missing_variables)
    graph.add_node("map_data_ids", map_to_data_ids)

    # Wire edges with conditional routing
    graph.set_entry_point("extract_variables")
    graph.add_edge("extract_variables", "normalize_variables")

    # Conditional edge: skip Step 3 if combined extraction was used
    graph.add_conditional_edges(
        "normalize_variables",
        should_skip_step3,
        {
            "detect_missing": "detect_missing",
            "map_data_ids": "map_data_ids"
        }
    )

    graph.add_edge("detect_missing", "map_data_ids")
    graph.add_edge("map_data_ids", END)

    return graph.compile()


def run_variable_mapper(synthesis_text: str, data_temporal_context: dict = None) -> dict:
    """
    Main entry point for variable mapping.

    Args:
        synthesis_text: Raw synthesis text from database_retriever
        data_temporal_context: Optional temporal context from retriever
            (e.g., {"data_years": ["2025", "2026"], "forward_looking_count": 3})

    Returns:
        Final state with extracted/mapped variables
    """
    print(f"[orchestrator] Starting variable mapping...")
    print(f"[orchestrator] Input length: {len(synthesis_text)} chars")
    if data_temporal_context:
        print(f"[orchestrator] Temporal context: {data_temporal_context.get('data_years', 'unknown')}")

    graph = build_graph()
    initial_state = VariableMapperState(
        synthesis_input=synthesis_text,
        data_temporal_context=data_temporal_context or {}
    )
    final_state = graph.invoke(initial_state)

    print(f"[orchestrator] Variable mapping complete")
    return final_state


# CLI entry point for testing
if __name__ == "__main__":
    # Load sample input for testing
    print(f"[orchestrator] Loading sample input from: {SAMPLE_INPUT_FILE}")

    with open(SAMPLE_INPUT_FILE, "r", encoding="utf-8") as f:
        sample_text = f.read()

    print(f"[orchestrator] Sample input loaded: {len(sample_text)} chars")
    print("-" * 50)

    result = run_variable_mapper(sample_text)

    print("-" * 50)
    print("[orchestrator] Final Result Summary:")
    print(f"  Extracted variables: {len(result.get('extracted_variables', []))}")
    print(f"  Normalized variables: {len(result.get('normalized_variables', []))}")
    print(f"  Missing variables: {len(result.get('missing_variables', []))}")
    print(f"  Unmapped variables: {len(result.get('unmapped_variables', []))}")
    print(f"  Chain dependencies: {len(result.get('chain_dependencies', []))}")

    # Print final output
    print("\n" + "=" * 50)
    print("FINAL OUTPUT JSON:")
    print("=" * 50)
    final_output = result.get('final_output', {})
    print(json.dumps(final_output, indent=2, default=str))
