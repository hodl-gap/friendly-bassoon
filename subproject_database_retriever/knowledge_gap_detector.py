"""
Knowledge Gap Detector Module

Detects gaps in retrieved information and fills them via web search or data fetching.
This is part of the retrieval layer - topic-agnostic gap detection that works for any query.
"""

import sys
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Lock to prevent concurrent sys.modules manipulation across threads
_import_lock = threading.Lock()

from models import call_claude_haiku, call_claude_sonnet, call_claude_with_tools
from knowledge_gap_prompts import (
    SYSTEM_PROMPT, GAP_DETECTION_PROMPT,
    EXTRACT_EXTREME_DATES_PROMPT, EXTRACT_READINGS_FROM_IMAGE_PROMPT,
    INTERPRET_EVENT_STUDY_PROMPT
)
from query_processing import expand_for_web_chain_extraction

def format_chains_for_prompt(logic_chains: list) -> str:
    """Format logic chains for the gap detection prompt."""
    if not logic_chains:
        return "(No logic chains extracted)"

    lines = []
    for i, chain in enumerate(logic_chains[:10], 1):  # Limit to 10 chains
        if isinstance(chain, dict):
            steps = chain.get("steps", [])
            if steps:
                chain_str = " → ".join(
                    f"{s.get('cause', '?')} → {s.get('effect', '?')}"
                    for s in steps[:3]  # Limit steps
                )
                lines.append(f"{i}. {chain_str}")

    return "\n".join(lines) if lines else "(No logic chains extracted)"


