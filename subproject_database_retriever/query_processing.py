"""
Query Processing Module

Processes, expands, and refines user queries for better retrieval.
"""

import sys
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_haiku
from states import RetrieverState
from query_processing_prompts import QUERY_EXPANSION_PROMPT, QUERY_TYPE_PROMPT


def process_query(state: RetrieverState) -> RetrieverState:
    """
    Process and optionally expand user query.

    Input: query
    Output: processed_query, query_type, query_variations
    """
    query = state.get("query", "")
    iteration = state.get("iteration_count", 0)

    print(f"[query_processing] Processing query (iteration {iteration}): {query[:100]}...")

    # First iteration: classify and expand
    if iteration == 0:
        # Classify query type
        query_type = classify_query(query)

        # Expand query for better recall (layered approach)
        processed_query, variations, layered_results = expand_query(query)

        print(f"[query_processing] Type: {query_type}, Variations: {len(variations)}")

        return {
            **state,
            "processed_query": processed_query,
            "query_type": query_type,
            "query_variations": variations,
            "query_dimensions": layered_results  # Full debug info with dimensions/reasoning
        }

    # Subsequent iterations: refine based on previous results
    else:
        refined_query = refine_query(query, state.get("retrieved_chunks", []))
        print(f"[query_processing] Refined query: {refined_query[:100]}...")

        return {
            **state,
            "processed_query": refined_query
        }


def classify_query(query: str) -> str:
    """Classify query as research_question or data_lookup."""
    messages = [{"role": "user", "content": QUERY_TYPE_PROMPT.format(query=query)}]
    response = call_claude_haiku(messages, temperature=0.0, max_tokens=50)

    print(f"[query_processing] Classification response: {response}")

    if "data_lookup" in response.lower():
        return "data_lookup"
    return "research_question"


def expand_query(query: str) -> tuple:
    """Generate query variations using layered approach."""
    messages = [{"role": "user", "content": QUERY_EXPANSION_PROMPT.format(query=query)}]
    response = call_claude_haiku(messages, temperature=0.3, max_tokens=1500)

    print(f"[query_processing] Expansion response:\n{response}")

    # Parse structured output
    queries = []
    layered_results = []  # Full structured data for debugging

    current_layer = None
    current_reasoning = None

    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Handle variations: "DIMENSION:", "**DIMENSION:", etc.
        if "DIMENSION:" in line.upper():
            # Remove markdown formatting and extract dimension name
            current_layer = line.split(":", 1)[-1].strip().strip("*").strip()
        elif line.upper().startswith("REASONING:") or "REASONING:" in line:
            current_reasoning = line.split(":", 1)[-1].strip().strip("*").strip()
        elif line.upper().startswith("QUERY:") or "QUERY:" in line:
            query_text = line.split(":", 1)[-1].strip().strip("`").strip("*").strip()
            if query_text:
                queries.append(query_text)
                layered_results.append({
                    "dimension": current_layer,
                    "reasoning": current_reasoning,
                    "query": query_text
                })
                current_layer = None
                current_reasoning = None

    # Debug print the layered breakdown
    print(f"\n[query_processing] Parsed {len(queries)} dimension queries:")
    for item in layered_results:
        print(f"  [{item['dimension']}] {item['query']}")
        print(f"    -> {item['reasoning']}")

    return query, queries, layered_results


def refine_query(original_query: str, previous_chunks: list) -> str:
    """Refine query based on previous retrieval results."""
    # Simple refinement: just return original for now
    # TODO: Implement smarter refinement based on retrieved context
    return original_query
