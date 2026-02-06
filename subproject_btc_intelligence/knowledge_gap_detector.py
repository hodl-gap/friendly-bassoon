"""
Knowledge Gap Detector Module

First-pass LLM call to identify what information is missing before impact analysis.
This separates "assess what's missing" from "analyze what you have".
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_haiku
from .knowledge_gap_prompts import SYSTEM_PROMPT, GAP_DETECTION_PROMPT
from .current_data_fetcher import format_current_values_for_prompt


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
    current_values: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Detect knowledge gaps in retrieved information.

    This is a separate LLM call BEFORE the impact analysis to identify
    what information is missing. Gaps can then be filled via web search
    before the final analysis.

    Args:
        query: User's original query
        synthesis: Retrieved synthesis text from database
        logic_chains: Extracted logic chains
        current_values: Current market data dict

    Returns:
        {
            "coverage_rating": "COMPLETE|PARTIAL|INSUFFICIENT",
            "gaps": [
                {
                    "category": "historical_precedent_depth",
                    "status": "GAP",
                    "found": "July 2024 BOJ hike example only",
                    "missing": "Other intervention episodes with BTC impact %",
                    "search_query": "JPY intervention 2022 2023 Bitcoin impact percentage"
                },
                ...
            ],
            "gap_count": 3,
            "search_queries": ["query1", "query2"]  # Extracted for convenience
        }
    """
    # Format inputs
    chains_text = format_chains_for_prompt(logic_chains)
    current_values_text = format_current_values_for_prompt(current_values)

    # Build prompt
    prompt = GAP_DETECTION_PROMPT.format(
        query=query,
        synthesis=synthesis[:4000],  # Truncate to save tokens
        chains_text=chains_text,
        current_values_text=current_values_text
    )

    # Combine system prompt with user prompt (Anthropic API doesn't accept system role in messages)
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

    The btc_impact_orchestrator adds subproject_database_retriever to sys.path,
    which causes its config.py to shadow the data_collection config.py.
    We temporarily clear the cached 'config' module so the adapter can import
    the correct one from subproject_data_collection.

    Returns:
        WebSearchAdapter instance or None if import fails
    """
    try:
        data_collection_path = str(Path(__file__).parent.parent / "subproject_data_collection")

        # Clear cached modules that would shadow data_collection's imports.
        # The retriever's config.py is already cached as 'config' in sys.modules,
        # which prevents data_collection's config.py from being loaded.
        saved_modules = {}
        for mod_name in ['config', 'web_search_prompts']:
            if mod_name in sys.modules:
                saved_modules[mod_name] = sys.modules.pop(mod_name)

        # Ensure data_collection path is at the front of sys.path
        if data_collection_path in sys.path:
            sys.path.remove(data_collection_path)
        sys.path.insert(0, data_collection_path)

        from adapters.web_search_adapter import WebSearchAdapter

        # Restore previously cached modules so other code isn't broken.
        # The adapter module already has its own bound references to the
        # correct config values, so restoring the old 'config' is safe.
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
    """Format filled gap result as enrichment text for the impact analysis prompt."""
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

    LLMs sometimes return instructions ("Search for X and Y separately")
    instead of actual query strings. This catches those cases.

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
    Attempt to fill knowledge gaps with limited iteration.

    Args:
        gaps: List of gap dicts from detect_knowledge_gaps()
              Each gap MUST contain:
              - category: str (e.g., "historical_precedent_depth")
              - missing: str (what info is needed)
              - search_query: str (suggested query from detector)
        max_searches: Maximum total web searches (default: 6)
        max_attempts_per_gap: Max attempts per gap, primary + refinements (default: 2)

    Strategy:
    1. For each gap, try primary search query (gap["search_query"])
    2. Evaluate: Did search return useful data?
       - YES (confidence >= 0.6) → Mark gap as FILLED, move to next gap
       - NO → Try ONE refined query (LLM suggests refinement)
    3. Evaluate refined query result:
       - YES → Mark gap as FILLED
       - PARTIAL (0.3 <= confidence < 0.6) → Mark as PARTIALLY_FILLED
       - NO → Mark gap as UNFILLABLE, move to next gap
    4. Terminate when: all gaps processed OR max searches reached

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
            # Budget exhausted, mark remaining as unfillable
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

    # Summary
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
              Each gap should contain:
              - category: str
              - instruments: list of variable names (e.g., ["btc", "usdjpy"])

    Returns:
        Same format as fill_gaps_with_search() for easy merging.
    """
    import numpy as np
    from .current_data_fetcher import resolve_variable, fetch_yahoo_with_history, fetch_fred_with_history

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

        # Fetch price history for each instrument (use 1y lookback)
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
    """
    Get WebSearchAdapter configured for chain extraction.

    Similar to _get_web_search_adapter but with proper module handling
    for chain extraction functionality.
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


def _format_chain_enrichment(chains: List[Dict[str, Any]], sources: List[str]) -> str:
    """Format extracted web chains as enrichment text for impact analysis."""
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

        # Include evidence quote if present
        quote = chain.get("evidence_quote", "")
        if quote and len(quote) > 20:
            lines.append(f"- **Evidence**: \"{quote[:150]}...\"" if len(quote) > 150 else f"- **Evidence**: \"{quote}\"")

    if sources:
        lines.append(f"\n**Sources**: {', '.join(sources[:3])}")

    return "\n".join(lines)


def fill_gaps_with_web_chains(
    gaps: List[Dict[str, Any]],
    min_tier: int = 2,
    min_trusted_sources: int = 2,
    confidence_weight: float = 0.7
) -> Dict[str, Any]:
    """
    Fill topic_not_covered gaps by extracting logic chains from trusted web sources.

    This is the main integration point for on-the-fly chain extraction when
    the database has no relevant research on a query topic.

    Args:
        gaps: List of gap dicts with fill_method=="web_chain_extraction"
        min_tier: Minimum source tier (1 = Tier 1 only, 2 = include Tier 2)
        min_trusted_sources: Minimum trusted sources required to proceed
        confidence_weight: Weight for web chains (vs 1.0 for DB chains)

    Returns:
        {
            "filled_gaps": [...],
            "partially_filled_gaps": [...],
            "unfillable_gaps": [...],
            "enrichment_text": "...",
            "extracted_chains": [...],  # Raw chains for merging with DB chains
            "total_searches": N,
            "termination_reason": "..."
        }
    """
    # Filter to web_chain_extraction gaps
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
        search_query = gap.get("search_query", "")
        topic = gap.get("missing", search_query)

        if not search_query:
            unfillable.append({**gap, "status": "UNFILLABLE", "reason": "no_search_query"})
            continue

        print(f"\n[Gap: {category}] (web_chain_extraction)")
        print(f"  Query: {search_query}")

        # Extract chains from trusted sources
        result = adapter.search_and_extract_chains(
            query=search_query,
            topic=topic,
            min_tier=min_tier,
            verify_quotes=True
        )
        search_count += 1

        chains = result.get("chains", [])
        trusted_count = result.get("trusted_sources_count", 0)
        filtered_sources = result.get("filtered_sources", [])

        print(f"  → Found {len(chains)} chains from {trusted_count} trusted sources")

        # Check minimum trusted sources requirement
        if trusted_count < min_trusted_sources:
            print(f"  → Insufficient trusted sources ({trusted_count} < {min_trusted_sources})")
            unfillable.append({
                **gap,
                "status": "UNFILLABLE",
                "reason": f"insufficient_trusted_sources ({trusted_count})",
                "trusted_sources_count": trusted_count
            })
            continue

        if not chains:
            print(f"  → No chains extracted despite trusted sources")
            unfillable.append({
                **gap,
                "status": "UNFILLABLE",
                "reason": "no_chains_extracted",
                "trusted_sources_count": trusted_count
            })
            continue

        # Apply confidence weight to chains
        for chain in chains:
            chain["source_type"] = "web"
            chain["confidence_weight"] = confidence_weight

        all_chains.extend(chains)

        # Determine fill status based on chain quality
        verified_count = sum(1 for c in chains if c.get("quote_verified", False))
        high_confidence_count = sum(1 for c in chains if c.get("confidence") == "high")

        if verified_count >= 2 or high_confidence_count >= 2:
            filled.append({
                **gap,
                "status": "FILLED",
                "chain_count": len(chains),
                "verified_quotes": verified_count,
                "trusted_sources_count": trusted_count,
                "sources": filtered_sources
            })
            enrichment_parts.append(_format_chain_enrichment(chains, filtered_sources))
            print(f"  → Status: FILLED ({len(chains)} chains, {verified_count} verified)")
        elif len(chains) >= 1:
            partial.append({
                **gap,
                "status": "PARTIALLY_FILLED",
                "chain_count": len(chains),
                "verified_quotes": verified_count,
                "trusted_sources_count": trusted_count,
                "sources": filtered_sources
            })
            enrichment_parts.append(_format_chain_enrichment(chains, filtered_sources))
            print(f"  → Status: PARTIALLY_FILLED ({len(chains)} chains)")
        else:
            unfillable.append({
                **gap,
                "status": "UNFILLABLE",
                "reason": "low_quality_chains",
                "chain_count": len(chains)
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