def detect_knowledge_gaps(
    query: str,
    synthesis: str,
    logic_chains: list,
    topic_coverage: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Detect knowledge gaps in retrieved information.

    This is a separate LLM call to identify what information is missing
    before passing context to the consumer (e.g., BTC Intelligence).
    Gaps can then be filled via web search before the final context is returned.

    Args:
        query: User's original query
        synthesis: Retrieved synthesis text from database
        logic_chains: Extracted logic chains
        topic_coverage: Topic coverage dict from answer_generation

    Returns:
        {
            "coverage_rating": "COMPLETE|PARTIAL|INSUFFICIENT",
            "gaps": [
                {
                    "category": "historical_precedent_depth",
                    "status": "GAP",
                    "found": "July 2024 BOJ hike example only",
                    "missing": "Other intervention episodes with impact %",
                    "search_query": "JPY intervention 2022 2023 impact percentage"
                },
                ...
            ],
            "gap_count": 3,
            "search_queries": ["query1", "query2"]  # Extracted for convenience
        }
    """
    # Format inputs
    chains_text = format_chains_for_prompt(logic_chains)

    # Build topic coverage text for prompt
    topic_text = ""
    if topic_coverage:
        topic_text = f"""
Topic Coverage Analysis:
- Query entities: {topic_coverage.get('query_entities', [])}
- Found entities: {topic_coverage.get('found_entities', [])}
- Match ratio: {topic_coverage.get('match_ratio', 0):.2f}
- Direct match: {topic_coverage.get('direct_match', True)}
"""
        if topic_coverage.get('extrapolation_note'):
            topic_text += f"- Note: {topic_coverage['extrapolation_note']}\n"

    # Build prompt
    prompt = GAP_DETECTION_PROMPT.format(
        query=query,
        synthesis=synthesis[:8000],  # Truncate to save tokens
        chains_text=chains_text,
        topic_coverage_text=topic_text
    )

    # Combine system prompt with user prompt
    full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
    messages = [
        {"role": "user", "content": full_prompt}
    ]

    print("[Knowledge Gap] Detecting gaps in retrieved information...")

    # Tool schema for structured output
    gap_tool = {
        "name": "output_gaps",
        "description": "Output detected knowledge gaps",
        "input_schema": {
            "type": "object",
            "properties": {
                "coverage_rating": {
                    "type": "string",
                    "enum": ["COMPLETE", "PARTIAL", "INSUFFICIENT"],
                    "description": "COMPLETE (0 gaps), PARTIAL (1-3 gaps), INSUFFICIENT (4+ gaps)"
                },
                "gaps": {
                    "type": "array",
                    "description": "List of evaluated knowledge categories",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "topic_not_covered",
                                    "historical_precedent_depth",
                                    "quantified_relationships",
                                    "monitoring_thresholds",
                                    "event_calendar",
                                    "mechanism_conditions",
                                    "exit_criteria"
                                ],
                                "description": "Knowledge category being evaluated"
                            },
                            "status": {
                                "type": "string",
                                "enum": ["COVERED", "GAP"],
                                "description": "Whether this category is covered or has a gap"
                            },
                            "fill_method": {
                                "type": "string",
                                "enum": ["web_chain_extraction", "web_search", "data_fetch", "historical_analog"],
                                "description": "Method to fill the gap"
                            },
                            "found": {
                                "type": "string",
                                "description": "What was found (be specific, 1-2 sentences max)"
                            },
                            "missing": {
                                "type": ["string", "null"],
                                "description": "What specific information would fill this gap (null if COVERED)"
                            },
                            "search_query": {
                                "type": ["string", "null"],
                                "description": "Web search query (null if COVERED or if fill_method is data_fetch/historical_analog)"
                            },
                            "instruments": {
                                "type": ["array", "null"],
                                "items": {"type": "string"},
                                "description": "Normalized variable names for data_fetch (null otherwise)"
                            },
                            "indicator_name": {
                                "type": ["string", "null"],
                                "description": "Specific indicator name for historical_analog (null otherwise)"
                            }
                        },
                        "required": ["category", "status", "found"]
                    }
                },
                "gap_count": {
                    "type": "integer",
                    "description": "Number of items with status=GAP"
                }
            },
            "required": ["coverage_rating", "gaps", "gap_count"]
        }
    }

    try:
        # Primary approach: tool_use for structured output
        response = call_claude_with_tools(
            messages=messages,
            tools=[gap_tool],
            tool_choice={"type": "tool", "name": "output_gaps"},
            model="haiku",
            temperature=0.0,
            max_tokens=2000
        )

        # Extract tool_use result
        result = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_gaps":
                result = block.input
                break

        if result is None:
            raise ValueError("No tool_use block found in response")

        print(f"[Knowledge Gap] Raw tool_use response:\n{json.dumps(result, indent=2)}")

    except Exception as e:
        # Fallback: use call_claude_haiku with text parsing
        print(f"[Knowledge Gap] tool_use failed ({e}), falling back to text parsing...")
        try:
            response_text = call_claude_haiku(messages, temperature=0.0, max_tokens=1500)
            print(f"[Knowledge Gap] Raw fallback response:\n{response_text}")

            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            result = json.loads(json_str)
        except Exception as fallback_err:
            print(f"[Knowledge Gap] Fallback also failed: {fallback_err}")
            return {
                "coverage_rating": "UNKNOWN",
                "gaps": [],
                "gap_count": 0,
                "search_queries": [],
                "error": f"Both tool_use and fallback failed: {e}; {fallback_err}"
            }

    try:
        # Extract search queries for convenience
        search_queries = [
            gap["search_query"]
            for gap in result.get("gaps", [])
            if gap.get("status") == "GAP" and gap.get("search_query")
        ]
        result["search_queries"] = search_queries

        # Log summary
        gap_count = result.get("gap_count", 0)
        coverage = result.get("coverage_rating", "UNKNOWN")
        print(f"[Knowledge Gap] Coverage: {coverage}, Gaps: {gap_count}")

        if search_queries:
            print(f"[Knowledge Gap] Suggested searches:")
            for q in search_queries:
                print(f"  - {q}")

        return result

    except Exception as e:
        print(f"[Knowledge Gap] Detection error: {e}")
        return {
            "coverage_rating": "UNKNOWN",
            "gaps": [],
            "gap_count": 0,
            "search_queries": [],
            "error": str(e)
        }


def _get_web_search_adapter():
    """
    Get WebSearchAdapter instance with proper import handling.

    Returns:
        WebSearchAdapter instance or None if import fails
    """
    with _import_lock:
        try:
            data_collection_path = str(Path(__file__).parent.parent / "subproject_data_collection")

            # Clear cached modules that would shadow data_collection's imports
            saved_modules = {}
            for mod_name in ['config', 'web_search_prompts']:
                if mod_name in sys.modules:
                    saved_modules[mod_name] = sys.modules.pop(mod_name)

            # Ensure data_collection path is at the front of sys.path
            if data_collection_path in sys.path:
                sys.path.remove(data_collection_path)
            sys.path.insert(0, data_collection_path)

            from adapters.web_search_adapter import WebSearchAdapter

            # Restore previously cached modules
            for mod_name, mod in saved_modules.items():
                if mod_name not in sys.modules:
                    sys.modules[mod_name] = mod

            return WebSearchAdapter(max_results=8)
        except ImportError as e:
            print(f"[Knowledge Gap] WebSearchAdapter import failed: {e}")
            # Restore on failure too
            for mod_name, mod in saved_modules.items():
                if mod_name not in sys.modules:
                    sys.modules[mod_name] = mod
            return None


def _search_and_evaluate(
    adapter,
    query: str,
    category: str,
    missing: str
) -> Dict[str, Any]:
    """
    Execute search and evaluate if it fills the gap.

    Args:
        adapter: WebSearchAdapter instance
        query: Search query to execute
        category: Gap category being filled
        missing: Description of what's missing

    Returns:
        {
            "filled": True/False,
            "confidence": 0.0-1.0,
            "extracted_info": {...},
            "sources": [...],
            "suggested_refinement": "..." or None
        }
    """
    try:
        result = adapter.search_and_extract(
            query,
            extract_type="knowledge_gap",
            gap_category=category,
            missing_description=missing
        )

        extracted = result.get("extracted", {})
        sources = result.get("sources", [])

        if extracted.get("error"):
            return {
                "filled": False,
                "confidence": 0.0,
                "extracted_info": None,
                "sources": sources,
                "suggested_refinement": None,
                "error": extracted.get("error")
            }

        gap_filled = extracted.get("gap_filled", False)
        confidence = extracted.get("confidence", 0.0)
        suggested_refinement = extracted.get("suggested_refinement")

        return {
            "filled": gap_filled and confidence >= 0.6,
            "confidence": confidence,
            "extracted_info": extracted,
            "sources": sources,
            "suggested_refinement": suggested_refinement
        }

    except Exception as e:
        print(f"[Knowledge Gap] Search error: {e}")
        return {
            "filled": False,
            "confidence": 0.0,
            "extracted_info": None,
            "sources": [],
            "suggested_refinement": None,
            "error": str(e)
        }


def _format_enrichment(category: str, result: Dict[str, Any]) -> str:
    """Format filled gap result as enrichment text."""
    extracted = result.get("extracted_info", {})
    if not extracted:
        return ""

    facts = extracted.get("extracted_facts", [])
    summary = extracted.get("summary", "")
    sources = result.get("sources", [])[:3]  # Limit sources shown

    lines = [
        f"## Additional Context: {category.replace('_', ' ').title()}",
        f"(Source: Web search)"
    ]

    if summary:
        lines.append(summary)

    for fact in facts[:5]:  # Limit facts
        if isinstance(fact, dict):
            fact_text = fact.get("fact", str(fact))
            source = fact.get("source", "")
            if source:
                lines.append(f"- {fact_text} (via {source})")
            else:
                lines.append(f"- {fact_text}")
        else:
            lines.append(f"- {fact}")

    lines.append("")
    return "\n".join(lines)


def _determine_termination_reason(
    filled: list,
    partial: list,
    unfillable: list,
    search_count: int,
    max_searches: int
) -> str:
    """Determine why gap filling terminated."""
    if search_count >= max_searches:
        return "max_searches"
    if len(filled) + len(partial) == 0 and len(unfillable) > 0:
        return "all_unfillable"
    return "all_processed"


def _sanitize_query(query: str) -> Optional[str]:
    """
    Validate that a query string is a usable search engine query.

    Returns:
        The query if valid, or None if it looks like instructions.
    """
    if not query or not query.strip():
        return None

    query = query.strip()

    # Too long - likely instructions or multiple queries joined together
    if len(query) > 120:
        return None

    # Starts with instructional verbs - it's advice, not a query
    lower = query.lower()
    instructional_prefixes = [
        "search for", "try searching", "try ", "look for",
        "use ", "check ", "go to ", "visit ",
    ]
    for prefix in instructional_prefixes:
        if lower.startswith(prefix):
            return None

    # Contains OR joining multiple queries
    if " OR " in query and query.count(" OR ") >= 2:
        return None

    return query


def _empty_fill_result(reason: str) -> Dict[str, Any]:
    """Return empty fill result with given reason."""
    return {
        "filled_gaps": [],
        "partially_filled_gaps": [],
        "unfillable_gaps": [],
        "enrichment_text": "",
        "total_searches": 0,
        "termination_reason": reason
    }


def fill_gaps_with_search(
    gaps: List[Dict[str, Any]],
    max_searches: int = 6,
    max_attempts_per_gap: int = 2
) -> Dict[str, Any]:
    """
    Attempt to fill knowledge gaps via web search with limited iteration.

    Args:
        gaps: List of gap dicts from detect_knowledge_gaps()
        max_searches: Maximum total web searches (default: 6)
        max_attempts_per_gap: Max attempts per gap (default: 2)

    Returns:
        {
            "filled_gaps": [...],
            "partially_filled_gaps": [...],
            "unfillable_gaps": [...],
            "enrichment_text": "...",
            "total_searches": N,
            "termination_reason": "all_processed" | "max_searches" | "all_unfillable"
        }
    """
    # Filter to only web_search gaps with search queries
    searchable_gaps = [
        g for g in gaps
        if g.get("status") == "GAP"
        and g.get("fill_method", "web_search") == "web_search"
        and g.get("search_query")
    ]

    if not searchable_gaps:
        return _empty_fill_result("no_searchable_gaps")

    adapter = _get_web_search_adapter()
    if not adapter:
        print("[Knowledge Gap] WebSearchAdapter not available, skipping gap filling")
        return _empty_fill_result("adapter_unavailable")

    filled = []
    partial = []
    unfillable = []
    enrichment_parts = []
    search_count = 0

    print(f"[Knowledge Gap] Attempting to fill {len(searchable_gaps)} gaps (max {max_searches} searches)...")

    for gap in searchable_gaps:
        if search_count >= max_searches:
            unfillable.append({**gap, "reason": "max_searches_reached"})
            continue

        category = gap.get("category", "unknown")
        missing = gap.get("missing", "")
        primary_query = gap.get("search_query", "")

        print(f"\n[Gap: {category}]")
        print(f"  Primary query: {primary_query}")

        # Attempt 1: Primary query
        result = _search_and_evaluate(adapter, primary_query, category, missing)
        search_count += 1

        confidence = result.get("confidence", 0.0)
        print(f"  → Confidence: {confidence:.2f}, Filled: {result.get('filled', False)}")

        if result.get("filled"):
            filled.append({
                **gap,
                "status": "FILLED",
                "confidence": confidence,
                "extracted_info": result.get("extracted_info", {}),
                "sources": result.get("sources", [])
            })
            enrichment_parts.append(_format_enrichment(category, result))
            print(f"  → Status: FILLED")
            continue

        # Attempt 2: Refined query (if allowed and search budget remains)
        if max_attempts_per_gap > 1 and search_count < max_searches:
            raw_refinement = result.get("suggested_refinement")
            refined_query = _sanitize_query(raw_refinement)
            if raw_refinement and not refined_query:
                print(f"  Refined query rejected (not a valid search query): {raw_refinement[:80]}...")
            if refined_query and refined_query != primary_query:
                print(f"  Refined query: {refined_query}")
                result = _search_and_evaluate(adapter, refined_query, category, missing)
                search_count += 1

                confidence = result.get("confidence", 0.0)
                print(f"  → Confidence: {confidence:.2f}, Filled: {result.get('filled', False)}")

                if result.get("filled"):
                    filled.append({
                        **gap,
                        "status": "FILLED",
                        "confidence": confidence,
                        "extracted_info": result.get("extracted_info", {}),
                        "sources": result.get("sources", []),
                        "refined_query": refined_query
                    })
                    enrichment_parts.append(_format_enrichment(category, result))
                    print(f"  → Status: FILLED (via refinement)")
                    continue
                elif confidence >= 0.3:
                    partial.append({
                        **gap,
                        "status": "PARTIALLY_FILLED",
                        "confidence": confidence,
                        "extracted_info": result.get("extracted_info", {}),
                        "sources": result.get("sources", []),
                        "refined_query": refined_query
                    })
                    enrichment_parts.append(_format_enrichment(category, result))
                    print(f"  → Status: PARTIALLY_FILLED")
                    continue

        # Mark as unfillable
        unfillable.append({
            **gap,
            "status": "UNFILLABLE",
            "reason": "no_relevant_results"
        })
        print(f"  → Status: UNFILLABLE")

    termination_reason = _determine_termination_reason(
        filled, partial, unfillable, search_count, max_searches
    )

    print(f"\n[Knowledge Gap] Summary: {len(filled)} filled, {len(partial)} partial, {len(unfillable)} unfillable")
    print(f"[Knowledge Gap] Total searches: {search_count}, termination: {termination_reason}")

    return {
        "filled_gaps": filled,
        "partially_filled_gaps": partial,
        "unfillable_gaps": unfillable,
        "enrichment_text": "\n\n".join(enrichment_parts),
        "total_searches": search_count,
        "termination_reason": termination_reason
    }


def fill_gaps_with_data(
    gaps: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Fill data_fetch gaps by fetching instruments and computing metrics.

    For quantified_relationships gaps: fetches price series from Yahoo/FRED
    and computes correlation.

    Args:
        gaps: List of gap dicts with fill_method=="data_fetch".

    Returns:
        Same format as fill_gaps_with_search() for easy merging.
    """
    import numpy as np

    # Import data fetcher from risk_intelligence (has the fetch logic)
    try:
        with _import_lock:
            btc_intel_path = str(Path(__file__).parent.parent / "subproject_risk_intelligence")
            # Save and clear modules that might conflict
            saved_modules = {}
            for mod_name in ['states', 'config']:
                if mod_name in sys.modules:
                    saved_modules[mod_name] = sys.modules.pop(mod_name)

            if btc_intel_path not in sys.path:
                sys.path.insert(0, btc_intel_path)
            from current_data_fetcher import resolve_variable, fetch_yahoo_with_history, fetch_fred_with_history

            # Restore saved modules
            for mod_name, mod in saved_modules.items():
                if mod_name not in sys.modules:
                    sys.modules[mod_name] = mod
    except ImportError as e:
        print(f"[Knowledge Gap] Data fetcher import failed: {e}")
        return _empty_fill_result("data_fetcher_unavailable")

    data_gaps = [
        g for g in gaps
        if g.get("status") == "GAP" and g.get("fill_method") == "data_fetch"
    ]

    if not data_gaps:
        return _empty_fill_result("no_data_gaps")

    filled = []
    unfillable = []
    enrichment_parts = []

    for gap in data_gaps:
        category = gap.get("category", "unknown")
        instruments = gap.get("instruments", [])

        print(f"\n[Gap: {category}] (data_fetch)")
        print(f"  Instruments: {instruments}")

        if len(instruments) < 2:
            print(f"  → Need at least 2 instruments for correlation, got {len(instruments)}")
            unfillable.append({**gap, "status": "UNFILLABLE", "reason": "insufficient_instruments"})
            continue

        # Fetch price history for each instrument
        series_data = {}
        for inst in instruments[:2]:
            mapping = resolve_variable(inst)
            if not mapping:
                print(f"  → Could not resolve: {inst}")
                continue

            source = mapping["source"]
            series_id = mapping["series_id"]
            data = None

            if source == "Yahoo":
                data = fetch_yahoo_with_history(series_id, lookback_days=90)
            elif source == "FRED":
                data = fetch_fred_with_history(series_id, lookback_days=120)

            if data and data.get("history"):
                series_data[inst] = {
                    "history": data["history"],
                    "source": source,
                    "series_id": series_id
                }
                print(f"  → Fetched {inst}: {len(data['history'])} data points from {source}")

        if len(series_data) < 2:
            print(f"  → Could not fetch enough instruments")
            unfillable.append({**gap, "status": "UNFILLABLE", "reason": "fetch_failed"})
            continue

        # Align dates and compute correlation
        inst_names = list(series_data.keys())
        hist_a = {d: v for d, v in series_data[inst_names[0]]["history"]}
        hist_b = {d: v for d, v in series_data[inst_names[1]]["history"]}

        common_dates = sorted(set(hist_a.keys()) & set(hist_b.keys()))
        if len(common_dates) < 10:
            print(f"  → Only {len(common_dates)} overlapping dates, need at least 10")
            unfillable.append({**gap, "status": "UNFILLABLE", "reason": "insufficient_overlap"})
            continue

        values_a = np.array([hist_a[d] for d in common_dates])
        values_b = np.array([hist_b[d] for d in common_dates])
        correlation = float(np.corrcoef(values_a, values_b)[0, 1])

        print(f"  → Correlation({inst_names[0]}, {inst_names[1]}): {correlation:.4f} over {len(common_dates)} days")

        # Build enrichment text
        enrichment = (
            f"## Additional Context: {category.replace('_', ' ').title()}\n"
            f"(Source: Computed from {series_data[inst_names[0]]['source']}/{series_data[inst_names[1]]['source']} data)\n"
            f"- {inst_names[0].upper()} vs {inst_names[1].upper()} correlation: {correlation:.4f} "
            f"(over {len(common_dates)} trading days)\n"
            f"- Period: {common_dates[0]} to {common_dates[-1]}\n"
        )

        filled.append({
            **gap,
            "status": "FILLED",
            "confidence": 0.9,
            "computed_correlation": correlation,
            "data_points": len(common_dates),
            "period": f"{common_dates[0]} to {common_dates[-1]}"
        })
        enrichment_parts.append(enrichment)

    print(f"\n[Knowledge Gap] Data fetch: {len(filled)} filled, {len(unfillable)} unfillable")

    return {
        "filled_gaps": filled,
        "partially_filled_gaps": [],
        "unfillable_gaps": unfillable,
        "enrichment_text": "\n\n".join(enrichment_parts),
        "total_searches": 0,
        "termination_reason": "all_processed"
    }


def _get_web_chain_adapter():
    """Get WebSearchAdapter configured for chain extraction."""
    with _import_lock:
        try:
            data_collection_path = str(Path(__file__).parent.parent / "subproject_data_collection")

            saved_modules = {}
            for mod_name in ['config', 'web_search_prompts']:
                if mod_name in sys.modules:
                    saved_modules[mod_name] = sys.modules.pop(mod_name)

            if data_collection_path in sys.path:
                sys.path.remove(data_collection_path)
            sys.path.insert(0, data_collection_path)

            from adapters.web_search_adapter import WebSearchAdapter

            for mod_name, mod in saved_modules.items():
                if mod_name not in sys.modules:
                    sys.modules[mod_name] = mod

            return WebSearchAdapter(max_results=8)
        except ImportError as e:
            print(f"[Knowledge Gap] WebSearchAdapter import failed: {e}")
            for mod_name, mod in saved_modules.items():
                if mod_name not in sys.modules:
                    sys.modules[mod_name] = mod
            return None


def _format_chain_enrichment(chains: List[Dict[str, Any]], sources: List[str]) -> str:
    """Format extracted web chains as enrichment text."""
    if not chains:
        return ""

    lines = [
        "## Additional Context: Logic Chains from Trusted Web Sources",
        "(Source: Web search - chains extracted from trusted financial sources)"
    ]

    for i, chain in enumerate(chains, 1):
        cause = chain.get("cause", "Unknown cause")
        effect = chain.get("effect", "Unknown effect")
        mechanism = chain.get("mechanism", "")
        polarity = chain.get("polarity", "unknown")
        source_name = chain.get("source_name", "Unknown source")
        confidence = chain.get("confidence", "medium")
        verified = chain.get("quote_verified", False)

        polarity_symbol = {"positive": "+", "negative": "-", "mixed": "±"}.get(polarity, "?")

        lines.append(f"\n### Chain {i} ({source_name})")
        lines.append(f"- **Cause**: {cause}")
        lines.append(f"- **Effect**: {effect} [{polarity_symbol}]")
        if mechanism:
            lines.append(f"- **Mechanism**: {mechanism}")
        lines.append(f"- **Confidence**: {confidence}" + (" (quote verified)" if verified else ""))

        quote = chain.get("evidence_quote", "")
        if quote and len(quote) > 20:
            lines.append(f"- **Evidence**: \"{quote[:150]}...\"" if len(quote) > 150 else f"- **Evidence**: \"{quote}\"")

    if sources:
        lines.append(f"\n**Sources**: {', '.join(sources[:3])}")

    return "\n".join(lines)


def _convert_saved_chunks_to_web_chains(chunks: list) -> list:
    """
    Convert Pinecone web chain chunks back to flat chain format.

    Saved web chains in Pinecone have their chain data in metadata.extracted_data
    (JSON string) or in top-level metadata fields (cause, effect, mechanism, etc.).
    This parses them into the same flat dict format that fill_gaps_with_web_chains()
    produces, so they can be merged with newly extracted chains.

    Args:
        chunks: List of Pinecone result dicts with id, score, metadata

    Returns:
        List of flat chain dicts compatible with merge_web_chains_with_db_chains()
    """
    chains = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})

        # Try extracted_data JSON first (canonical storage format)
        extracted_data = metadata.get("extracted_data", "")
        if isinstance(extracted_data, str) and extracted_data:
            try:
                parsed = json.loads(extracted_data)
                for lc in parsed.get("logic_chains", []):
                    for step in lc.get("steps", []):
                        chains.append({
                            "cause": step.get("cause", ""),
                            "effect": step.get("effect", ""),
                            "mechanism": step.get("mechanism", lc.get("mechanism", "")),
                            "polarity": step.get("polarity", "unknown"),
                            "source_name": metadata.get("source", "web (saved)"),
                            "confidence": step.get("confidence", "medium"),
                            "source_type": "web",
                            "confidence_weight": 0.7,
                            "from_saved": True,
                        })
                if chains:
                    continue  # Got chains from extracted_data, skip fallback
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback: top-level metadata fields (set by web_chain_persistence.py)
        cause = metadata.get("cause", "")
        effect = metadata.get("effect", "")
        if cause and effect:
            chains.append({
                "cause": cause,
                "effect": effect,
                "mechanism": metadata.get("mechanism", ""),
                "polarity": metadata.get("polarity", "unknown"),
                "source_name": metadata.get("source", "web (saved)"),
                "confidence": metadata.get("confidence", "medium"),
                "source_type": "web",
                "confidence_weight": 0.7,
                "from_saved": True,
            })

    return chains


