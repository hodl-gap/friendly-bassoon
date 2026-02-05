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
    # Filter to only gaps with search queries
    searchable_gaps = [
        g for g in gaps
        if g.get("status") == "GAP" and g.get("search_query")
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
