"""
Output Formatter Module

Formats final output for downstream consumers.
"""

from datetime import datetime
from typing import Dict, Any

from states import DataCollectionState


def format_output(state: DataCollectionState) -> DataCollectionState:
    """
    Format final output for downstream consumers.

    LangGraph node function.

    Args:
        state: Current workflow state

    Returns:
        Updated state with formatted final_output
    """
    mode = state.get("mode", "claim_validation")
    timestamp = datetime.utcnow().isoformat() + "Z"

    print(f"[output_formatter] Formatting output for mode: {mode}")

    if mode == "claim_validation":
        state["final_output"] = format_claim_validation_output(state, timestamp)
    elif mode == "news_collection":
        state["final_output"] = format_news_collection_output(state, timestamp)
    else:
        state["final_output"] = {
            "mode": mode,
            "timestamp": timestamp,
            "error": f"Unknown mode: {mode}"
        }

    return state


def format_claim_validation_output(
    state: DataCollectionState,
    timestamp: str
) -> Dict[str, Any]:
    """
    Format claim validation output.

    Args:
        state: Workflow state
        timestamp: ISO timestamp

    Returns:
        Formatted output dict
    """
    validation_results = state.get("validation_results", [])
    parsed_claims = state.get("parsed_claims", [])

    # Count statuses
    status_counts = {
        "confirmed": 0,
        "partially_confirmed": 0,
        "refuted": 0,
        "inconclusive": 0
    }
    for result in validation_results:
        status = result.get("status", "inconclusive")
        if status in status_counts:
            status_counts[status] += 1

    # Summary stats
    total = len(validation_results)
    validated = status_counts["confirmed"] + status_counts["partially_confirmed"]

    return {
        "mode": "claim_validation",
        "timestamp": timestamp,
        "summary": {
            "claims_parsed": len(parsed_claims),
            "claims_validated": total,
            "confirmed": status_counts["confirmed"],
            "partially_confirmed": status_counts["partially_confirmed"],
            "refuted": status_counts["refuted"],
            "inconclusive": status_counts["inconclusive"],
            "validation_rate": round(validated / total, 2) if total > 0 else 0
        },
        "results": validation_results,
        "data_sources_used": list(set(
            state.get("resolved_data_ids", {}).get(v, {}).get("source", "")
            for v in state.get("resolved_data_ids", {})
        )),
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", [])
    }


def format_news_collection_output(
    state: DataCollectionState,
    timestamp: str
) -> Dict[str, Any]:
    """
    Format news collection output.

    Args:
        state: Workflow state
        timestamp: ISO timestamp

    Returns:
        Formatted output dict
    """
    collected = state.get("collected_articles", [])
    filtered = state.get("filtered_articles", [])
    analyzed = state.get("analyzed_news", [])
    queries = state.get("retriever_queries", [])

    # Extract actionable insights
    actionable = [
        {
            "institution": item.get("institution", "Unknown"),
            "institution_type": item.get("institution_type", ""),
            "action": item.get("action", ""),
            "asset_class": item.get("asset_class", ""),
            "direction": item.get("direction", ""),
            "confidence": item.get("confidence", 0),
            "actionable_insight": item.get("actionable_insight", ""),
            "source_article": item.get("article", {}).get("title", "")
        }
        for item in analyzed
        if item.get("confidence", 0) >= 0.6
    ]

    return {
        "mode": "news_collection",
        "timestamp": timestamp,
        "query": state.get("news_query", ""),
        "sources_queried": state.get("news_sources", []),
        "time_window_days": state.get("time_window_days", 7),
        "summary": {
            "articles_collected": len(collected),
            "articles_relevant": len(filtered),
            "articles_analyzed": len(analyzed),
            "actionable_insights": len(actionable)
        },
        "insights": actionable,
        "retriever_queries": queries,
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", [])
    }


def format_result_for_display(result: Dict[str, Any]) -> str:
    """
    Format result for console display.

    Args:
        result: Final output dict

    Returns:
        Formatted string for display
    """
    lines = []
    mode = result.get("mode", "unknown")

    lines.append(f"Mode: {mode}")
    lines.append(f"Timestamp: {result.get('timestamp', '')}")
    lines.append("")

    if mode == "claim_validation":
        summary = result.get("summary", {})
        lines.append("=== CLAIM VALIDATION RESULTS ===")
        lines.append(f"Claims parsed: {summary.get('claims_parsed', 0)}")
        lines.append(f"Claims validated: {summary.get('claims_validated', 0)}")
        lines.append(f"  - Confirmed: {summary.get('confirmed', 0)}")
        lines.append(f"  - Partially confirmed: {summary.get('partially_confirmed', 0)}")
        lines.append(f"  - Refuted: {summary.get('refuted', 0)}")
        lines.append(f"  - Inconclusive: {summary.get('inconclusive', 0)}")
        lines.append("")

        for i, res in enumerate(result.get("results", []), 1):
            lines.append(f"Claim {i}: {res.get('claim', '')[:60]}...")
            lines.append(f"  Status: {res.get('status', 'unknown').upper()}")
            lines.append(f"  {res.get('interpretation', '')}")
            lines.append("")

    elif mode == "news_collection":
        summary = result.get("summary", {})
        lines.append("=== NEWS COLLECTION RESULTS ===")
        lines.append(f"Query: {result.get('query', '')}")
        lines.append(f"Articles collected: {summary.get('articles_collected', 0)}")
        lines.append(f"Relevant articles: {summary.get('articles_relevant', 0)}")
        lines.append(f"Actionable insights: {summary.get('actionable_insights', 0)}")
        lines.append("")

        for insight in result.get("insights", []):
            lines.append(f"Institution: {insight.get('institution', 'Unknown')}")
            lines.append(f"  Action: {insight.get('action', '')} {insight.get('direction', '')}")
            lines.append(f"  Insight: {insight.get('actionable_insight', '')}")
            lines.append("")

        if result.get("retriever_queries"):
            lines.append("Suggested follow-up queries:")
            for q in result.get("retriever_queries", []):
                lines.append(f"  - {q}")

    if result.get("errors"):
        lines.append("")
        lines.append("ERRORS:")
        for err in result.get("errors", []):
            lines.append(f"  - {err}")

    if result.get("warnings"):
        lines.append("")
        lines.append("WARNINGS:")
        for warn in result.get("warnings", []):
            lines.append(f"  - {warn}")

    return "\n".join(lines)