def fill_gaps_with_web_chains(
    gaps: List[Dict[str, Any]],
    query: str,
    min_tier: int = 2,
    min_trusted_sources: int = 2,
    confidence_weight: float = 0.7
) -> Dict[str, Any]:
    """
    Fill topic_not_covered gaps by extracting logic chains from trusted web sources.

    Uses multi-angle query expansion to search from multiple dimensions,
    just like the regular query expansion does for DB retrieval.

    Args:
        gaps: List of gap dicts with fill_method=="web_chain_extraction"
        query: Original user query (used for multi-angle expansion)
        min_tier: Minimum source tier (1 = Tier 1 only, 2 = include Tier 2)
        min_trusted_sources: Minimum trusted sources required
        confidence_weight: Weight for web chains (vs 1.0 for DB chains)

    Returns:
        {
            "filled_gaps": [...],
            "partially_filled_gaps": [...],
            "unfillable_gaps": [...],
            "enrichment_text": "...",
            "extracted_chains": [...],
            "total_searches": N,
            "termination_reason": "..."
        }
    """
    chain_gaps = [
        g for g in gaps
        if g.get("status") == "GAP" and g.get("fill_method") == "web_chain_extraction"
    ]

    if not chain_gaps:
        return {
            "filled_gaps": [],
            "partially_filled_gaps": [],
            "unfillable_gaps": [],
            "enrichment_text": "",
            "extracted_chains": [],
            "total_searches": 0,
            "termination_reason": "no_chain_gaps"
        }

    adapter = _get_web_chain_adapter()
    if not adapter:
        print("[Knowledge Gap] WebSearchAdapter not available for chain extraction")
        return {
            "filled_gaps": [],
            "partially_filled_gaps": [],
            "unfillable_gaps": chain_gaps,
            "enrichment_text": "",
            "extracted_chains": [],
            "total_searches": 0,
            "termination_reason": "adapter_unavailable"
        }

    filled = []
    partial = []
    unfillable = []
    all_chains = []
    enrichment_parts = []
    search_count = 0

    print(f"[Knowledge Gap] Extracting logic chains for {len(chain_gaps)} topic gaps...")

    for gap in chain_gaps:
        category = gap.get("category", "unknown")
        gap_description = gap.get("missing", "")
        primary_query = gap.get("search_query", "")
        topic = gap_description or primary_query

        if not topic:
            unfillable.append({**gap, "status": "UNFILLABLE", "reason": "no_topic"})
            continue

        print(f"\n[Gap: {category}] (web_chain_extraction)")
        print(f"  Topic: {topic}")

        # Generate multi-angle queries using query expansion logic
        expanded_queries = expand_for_web_chain_extraction(query, gap_description)
        print(f"  Expanded to {len(expanded_queries)} dimension queries:")
        for eq in expanded_queries:
            print(f"    [{eq.get('dimension', '?')}] {eq.get('query', '')}")

        # Search each dimension and collect chains
        gap_chains = []
        gap_sources = []

        for dim_query in expanded_queries:
            dim_name = dim_query.get("dimension", "unknown")
            search_q = dim_query.get("query", "")

            if not search_q:
                continue

            print(f"  Searching: {search_q}")
            result = adapter.search_and_extract_chains(
                query=search_q,
                topic=topic,
                min_tier=min_tier,
                verify_quotes=True,
                extraction_focus=dim_query.get("reasoning", "")
            )
            search_count += 1

            chains = result.get("chains", [])
            trusted_count = result.get("trusted_sources_count", 0)
            filtered_sources = result.get("filtered_sources", [])

            print(f"    → Found {len(chains)} chains from {trusted_count} trusted sources")

            # Add dimension info to chains
            for chain in chains:
                chain["dimension"] = dim_name
                chain["source_type"] = "web"
                chain["confidence_weight"] = confidence_weight

            gap_chains.extend(chains)
            gap_sources.extend(filtered_sources)

        # Deduplicate sources
        gap_sources = list(set(gap_sources))

        print(f"  Total: {len(gap_chains)} chains from {len(gap_sources)} unique sources")

        # Check minimum requirements
        if len(gap_sources) < min_trusted_sources:
            print(f"  → Insufficient trusted sources ({len(gap_sources)} < {min_trusted_sources})")
            unfillable.append({
                **gap,
                "status": "UNFILLABLE",
                "reason": f"insufficient_trusted_sources ({len(gap_sources)})",
                "trusted_sources_count": len(gap_sources)
            })
            continue

        if not gap_chains:
            print(f"  → No chains extracted despite trusted sources")
            unfillable.append({
                **gap,
                "status": "UNFILLABLE",
                "reason": "no_chains_extracted",
                "trusted_sources_count": len(gap_sources)
            })
            continue

        all_chains.extend(gap_chains)

        # Determine fill status based on chain quality
        verified_count = sum(1 for c in gap_chains if c.get("quote_verified", False))
        high_confidence_count = sum(1 for c in gap_chains if c.get("confidence") == "high")

        if verified_count >= 2 or high_confidence_count >= 2:
            filled.append({
                **gap,
                "status": "FILLED",
                "chain_count": len(gap_chains),
                "verified_quotes": verified_count,
                "trusted_sources_count": len(gap_sources),
                "sources": gap_sources,
                "dimensions_searched": [q.get("dimension") for q in expanded_queries]
            })
            enrichment_parts.append(_format_chain_enrichment(gap_chains, gap_sources))
            print(f"  → Status: FILLED ({len(gap_chains)} chains, {verified_count} verified)")
        elif len(gap_chains) >= 1:
            partial.append({
                **gap,
                "status": "PARTIALLY_FILLED",
                "chain_count": len(gap_chains),
                "verified_quotes": verified_count,
                "trusted_sources_count": len(gap_sources),
                "sources": gap_sources
            })
            enrichment_parts.append(_format_chain_enrichment(gap_chains, gap_sources))
            print(f"  → Status: PARTIALLY_FILLED ({len(gap_chains)} chains)")
        else:
            unfillable.append({
                **gap,
                "status": "UNFILLABLE",
                "reason": "low_quality_chains",
                "chain_count": len(gap_chains)
            })

    print(f"\n[Knowledge Gap] Web chain extraction: {len(filled)} filled, {len(partial)} partial, {len(unfillable)} unfillable")
    print(f"[Knowledge Gap] Total chains extracted: {len(all_chains)}")

    return {
        "filled_gaps": filled,
        "partially_filled_gaps": partial,
        "unfillable_gaps": unfillable,
        "enrichment_text": "\n\n".join(enrichment_parts),
        "extracted_chains": all_chains,
        "total_searches": search_count,
        "termination_reason": "all_processed"
    }


