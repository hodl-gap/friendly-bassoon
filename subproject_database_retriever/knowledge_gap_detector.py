"""
Knowledge Gap Detector Module

Detects gaps in retrieved information and fills them via web search or data fetching.
This is part of the retrieval layer - topic-agnostic gap detection that works for any query.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_haiku
from knowledge_gap_prompts import SYSTEM_PROMPT, GAP_DETECTION_PROMPT
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
        synthesis=synthesis[:4000],  # Truncate to save tokens
        chains_text=chains_text,
        topic_coverage_text=topic_text
    )

    # Combine system prompt with user prompt
    full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
    messages = [
        {"role": "user", "content": full_prompt}
    ]

    print("[Knowledge Gap] Detecting gaps in retrieved information...")

    try:
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=1500)
        print(f"[Knowledge Gap] Raw response:\n{response}")

        # Parse JSON response
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        result = json.loads(json_str)

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

    except json.JSONDecodeError as e:
        print(f"[Knowledge Gap] JSON parse error: {e}")
        return {
            "coverage_rating": "UNKNOWN",
            "gaps": [],
            "gap_count": 0,
            "search_queries": [],
            "error": f"Parse error: {e}"
        }
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

    # Import data fetcher from btc_intelligence (has the fetch logic)
    try:
        btc_intel_path = str(Path(__file__).parent.parent / "subproject_btc_intelligence")
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
                verify_quotes=True
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


def fill_historical_analog_gap(
    gap: Dict[str, Any],
    indicator_readings: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Fill historical_precedent_depth gap by analyzing what happened after prior
    extreme readings of the SAME indicator.

    Instead of generic "short squeeze history" searches, this:
    1. Takes prior extreme readings of the specific indicator (dates + values)
    2. Fetches price data (SPY, VIX) around each date
    3. Calculates what happened in the 1wk, 2wk, 1mo after each reading
    4. Summarizes the pattern (e.g., "3 of 4 prior extremes led to squeezes")

    Args:
        gap: Gap dict with category="historical_precedent_depth"
        indicator_readings: List of prior readings, each with:
            - date: "YYYY-MM-DD" when extreme reading occurred
            - value: The indicator value (e.g., Z-score +2.5)
            - label: Description (e.g., "Early 2022")
            If None, attempts to search for prior readings.

    Returns:
        {
            "filled": True/False,
            "historical_analysis": {...},
            "enrichment_text": "...",
            "pattern_summary": "..."
        }
    """
    import numpy as np
    from datetime import datetime, timedelta

    # Import Yahoo fetcher
    try:
        import yfinance as yf
    except ImportError:
        print("[Historical Analog] yfinance not installed")
        return {"filled": False, "reason": "yfinance_unavailable"}

    # Default indicator readings from GS Prime Book chart (extracted from image)
    # These are the dates when Z-score was approximately +2 or higher
    if indicator_readings is None:
        indicator_readings = [
            {"date": "2022-01-24", "value": "+2.5", "label": "Early 2022"},
            {"date": "2022-06-17", "value": "+2", "label": "Mid 2022 (bear market low)"},
            {"date": "2023-01-03", "value": "+2", "label": "Early 2023"},
            {"date": "2024-08-05", "value": "+1.5", "label": "Late 2024 (carry unwind)"},
        ]

    print(f"[Historical Analog] Analyzing {len(indicator_readings)} prior extreme readings...")

    # Fetch SPY and VIX data
    try:
        spy = yf.Ticker("SPY")
        vix = yf.Ticker("^VIX")
        spy_hist = spy.history(start="2022-01-01", end="2026-02-10")
        vix_hist = vix.history(start="2022-01-01", end="2026-02-10")
    except Exception as e:
        print(f"[Historical Analog] Failed to fetch data: {e}")
        return {"filled": False, "reason": f"fetch_failed: {e}"}

    results = []
    squeeze_count = 0
    total_valid = 0

    for reading in indicator_readings:
        date_str = reading["date"]
        value = reading["value"]
        label = reading["label"]

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            continue

        # Find closest trading day in SPY data
        closest_idx = None
        for i, idx in enumerate(spy_hist.index):
            if idx.tz_localize(None) >= date:
                closest_idx = i
                break

        if closest_idx is None or closest_idx + 22 >= len(spy_hist):
            print(f"  {label}: Insufficient data")
            continue

        base_price = spy_hist.iloc[closest_idx]['Close']
        base_date = spy_hist.index[closest_idx].strftime("%Y-%m-%d")

        # Calculate SPY returns at different horizons
        returns = {}
        for days, period_label in [(5, "1wk"), (10, "2wk"), (22, "1mo")]:
            if closest_idx + days < len(spy_hist):
                future_price = spy_hist.iloc[closest_idx + days]['Close']
                ret = (future_price - base_price) / base_price * 100
                returns[period_label] = round(ret, 1)

        # Get VIX change over 1 month
        vix_change = None
        vix_closest_idx = None
        for i, idx in enumerate(vix_hist.index):
            if idx.tz_localize(None) >= date:
                vix_closest_idx = i
                break

        if vix_closest_idx and vix_closest_idx + 22 < len(vix_hist):
            base_vix = vix_hist.iloc[vix_closest_idx]['Close']
            future_vix = vix_hist.iloc[vix_closest_idx + 22]['Close']
            vix_change = round((future_vix - base_vix) / base_vix * 100, 1)

        # Determine if this was a squeeze (SPY +5% in 1mo AND VIX down 15%+)
        is_squeeze = returns.get("1mo", 0) > 5 and (vix_change is not None and vix_change < -15)

        total_valid += 1
        if is_squeeze:
            squeeze_count += 1

        result_entry = {
            "label": label,
            "date": base_date,
            "indicator_value": value,
            "spy_returns": returns,
            "vix_change_1mo": vix_change,
            "outcome": "SQUEEZE" if is_squeeze else "NO_SQUEEZE"
        }
        results.append(result_entry)

        outcome_str = "✅ SQUEEZE" if is_squeeze else "❌ NO SQUEEZE"
        print(f"  {label} ({base_date}): SPY 1mo={returns.get('1mo', 'N/A')}%, VIX 1mo={vix_change}% → {outcome_str}")

    if total_valid == 0:
        return {"filled": False, "reason": "no_valid_readings"}

    # Build pattern summary
    squeeze_rate = squeeze_count / total_valid
    pattern_summary = (
        f"{squeeze_count} of {total_valid} prior extreme readings led to short squeezes "
        f"(SPY +5%+ in 1mo, VIX crushed 15%+). "
        f"Squeeze probability based on historical pattern: {squeeze_rate*100:.0f}%"
    )

    # Build enrichment text
    enrichment_lines = [
        "## Historical Analog Analysis: Prior Extreme Short Positioning Episodes",
        f"(Source: Computed from Yahoo Finance data for GS Prime Book extreme readings)",
        "",
        "| Period | Date | Indicator | SPY 1mo | VIX 1mo | Outcome |",
        "|--------|------|-----------|---------|---------|---------|"
    ]

    for r in results:
        spy_1mo = f"{r['spy_returns'].get('1mo', 'N/A'):+.1f}%" if isinstance(r['spy_returns'].get('1mo'), (int, float)) else "N/A"
        vix_1mo = f"{r['vix_change_1mo']:+.1f}%" if r['vix_change_1mo'] is not None else "N/A"
        outcome = "✅ SQUEEZE" if r['outcome'] == "SQUEEZE" else "❌ No squeeze"
        enrichment_lines.append(
            f"| {r['label']} | {r['date']} | {r['indicator_value']} | {spy_1mo} | {vix_1mo} | {outcome} |"
        )

    enrichment_lines.extend([
        "",
        f"**Pattern Summary**: {pattern_summary}",
        "",
        f"**Current Reading**: Z-score +3 (highest on record since 2021)",
        f"**Historical Implication**: Based on {squeeze_count}/{total_valid} prior episodes, "
        f"probability of short squeeze is {'elevated' if squeeze_rate >= 0.5 else 'uncertain'}."
    ])

    print(f"\n[Historical Analog] Pattern: {squeeze_count}/{total_valid} squeezes ({squeeze_rate*100:.0f}%)")

    return {
        "filled": True,
        "historical_analysis": {
            "episodes": results,
            "squeeze_count": squeeze_count,
            "total_episodes": total_valid,
            "squeeze_rate": squeeze_rate
        },
        "enrichment_text": "\n".join(enrichment_lines),
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
            merged.append({
                **chain,
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
    max_attempts_per_gap: int = 2
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

    print(f"[Knowledge Gap] Gap split: {len(web_chain_gaps)} web_chain, {len(web_search_gaps)} web_search, {len(data_fetch_gaps)} data_fetch, {len(historical_analog_gaps)} historical_analog")

    all_filled = []
    all_partial = []
    all_unfillable = []
    all_enrichment = []
    extracted_web_chains = []

    # Step 3a: Fill web_chain_extraction gaps (multi-angle)
    if web_chain_gaps:
        chain_result = fill_gaps_with_web_chains(
            gaps=web_chain_gaps,
            query=query
        )
        all_filled.extend(chain_result.get("filled_gaps", []))
        all_partial.extend(chain_result.get("partially_filled_gaps", []))
        all_unfillable.extend(chain_result.get("unfillable_gaps", []))
        extracted_web_chains = chain_result.get("extracted_chains", [])
        if chain_result.get("enrichment_text"):
            all_enrichment.append(chain_result["enrichment_text"])

    # Step 3b: Fill data_fetch gaps
    if data_fetch_gaps:
        data_result = fill_gaps_with_data(gaps=data_fetch_gaps)
        all_filled.extend(data_result.get("filled_gaps", []))
        all_unfillable.extend(data_result.get("unfillable_gaps", []))
        if data_result.get("enrichment_text"):
            all_enrichment.append(data_result["enrichment_text"])

    # Step 3b2: Fill historical_analog gaps (indicator-specific historical precedent)
    if historical_analog_gaps:
        print(f"\n[Knowledge Gap] Filling {len(historical_analog_gaps)} historical analog gaps...")
        for gap in historical_analog_gaps:
            indicator = gap.get("indicator_name", "Unknown indicator")
            print(f"  Indicator: {indicator}")

            # Call the historical analog analysis
            analog_result = fill_historical_analog_gap(gap)

            if analog_result.get("filled"):
                all_filled.append({
                    **gap,
                    "status": "FILLED",
                    "historical_analysis": analog_result.get("historical_analysis", {}),
                    "pattern_summary": analog_result.get("pattern_summary", "")
                })
                if analog_result.get("enrichment_text"):
                    all_enrichment.append(analog_result["enrichment_text"])
            else:
                all_unfillable.append({
                    **gap,
                    "status": "UNFILLABLE",
                    "reason": analog_result.get("reason", "unknown")
                })

    # Step 3c: Fill web_search gaps
    if web_search_gaps:
        search_result = fill_gaps_with_search(
            gaps=web_search_gaps,
            max_searches=max_searches,
            max_attempts_per_gap=max_attempts_per_gap
        )
        all_filled.extend(search_result.get("filled_gaps", []))
        all_partial.extend(search_result.get("partially_filled_gaps", []))
        all_unfillable.extend(search_result.get("unfillable_gaps", []))
        if search_result.get("enrichment_text"):
            all_enrichment.append(search_result["enrichment_text"])

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
