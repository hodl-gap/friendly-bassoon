"""
Data Collection Orchestrator

This file contains ONLY:
1. Loading of States
2. Calling other function modules
3. Central router logic
4. NO business logic or implementation details

Two workflow modes:
- claim_validation: Parse claims → Fetch data → Validate statistically
- news_collection: Collect news → Filter relevant → Analyze actionability
"""

import json
import argparse
from datetime import datetime
from langgraph.graph import StateGraph, END
from states import DataCollectionState
from config import (
    ENABLE_CLAIM_VALIDATION,
    ENABLE_NEWS_COLLECTION,
    DEFAULT_NEWS_SOURCES,
    DEFAULT_TIME_WINDOW_DAYS
)

# Import function modules - Claim Validation Path (Phase 3)
from claim_parsing import parse_claims
from data_fetching import resolve_data_ids, fetch_historical_data
from validation_logic import validate_claims
from output_formatter import format_output

# Import function modules - News Collection Path (Phase 4)
from news_collection import collect_news
from news_analysis import filter_relevant_articles, analyze_news_actionability, generate_retriever_queries


# =============================================================================
# ROUTER FUNCTIONS
# =============================================================================

def route_by_mode(state: DataCollectionState) -> str:
    """Router: decide workflow based on mode."""
    mode = state.get("mode", "claim_validation")

    print(f"[orchestrator] Routing by mode: {mode}")

    if mode == "news_collection":
        if not ENABLE_NEWS_COLLECTION:
            print("[orchestrator] News collection disabled, skipping to output")
            return "format_output"
        return "collect_news"
    elif mode == "claim_validation":
        if not ENABLE_CLAIM_VALIDATION:
            print("[orchestrator] Claim validation disabled, skipping to output")
            return "format_output"
        return "parse_claims"
    else:
        print(f"[orchestrator] Unknown mode: {mode}, defaulting to claim_validation")
        return "parse_claims"


def should_analyze_news(state: DataCollectionState) -> str:
    """Router: decide if we should analyze news (skip if no relevant articles)."""
    filtered = state.get("filtered_articles", [])

    if not filtered:
        print("[orchestrator] No relevant articles found, skipping analysis")
        state["skip_news_analysis"] = True
        return "format_output"

    return "analyze_news"


def should_generate_queries(state: DataCollectionState) -> str:
    """Router: decide if we should generate retriever queries."""
    analyzed = state.get("analyzed_news", [])
    actionable = [a for a in analyzed if a.get("confidence", 0) >= 0.6]

    if not actionable:
        print("[orchestrator] No actionable insights, skipping query generation")
        return "format_output"

    return "generate_queries"


# =============================================================================
# GRAPH BUILDER
# =============================================================================

def build_graph() -> StateGraph:
    """Build the LangGraph workflow with conditional routing."""
    graph = StateGraph(DataCollectionState)

    # Add all nodes
    # Claim validation path
    graph.add_node("parse_claims", parse_claims)
    graph.add_node("resolve_data_ids", resolve_data_ids)
    graph.add_node("fetch_data", fetch_historical_data)
    graph.add_node("validate_claims", validate_claims)

    # News collection path
    graph.add_node("collect_news", collect_news)
    graph.add_node("filter_relevant", filter_relevant_articles)
    graph.add_node("analyze_news", analyze_news_actionability)
    graph.add_node("generate_queries", generate_retriever_queries)

    # Shared
    graph.add_node("format_output", format_output)

    # Entry point with mode routing
    graph.set_conditional_entry_point(
        route_by_mode,
        {
            "collect_news": "collect_news",
            "parse_claims": "parse_claims",
            "format_output": "format_output"
        }
    )

    # Claim validation path edges
    graph.add_edge("parse_claims", "resolve_data_ids")
    graph.add_edge("resolve_data_ids", "fetch_data")
    graph.add_edge("fetch_data", "validate_claims")
    graph.add_edge("validate_claims", "format_output")

    # News collection path edges
    graph.add_edge("collect_news", "filter_relevant")
    graph.add_conditional_edges(
        "filter_relevant",
        should_analyze_news,
        {
            "analyze_news": "analyze_news",
            "format_output": "format_output"
        }
    )
    graph.add_conditional_edges(
        "analyze_news",
        should_generate_queries,
        {
            "generate_queries": "generate_queries",
            "format_output": "format_output"
        }
    )
    graph.add_edge("generate_queries", "format_output")

    # Terminal
    graph.add_edge("format_output", END)

    return graph.compile()


# =============================================================================
# MAIN ENTRY POINTS
# =============================================================================

def run_claim_validation(
    synthesis_text: str,
    variable_mappings: dict = None
) -> dict:
    """
    Run claim validation workflow.

    Args:
        synthesis_text: Raw synthesis text from database_retriever
        variable_mappings: Optional pre-resolved data ID mappings

    Returns:
        Final state with validation results
    """
    print(f"[orchestrator] Starting claim validation...")
    print(f"[orchestrator] Input length: {len(synthesis_text)} chars")

    graph = build_graph()
    initial_state = DataCollectionState(
        mode="claim_validation",
        retriever_synthesis=synthesis_text,
        variable_mappings=variable_mappings or {},
        errors=[],
        warnings=[]
    )
    final_state = graph.invoke(initial_state)

    print(f"[orchestrator] Claim validation complete")
    return final_state


def run_news_collection(
    query: str,
    sources: list = None,
    time_window_days: int = None
) -> dict:
    """
    Run news collection workflow.

    Args:
        query: Topic to search for
        sources: List of news sources (default: DEFAULT_NEWS_SOURCES)
        time_window_days: How far back to search (default: DEFAULT_TIME_WINDOW_DAYS)

    Returns:
        Final state with collected/analyzed news
    """
    print(f"[orchestrator] Starting news collection...")
    print(f"[orchestrator] Query: {query}")

    graph = build_graph()
    initial_state = DataCollectionState(
        mode="news_collection",
        news_query=query,
        news_sources=sources or DEFAULT_NEWS_SOURCES,
        time_window_days=time_window_days or DEFAULT_TIME_WINDOW_DAYS,
        errors=[],
        warnings=[]
    )
    final_state = graph.invoke(initial_state)

    print(f"[orchestrator] News collection complete")
    return final_state


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for testing."""
    parser = argparse.ArgumentParser(description="Data Collection Orchestrator")
    parser.add_argument(
        "--mode",
        choices=["claim_validation", "news_collection"],
        default="claim_validation",
        help="Workflow mode"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Input text (synthesis for claim_validation, query for news_collection)"
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        help="News sources (for news_collection mode)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Time window in days (for news_collection mode)"
    )

    args = parser.parse_args()

    if args.mode == "claim_validation":
        if not args.input:
            # Use sample input for testing
            sample_text = """
            ## Consensus Conclusions
            - BTC follows gold with a lag of 63-428 days
            - TGA drawdown leads to liquidity expansion
            - Fed rate cuts correlate with equity rallies
            """
            print(f"[orchestrator] Using sample input for testing")
            result = run_claim_validation(sample_text)
        else:
            result = run_claim_validation(args.input)

    elif args.mode == "news_collection":
        query = args.input or "institutional investor rebalancing"
        result = run_news_collection(
            query=query,
            sources=args.sources,
            time_window_days=args.days
        )

    # Print result
    print("\n" + "=" * 60)
    print("FINAL OUTPUT:")
    print("=" * 60)
    print(json.dumps(result.get("final_output", {}), indent=2, default=str))


if __name__ == "__main__":
    main()