def extract_readings_from_image(
    image_path: str,
    indicator_name: str
) -> List[Dict[str, Any]]:
    """
    Extract extreme indicator readings from a chart image using Claude Sonnet vision.

    Args:
        image_path: Path to chart image (JPEG/PNG)
        indicator_name: Name of the indicator shown in the chart

    Returns:
        List of {date, value, label} dicts, or empty list on failure.
    """
    import base64

    print(f"[Historical Analog] Extracting readings from image: {image_path}")

    # Read and encode the image
    try:
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"[Historical Analog] Image file not found: {image_path}")
        return []
    except Exception as e:
        print(f"[Historical Analog] Error reading image: {e}")
        return []

    # Determine media type
    ext = Path(image_path).suffix.lower()
    media_type = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'
    }.get(ext, 'image/jpeg')

    # Build multimodal message
    prompt_text = EXTRACT_READINGS_FROM_IMAGE_PROMPT.format(indicator_name=indicator_name)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": prompt_text
                }
            ]
        }
    ]

    try:
        response = call_claude_sonnet(messages, temperature=0.0, max_tokens=1500)
        print(f"[Historical Analog] Vision response:\n{response}")

        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        parsed = json.loads(json_str)
        dates = parsed.get("dates", [])
        notes = parsed.get("notes", "")

        if notes:
            print(f"[Historical Analog] Image extraction notes: {notes}")
        print(f"[Historical Analog] Extracted {len(dates)} extreme dates from image")

        return dates

    except (json.JSONDecodeError, Exception) as e:
        print(f"[Historical Analog] Image extraction failed: {e}")
        return []


