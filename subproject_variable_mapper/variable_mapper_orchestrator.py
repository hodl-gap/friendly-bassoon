"""
Variable Mapper Orchestrator

This file contains ONLY:
1. Loading of States
2. Calling other function modules
3. Central router logic
4. NO business logic or implementation details
"""

from langgraph.graph import StateGraph, END
from states import VariableMapperState
from config import EXTRACTION_MODEL, SAMPLE_INPUT_FILE

# Import function modules (uncomment as implemented)
from variable_extraction import extract_variables
# from normalization import normalize_variables
# from missing_variable_detector import detect_missing_variables
# from data_id_mapping import map_to_data_ids
# from query_builder import build_query_output


def build_graph() -> StateGraph:
    """Build the LangGraph workflow."""
    graph = StateGraph(VariableMapperState)

    # Add nodes (function modules)
    graph.add_node("extract_variables", extract_variables)
    # graph.add_node("normalize_variables", normalize_variables)
    # graph.add_node("detect_missing", detect_missing_variables)
    # graph.add_node("map_data_ids", map_to_data_ids)
    # graph.add_node("build_output", build_query_output)

    # Define edges - Step 1 only for now
    graph.set_entry_point("extract_variables")
    graph.add_edge("extract_variables", END)

    # Full workflow (uncomment as modules are implemented):
    # graph.set_entry_point("extract_variables")
    # graph.add_edge("extract_variables", "normalize_variables")
    # graph.add_edge("normalize_variables", "detect_missing")
    # graph.add_edge("detect_missing", "map_data_ids")
    # graph.add_edge("map_data_ids", "build_output")
    # graph.add_edge("build_output", END)

    return graph.compile()


def run_variable_mapper(synthesis_text: str) -> dict:
    """
    Main entry point for variable mapping.

    Args:
        synthesis_text: Raw synthesis text from database_retriever

    Returns:
        Final state with extracted/mapped variables
    """
    print(f"[orchestrator] Starting variable mapping...")
    print(f"[orchestrator] Input length: {len(synthesis_text)} chars")

    graph = build_graph()
    initial_state = VariableMapperState(synthesis_input=synthesis_text)
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
    print("[orchestrator] Final Result:")
    print(f"  Extracted variables: {len(result.get('extracted_variables', []))}")

    # Print extracted variables
    for var in result.get('extracted_variables', []):
        print(f"    - {var}")
