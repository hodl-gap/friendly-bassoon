"""
Retrieval Orchestrator - Main Entry Point

This file contains ONLY:
1. Loading of States
2. Calling other function modules
3. Central router logic
4. NO business logic or implementation details
"""

from langgraph.graph import StateGraph, END
from states import RetrieverState
from config import MAX_ITERATIONS

# Import function modules
from query_processing import process_query
from vector_search import search_vectors
from answer_generation import generate_answer


def route_after_retrieval(state: RetrieverState) -> str:
    """Router: Decide whether to refine query or generate answer."""
    if state.get("needs_refinement", False) and state.get("iteration_count", 0) < MAX_ITERATIONS:
        return "refine"
    return "generate"


def build_graph() -> StateGraph:
    """Build the LangGraph workflow."""
    graph = StateGraph(RetrieverState)

    # Add nodes (function modules)
    graph.add_node("process_query", process_query)
    graph.add_node("search", search_vectors)
    graph.add_node("generate", generate_answer)

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
    graph.add_edge("generate", END)

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