def _extract_dates_from_urls(search_results: List[Dict[str, Any]], indicator_name: str) -> List[Dict[str, Any]]:
    """
    Extract dates embedded in URLs of search results.

    Financial news URLs almost always contain the publication date, which for
    event-driven articles is close to the event date. This catches episodes
    that Haiku can't extract from truncated/paywalled snippets.

    Returns list of {date, value, label} dicts.
    """
    import re

    url_dates = []
    seen_year_months = set()

    for r in search_results:
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("content", "") or r.get("snippet", "")

        # Try YYYY/MM/DD or YYYY-MM-DD patterns in URL
        match = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', url)
        if not match:
            continue

        year, month, day = match.groups()
        year_int = int(year)

        # Only consider plausible financial article dates (2000-2026)
        if year_int < 2000 or year_int > 2026:
            continue

        date_str = f"{year}-{month}-{day}"
        year_month = f"{year}-{month}"

        # Deduplicate by year-month (don't want multiple entries from same period)
        if year_month in seen_year_months:
            continue
        seen_year_months.add(year_month)

        # Build label from title (truncate to keep it readable)
        label = title[:80] if title else f"{indicator_name} episode"

        url_dates.append({
            "date": date_str,
            "value": "extreme",
            "label": label,
            "source": "url_extracted"
        })

    return url_dates


def discover_prior_extreme_dates(
    indicator_name: str,
    query_context: str = ""
) -> List[Dict[str, Any]]:
    """
    Discover prior dates when an indicator reached extreme levels via web search + LLM extraction.

    Uses three layers:
    1. LLM extraction from snippets (primary)
    2. URL date parsing as fallback for paywalled/truncated content
    3. Merge: URL-derived dates fill gaps that LLM missed

    Args:
        indicator_name: Name of the indicator (e.g., "VIX", "put/call ratio")
        query_context: Optional context from the gap's missing field

    Returns:
        List of {date, value, label} dicts, or empty list if discovery fails.
    """
    adapter = _get_web_search_adapter()
    if not adapter:
        print(f"[Historical Analog] WebSearchAdapter unavailable for date discovery")
        return []

    search_query = f'"{indicator_name}" extreme historical dates episodes'
    print(f"[Historical Analog] Searching for prior extreme dates: {search_query}")

    try:
        results = adapter._search(search_query, include_raw_content=False)
    except Exception as e:
        print(f"[Historical Analog] Search failed: {e}")
        return []

    # Format snippets from search results
    snippets_parts = []
    search_results = results if isinstance(results, list) else results.get("results", [])
    for i, r in enumerate(search_results[:8], 1):
        title = r.get("title", "")
        snippet = r.get("content", "") or r.get("snippet", "")
        if snippet:
            snippets_parts.append(f"{i}. [{title}] {snippet[:300]}")

    if not snippets_parts:
        print(f"[Historical Analog] No search snippets found")
        return []

    snippets_text = "\n".join(snippets_parts)
    print(f"[Historical Analog] Got {len(snippets_parts)} snippets, extracting dates via LLM...")

    # Step 1: Extract dates from URLs (catches paywalled articles)
    url_dates = _extract_dates_from_urls(search_results, indicator_name)
    if url_dates:
        print(f"[Historical Analog] Found {len(url_dates)} dates from URLs: {[d['date'] for d in url_dates]}")

    # Step 2: LLM extraction from snippet text
    prompt = EXTRACT_EXTREME_DATES_PROMPT.format(
        indicator_name=indicator_name,
        snippets=snippets_text
    )
    messages = [{"role": "user", "content": prompt}]

    llm_dates = []
    try:
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=1000)
        print(f"[Historical Analog] LLM date extraction response:\n{response}")

        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        parsed = json.loads(json_str)
        llm_dates = parsed.get("dates", [])
        notes = parsed.get("notes", "")

        if notes:
            print(f"[Historical Analog] Date extraction notes: {notes}")
        print(f"[Historical Analog] LLM extracted {len(llm_dates)} dates")

    except (json.JSONDecodeError, Exception) as e:
        print(f"[Historical Analog] LLM date extraction failed: {e}")

    # Step 3: Merge — URL dates fill gaps that LLM missed
    # Build set of year-months already covered by LLM dates
    llm_year_months = set()
    for d in llm_dates:
        date_str = d.get("date", "")
        if len(date_str) >= 7:
            llm_year_months.add(date_str[:7])  # "YYYY-MM"

    merged = list(llm_dates)
    added_from_urls = 0
    for ud in url_dates:
        date_str = ud.get("date", "")
        year_month = date_str[:7] if len(date_str) >= 7 else ""
        if year_month and year_month not in llm_year_months:
            merged.append(ud)
            llm_year_months.add(year_month)
            added_from_urls += 1

    if added_from_urls > 0:
        print(f"[Historical Analog] Added {added_from_urls} URL-derived dates that LLM missed: "
              f"{[d['date'] for d in merged if d.get('source') == 'url_extracted']}")

    # Sort chronologically
    merged.sort(key=lambda d: d.get("date", ""))

    print(f"[Historical Analog] Total: {len(merged)} extreme dates (LLM={len(llm_dates)}, URL-derived={added_from_urls})")
    return merged


def run_event_study(
    event_dates: List[Dict[str, Any]],
    instruments: List[str] = None,
    horizons: List[tuple] = None
) -> List[Dict[str, Any]]:
    """
    Run a generic event study: fetch price data around event dates and compute returns.

    Args:
        event_dates: List of {date, value, label} dicts
        instruments: Ticker symbols to fetch (default: ["SPY", "^VIX"])
        horizons: List of (trading_days, label) tuples (default: 1wk/2wk/1mo)

    Returns:
        List of episode dicts with returns per instrument per horizon.
        Each: {label, date, indicator_value, returns: {instrument: {horizon: pct}}}
    """
    from datetime import datetime

    try:
        import yfinance as yf
    except ImportError:
        print("[Historical Analog] yfinance not installed")
        return []

    if instruments is None:
        instruments = ["SPY", "^VIX"]
    if horizons is None:
        horizons = [(5, "1wk"), (10, "2wk"), (22, "1mo")]

    # Determine date range from event_dates
    all_dates = []
    for reading in event_dates:
        try:
            all_dates.append(datetime.strptime(reading["date"], "%Y-%m-%d"))
        except (ValueError, KeyError):
            continue

    if not all_dates:
        print("[Historical Analog] No valid dates in event_dates")
        return []

    earliest = min(all_dates)
    # Start 30 days before earliest event
    start_date = (earliest - __import__('datetime').timedelta(days=30)).strftime("%Y-%m-%d")

    print(f"[Historical Analog] Fetching {instruments} from {start_date}...")

    # Fetch all instrument histories
    histories = {}
    for ticker_symbol in instruments:
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(start=start_date)
            if hist is not None and len(hist) > 0:
                histories[ticker_symbol] = hist
                print(f"  Fetched {ticker_symbol}: {len(hist)} bars")
            else:
                print(f"  {ticker_symbol}: no data returned")
        except Exception as e:
            print(f"  {ticker_symbol}: fetch error: {e}")

    if not histories:
        print("[Historical Analog] Failed to fetch any instrument data")
        return []

    # Use the first instrument as the reference for snapping dates
    ref_instrument = instruments[0]
    ref_hist = histories.get(ref_instrument)
    if ref_hist is None:
        print(f"[Historical Analog] Reference instrument {ref_instrument} has no data")
        return []

    max_horizon = max(days for days, _ in horizons)
    episodes = []

    for reading in event_dates:
        date_str = reading.get("date", "")
        value = reading.get("value", "")
        label = reading.get("label", "")

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, KeyError):
            continue

        # Snap to nearest trading day in reference instrument
        closest_idx = None
        for i, idx in enumerate(ref_hist.index):
            if idx.tz_localize(None) >= date:
                closest_idx = i
                break

        if closest_idx is None or closest_idx + max_horizon >= len(ref_hist):
            print(f"  {label}: Insufficient data after {date_str}")
            continue

        snapped_date = ref_hist.index[closest_idx].strftime("%Y-%m-%d")

        # Compute returns for each instrument at each horizon
        episode_returns = {}
        for ticker_symbol in instruments:
            hist = histories.get(ticker_symbol)
            if hist is None:
                continue

            # Find this date in this instrument's history
            inst_idx = None
            for i, idx in enumerate(hist.index):
                if idx.tz_localize(None) >= date:
                    inst_idx = i
                    break

            if inst_idx is None:
                continue

            base_price = hist.iloc[inst_idx]['Close']
            inst_returns = {}
            for days, horizon_label in horizons:
                if inst_idx + days < len(hist):
                    future_price = hist.iloc[inst_idx + days]['Close']
                    ret = (future_price - base_price) / base_price * 100
                    inst_returns[horizon_label] = round(ret, 1)

            episode_returns[ticker_symbol] = inst_returns

        episode = {
            "label": label,
            "date": snapped_date,
            "indicator_value": value,
            "returns": episode_returns
        }
        episodes.append(episode)

        # Log summary
        ref_returns = episode_returns.get(ref_instrument, {})
        last_horizon = horizons[-1][1] if horizons else "?"
        print(f"  {label} ({snapped_date}): {ref_instrument} {last_horizon}={ref_returns.get(last_horizon, 'N/A')}%")

    print(f"[Historical Analog] Event study: {len(episodes)}/{len(event_dates)} episodes computed")
    return episodes


def interpret_event_study(
    indicator_name: str,
    episodes: List[Dict[str, Any]],
    gap_context: str = ""
) -> Dict[str, Any]:
    """
    Use LLM to interpret event study results — classify outcomes and identify patterns.

    Args:
        indicator_name: Name of the indicator
        episodes: Output from run_event_study()
        gap_context: Context from the gap's missing field

    Returns:
        {pattern_summary, episode_outcomes, dominant_pattern, pattern_probability, interpretation}
        or empty dict on failure.
    """
    if not episodes:
        return {}

    # Build a readable table for the LLM
    table_lines = ["| Episode | Date | Indicator | Returns |",
                   "|---------|------|-----------|---------|"]
    for ep in episodes:
        returns_parts = []
        for instrument, horizons in ep.get("returns", {}).items():
            for horizon, pct in horizons.items():
                returns_parts.append(f"{instrument} {horizon}: {pct:+.1f}%")
        returns_str = ", ".join(returns_parts) if returns_parts else "N/A"
        table_lines.append(f"| {ep['label']} | {ep['date']} | {ep['indicator_value']} | {returns_str} |")

    episodes_table = "\n".join(table_lines)

    prompt = INTERPRET_EVENT_STUDY_PROMPT.format(
        indicator_name=indicator_name,
        gap_context=gap_context or f"Analyzing prior extreme readings of {indicator_name}",
        episodes_table=episodes_table
    )
    messages = [{"role": "user", "content": prompt}]

    print(f"[Historical Analog] Interpreting {len(episodes)} episodes via LLM...")

    try:
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=1500)
        print(f"[Historical Analog] Interpretation response:\n{response}")

        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        parsed = json.loads(json_str)
        return parsed

    except (json.JSONDecodeError, Exception) as e:
        print(f"[Historical Analog] Interpretation failed: {e}")
        return {}


def _build_analog_enrichment(
    indicator_name: str,
    episodes: List[Dict[str, Any]],
    interpretation: Dict[str, Any]
) -> str:
    """
    Build generic markdown enrichment text from event study episodes and LLM interpretation.

    Args:
        indicator_name: Name of the indicator
        episodes: Output from run_event_study()
        interpretation: Output from interpret_event_study()

    Returns:
        Formatted markdown string.
    """
    if not episodes:
        return ""

    # Collect all instruments and horizons from episodes
    all_instruments = []
    all_horizons = []
    for ep in episodes:
        for instrument, horizons in ep.get("returns", {}).items():
            if instrument not in all_instruments:
                all_instruments.append(instrument)
            for h in horizons:
                if h not in all_horizons:
                    all_horizons.append(h)

    # Build dynamic table header
    header_parts = ["Period", "Date", "Indicator"]
    for inst in all_instruments:
        for h in all_horizons:
            header_parts.append(f"{inst} {h}")

    # Add outcome column if interpretation provided outcomes
    episode_outcomes = {
        eo["date"]: eo.get("outcome", "")
        for eo in interpretation.get("episode_outcomes", [])
        if "date" in eo
    }
    if episode_outcomes:
        header_parts.append("Outcome")

    header = " | ".join(header_parts)
    separator = " | ".join(["---"] * len(header_parts))

    lines = [
        f"## Historical Analog Analysis: Prior Extreme {indicator_name} Episodes",
        f"(Source: Computed from Yahoo Finance data)",
        "",
        f"| {header} |",
        f"| {separator} |"
    ]

    for ep in episodes:
        row = [ep["label"], ep["date"], str(ep["indicator_value"])]
        for inst in all_instruments:
            inst_returns = ep.get("returns", {}).get(inst, {})
            for h in all_horizons:
                val = inst_returns.get(h)
                row.append(f"{val:+.1f}%" if isinstance(val, (int, float)) else "N/A")
        if episode_outcomes:
            row.append(episode_outcomes.get(ep["date"], ""))
        lines.append("| " + " | ".join(row) + " |")

    # Add interpretation
    pattern_summary = interpretation.get("pattern_summary", "")
    interp_text = interpretation.get("interpretation", "")

    if pattern_summary:
        lines.extend(["", f"**Pattern Summary**: {pattern_summary}"])
    if interp_text:
        lines.extend(["", f"**Interpretation**: {interp_text}"])

    return "\n".join(lines)


def fill_historical_analog_gap(
    gap: Dict[str, Any],
    indicator_readings: List[Dict[str, Any]] = None,
    image_path: str = None
) -> Dict[str, Any]:
    """
    Fill historical_precedent_depth gap by analyzing what happened after prior
    extreme readings of the SAME indicator.

    Orchestrates: date discovery → event study → LLM interpretation → enrichment.

    Priority: explicit indicator_readings > image extraction > web search discovery.

    Args:
        gap: Gap dict with category="historical_precedent_depth"
        indicator_readings: List of prior readings, each with:
            - date: "YYYY-MM-DD" when extreme reading occurred
            - value: The indicator value (e.g., Z-score +2.5)
            - label: Description (e.g., "Early 2022")
            If None, attempts image extraction or web search discovery.
        image_path: Optional path to indicator chart image for vision-based extraction.

    Returns:
        {
            "filled": True/False,
            "historical_analysis": {...},
            "enrichment_text": "...",
            "pattern_summary": "..."
        }
    """
    indicator_name = gap.get("indicator_name", "Unknown indicator")
    gap_context = gap.get("missing", "")

    # Step 1: Get event dates (priority: explicit > image > web search)
    if indicator_readings is None and image_path:
        print(f"[Historical Analog] Extracting readings from image for '{indicator_name}'...")
        indicator_readings = extract_readings_from_image(image_path, indicator_name)

    if indicator_readings is None:
        print(f"[Historical Analog] No readings provided, discovering dates for '{indicator_name}'...")
        indicator_readings = discover_prior_extreme_dates(indicator_name, gap_context)

    if not indicator_readings:
        print(f"[Historical Analog] No extreme dates found for '{indicator_name}'")
        return {"filled": False, "reason": "no_dates_found"}

    print(f"[Historical Analog] Analyzing {len(indicator_readings)} prior extreme readings of {indicator_name}...")

    # Step 2: Run event study
    episodes = run_event_study(indicator_readings)

    if not episodes:
        return {"filled": False, "reason": "no_valid_episodes"}

    # Step 3: LLM interpretation
    interpretation = interpret_event_study(indicator_name, episodes, gap_context)

    # Step 4: Build enrichment
    enrichment_text = _build_analog_enrichment(indicator_name, episodes, interpretation)

    pattern_summary = interpretation.get("pattern_summary", "")
    dominant_pattern = interpretation.get("dominant_pattern", "")
    pattern_probability = interpretation.get("pattern_probability", 0.0)

    print(f"\n[Historical Analog] Done: {len(episodes)} episodes, dominant pattern='{dominant_pattern}' ({pattern_probability*100:.0f}%)")

    return {
        "filled": True,
        "historical_analysis": {
            "episodes": episodes,
            "interpretation": interpretation,
            "total_episodes": len(episodes),
            "dominant_pattern": dominant_pattern,
            "pattern_probability": pattern_probability
        },
        "enrichment_text": enrichment_text,
        "pattern_summary": pattern_summary
    }


def merge_web_chains_with_db_chains(
    db_chains: List[Dict[str, Any]],
    web_chains: List[Dict[str, Any]],
    db_weight: float = 1.0,
    web_weight: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Merge logic chains from database and web sources with appropriate weighting.

    DB chains get full weight (1.0), web chains get reduced weight (0.7).
    Deduplicates by cause+effect pair.

    Args:
        db_chains: Logic chains from vector database
        web_chains: Logic chains extracted from web
        db_weight: Weight for DB chains (default 1.0)
        web_weight: Weight for web chains (default 0.7)

    Returns:
        Merged and weighted list of chains
    """
    seen_pairs = set()
    merged = []

    # Add DB chains first (higher priority)
    for chain in db_chains:
        cause = chain.get("cause", "") or ""
        effect = chain.get("effect", "") or ""
        pair_key = (cause.lower().strip(), effect.lower().strip())

        if pair_key not in seen_pairs and cause and effect:
            seen_pairs.add(pair_key)
            merged.append({
                **chain,
                "source_type": "database",
                "confidence_weight": db_weight
            })

    # Add web chains (avoid duplicates)
    for chain in web_chains:
        cause = chain.get("cause", "") or ""
        effect = chain.get("effect", "") or ""
        pair_key = (cause.lower().strip(), effect.lower().strip())

        if pair_key not in seen_pairs and cause and effect:
            seen_pairs.add(pair_key)
            # Normalize source_name → source for canonical schema compatibility
            normalized = {**chain}
            if "source_name" in normalized and "source" not in normalized:
                normalized["source"] = normalized["source_name"]
            merged.append({
                **normalized,
                "source_type": "web",
                "confidence_weight": chain.get("confidence_weight", web_weight)
            })

    print(f"[Chain Merge] {len(db_chains)} DB + {len(web_chains)} web → {len(merged)} merged (deduplicated)")

    return merged


def detect_and_fill_gaps(
    query: str,
    synthesis: str,
    logic_chains: list,
    topic_coverage: Dict[str, Any] = None,
    enable_gap_filling: bool = True,
    max_searches: int = 6,
    max_attempts_per_gap: int = 2,
    image_path: str = None,
    existing_web_chains: list = None,
) -> Dict[str, Any]:
    """
    Main entry point: detect gaps and fill them.

    This orchestrates the full gap detection and filling workflow:
    1. Detect gaps using LLM
    2. Fill web_chain_extraction gaps (multi-angle)
    3. Fill data_fetch gaps (computed from data)
    4. Fill web_search gaps (factual lookups)

    Args:
        query: User's original query
        synthesis: Retrieved synthesis from database
        logic_chains: Extracted logic chains from DB
        topic_coverage: Topic coverage analysis from answer_generation
        enable_gap_filling: Whether to attempt filling gaps
        max_searches: Maximum web searches
        max_attempts_per_gap: Max refinement attempts per gap
        image_path: Optional path to indicator chart image for vision-based extraction
        existing_web_chains: Web chains already gathered by the retrieval agent (skip
            redundant Pinecone search if provided)

    Returns:
        {
            "knowledge_gaps": {...},
            "gap_enrichment_text": "...",
            "filled_gaps": [...],
            "partially_filled_gaps": [...],
            "unfillable_gaps": [...],
            "extracted_web_chains": [...],
            "merged_logic_chains": [...]
        }
    """
    # Step 1: Detect gaps
    gap_result = detect_knowledge_gaps(
        query=query,
        synthesis=synthesis,
        logic_chains=logic_chains,
        topic_coverage=topic_coverage
    )

    # Initialize result
    result = {
        "knowledge_gaps": gap_result,
        "gap_enrichment_text": "",
        "filled_gaps": [],
        "partially_filled_gaps": [],
        "unfillable_gaps": [],
        "extracted_web_chains": [],
        "merged_logic_chains": logic_chains
    }

    if not enable_gap_filling:
        print("[Knowledge Gap] Gap filling disabled")
        return result

    # Step 2: Split gaps by fill method
    gaps = gap_result.get("gaps", [])
    gaps_to_fill = [g for g in gaps if g.get("status") == "GAP"]

    web_chain_gaps = [g for g in gaps_to_fill if g.get("fill_method") == "web_chain_extraction"]
    web_search_gaps = [g for g in gaps_to_fill if g.get("fill_method", "web_search") == "web_search"]
    data_fetch_gaps = [g for g in gaps_to_fill if g.get("fill_method") == "data_fetch"]
    historical_analog_gaps = [g for g in gaps_to_fill if g.get("fill_method") == "historical_analog"]

    # Override: if answer_generation flagged incomplete chains but LLM gap detector
    # said topic is COVERED (e.g. from previously persisted web chains), inject a
    # web_chain_extraction gap so we search for additional angles
    if topic_coverage and topic_coverage.get("needs_web_chain_extraction") and not web_chain_gaps:
        # Focus on what upstream CAUSES are missing, not downstream effects
        # Chains explain what happened but not the investment/structural forces behind it
        missing_desc = (
            "Existing chains cover direct triggers but may be missing: "
            "(1) structural/upstream forces — capital flows, policy decisions, or market "
            "structure shifts that enabled or amplified this event, "
            "(2) institutional contradictions — named analyst or research reports with "
            "opposing views on the consensus narrative"
        )

        injected_gap = {
            "category": "topic_not_covered",
            "status": "GAP",
            "fill_method": "web_chain_extraction",
            "found": "Direct triggers covered but upstream investment/spending dynamics and contradictions missing",
            "missing": missing_desc,
            "search_query": query,
        }
        web_chain_gaps.append(injected_gap)
        print(f"[Knowledge Gap] Injected web_chain_extraction gap (chain override): {missing_desc[:200]}")

    print(f"[Knowledge Gap] Gap split: {len(web_chain_gaps)} web_chain, {len(web_search_gaps)} web_search, {len(data_fetch_gaps)} data_fetch, {len(historical_analog_gaps)} historical_analog")

    # Step 2.5: Check saved web chains in Pinecone before resorting to Tavily
    # Skip if the retrieval agent already gathered web chains (avoids redundant Pinecone search)
    saved_chains_filled = []
    remaining_web_chain_gaps = []
    saved_web_chain_list = []

    if web_chain_gaps and existing_web_chains:
        # Agent already fetched web chains — treat web_chain_extraction gaps as filled
        # Don't add to saved_web_chain_list; caller already tracks these chains
        for gap in web_chain_gaps:
            saved_chains_filled.append({
                **gap,
                "status": "FILLED",
                "chain_count": len(existing_web_chains),
                "fill_source": "agent_web_chains",
            })
        print(f"[Knowledge Gap] Using {len(existing_web_chains)} web chains from retrieval agent (skipping Pinecone re-search)")
        web_chain_gaps = []
    elif web_chain_gaps:
        from vector_search import search_saved_web_chains
        for gap in web_chain_gaps:
            gap_query = gap.get("search_query") or gap.get("missing") or query
            saved_chunks = search_saved_web_chains(gap_query)
            if len(saved_chunks) >= 2:
                converted = _convert_saved_chunks_to_web_chains(saved_chunks)
                if converted:
                    saved_web_chain_list.extend(converted)
                    saved_chains_filled.append({
                        **gap,
                        "status": "FILLED",
                        "chain_count": len(converted),
                        "fill_source": "saved_web_chains",
                    })
                    print(f"[Knowledge Gap] Saved web chains: filled gap '{gap.get('category', '?')}' with {len(converted)} chains from Pinecone")
                    continue
            remaining_web_chain_gaps.append(gap)

        filled_count = len(saved_chains_filled)
        remaining_count = len(remaining_web_chain_gaps)
        print(f"[Knowledge Gap] Saved web chains: {filled_count} gaps filled, {remaining_count} gaps remain for Tavily")
        web_chain_gaps = remaining_web_chain_gaps

    all_filled = list(saved_chains_filled)
    all_partial = []
    all_unfillable = []
    all_enrichment = []
    extracted_web_chains = list(saved_web_chain_list)

    # Parallel gap filling: run independent fill methods concurrently
    def _fill_web_chains():
        return fill_gaps_with_web_chains(gaps=web_chain_gaps, query=query)

    def _fill_data():
        return fill_gaps_with_data(gaps=data_fetch_gaps)

    def _fill_historical_analogs():
        results = {"filled": [], "unfillable": [], "enrichment": []}
        for gap in historical_analog_gaps:
            indicator = gap.get("indicator_name", "Unknown indicator")
            print(f"[retriever.gap_detector] Historical analog: {indicator}")
            analog_result = fill_historical_analog_gap(gap, image_path=image_path)
            if analog_result.get("filled"):
                results["filled"].append({
                    **gap,
                    "status": "FILLED",
                    "historical_analysis": analog_result.get("historical_analysis", {}),
                    "pattern_summary": analog_result.get("pattern_summary", "")
                })
                if analog_result.get("enrichment_text"):
                    results["enrichment"].append(analog_result["enrichment_text"])
            else:
                results["unfillable"].append({
                    **gap,
                    "status": "UNFILLABLE",
                    "reason": analog_result.get("reason", "unknown")
                })
        return results

    def _fill_web_search():
        return fill_gaps_with_search(
            gaps=web_search_gaps,
            max_searches=max_searches,
            max_attempts_per_gap=max_attempts_per_gap
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        if web_chain_gaps:
            futures[executor.submit(_fill_web_chains)] = "web_chains"
        if data_fetch_gaps:
            futures[executor.submit(_fill_data)] = "data_fetch"
        if historical_analog_gaps:
            futures[executor.submit(_fill_historical_analogs)] = "historical_analog"
        if web_search_gaps:
            futures[executor.submit(_fill_web_search)] = "web_search"

        for future in as_completed(futures):
            fill_type = futures[future]
            try:
                result_data = future.result()

                if fill_type == "web_chains":
                    all_filled.extend(result_data.get("filled_gaps", []))
                    all_partial.extend(result_data.get("partially_filled_gaps", []))
                    all_unfillable.extend(result_data.get("unfillable_gaps", []))
                    extracted_web_chains = result_data.get("extracted_chains", [])
                    if result_data.get("enrichment_text"):
                        all_enrichment.append(result_data["enrichment_text"])

                elif fill_type == "data_fetch":
                    all_filled.extend(result_data.get("filled_gaps", []))
                    all_unfillable.extend(result_data.get("unfillable_gaps", []))
                    if result_data.get("enrichment_text"):
                        all_enrichment.append(result_data["enrichment_text"])

                elif fill_type == "historical_analog":
                    all_filled.extend(result_data.get("filled", []))
                    all_unfillable.extend(result_data.get("unfillable", []))
                    all_enrichment.extend(result_data.get("enrichment", []))

                elif fill_type == "web_search":
                    all_filled.extend(result_data.get("filled_gaps", []))
                    all_partial.extend(result_data.get("partially_filled_gaps", []))
                    all_unfillable.extend(result_data.get("unfillable_gaps", []))
                    if result_data.get("enrichment_text"):
                        all_enrichment.append(result_data["enrichment_text"])

            except Exception as e:
                print(f"[retriever.gap_detector] Error in {fill_type} fill: {e}")

    # Step 4: Merge web chains with DB chains
    merged_chains = logic_chains
    if extracted_web_chains:
        merged_chains = merge_web_chains_with_db_chains(
            db_chains=logic_chains,
            web_chains=extracted_web_chains
        )

    result.update({
        "gap_enrichment_text": "\n\n".join(all_enrichment),
        "filled_gaps": all_filled,
        "partially_filled_gaps": all_partial,
        "unfillable_gaps": all_unfillable,
        "extracted_web_chains": extracted_web_chains,
        "merged_logic_chains": merged_chains
    })

    gap_count = len(gaps_to_fill)
    if gap_count > 0:
        print(f"[Knowledge Gap] Summary: {len(all_filled)}/{gap_count} filled, "
              f"{len(all_partial)} partial, {len(all_unfillable)} unfillable")
    else:
        print("[Knowledge Gap] No gaps detected")

    return result
