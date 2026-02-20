"""
Query Processing Module

Processes, expands, and refines user queries for better retrieval.
"""

import sys
import re
from pathlib import Path
from datetime import datetime

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_haiku
from states import RetrieverState
from query_processing_prompts import (
    QUERY_EXPANSION_PROMPT_SIMPLE,
    QUERY_EXPANSION_PROMPT_COMPLEX,
    QUERY_REFINEMENT_PROMPT,
)
from config import SIMPLE_QUERY_MAX_WORDS, SIMPLE_QUERY_DIMENSIONS, COMPLEX_QUERY_DIMENSIONS


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

        # Extract temporal reference from query
        temporal_ref = extract_temporal_reference(query)
        print(f"[query_processing] Temporal reference: {temporal_ref}")

        # Expand query for better recall (layered approach)
        processed_query, variations, layered_results = expand_query(query)

        print(f"[query_processing] Type: {query_type}, Variations: {len(variations)}")

        return {
            **state,
            "processed_query": processed_query,
            "query_type": query_type,
            "query_variations": variations,
            "query_dimensions": layered_results,  # Full debug info with dimensions/reasoning
            "query_temporal_reference": temporal_ref
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
    """Classify query type using pattern matching (no LLM needed).

    The system only processes research questions, so this is a lightweight check
    to conditionally skip contradiction detection for simple data lookups.
    """
    data_lookup_patterns = [
        "find all", "what level", "what threshold", "how much is",
        "get the value", "what is the current", "show me the",
        "list all", "what are the values"
    ]
    if any(p in query.lower() for p in data_lookup_patterns):
        return "data_lookup"
    return "research_question"


def is_simple_query(query: str) -> bool:
    """
    Determine if a query is "simple" (fewer dimensions needed).

    Simple queries:
    - Short (fewer words)
    - Single concept
    - Direct questions about one thing

    Complex queries:
    - Multiple concepts/relationships
    - Temporal elements
    - Causal chains
    """
    # Count words (simple heuristic)
    words = len(query.split())

    # Check for complexity indicators
    complexity_indicators = [
        " and ",
        " or ",
        " vs ",
        " versus ",
        " relationship ",
        " between ",
        " causes ",
        " affects ",
        " leads to ",
        " →",
        "->",
    ]

    has_complexity = any(indicator in query.lower() for indicator in complexity_indicators)

    # Simple if short AND no complexity indicators
    is_simple = words <= SIMPLE_QUERY_MAX_WORDS and not has_complexity

    return is_simple


def expand_query(query: str) -> tuple:
    """
    Generate query variations using layered approach.

    Adaptive expansion: fewer dimensions for simple queries, more for complex.
    """
    # Determine query complexity
    simple = is_simple_query(query)
    num_dimensions = SIMPLE_QUERY_DIMENSIONS if simple else COMPLEX_QUERY_DIMENSIONS

    print(f"[query_processing] Query complexity: {'simple' if simple else 'complex'} ({num_dimensions} dimensions)")

    # Use appropriate prompt
    if simple:
        prompt = QUERY_EXPANSION_PROMPT_SIMPLE.format(query=query)
    else:
        prompt = QUERY_EXPANSION_PROMPT_COMPLEX.format(query=query)

    messages = [{"role": "user", "content": prompt}]
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
    print(f"\n[query_processing] Parsed {len(queries)} dimension queries (target: {num_dimensions}):")
    for item in layered_results:
        print(f"  [{item['dimension']}] {item['query']}")
        print(f"    -> {item['reasoning']}")

    return query, queries, layered_results


def refine_query(original_query: str, previous_chunks: list) -> str:
    """Refine query based on previous retrieval results.

    Uses a Haiku call to examine what was (or wasn't) found and
    generate a refined query with alternative terminology.
    """
    chunk_summaries = "\n".join(
        f"- {c.get('metadata', {}).get('title', 'Untitled')}: {c.get('metadata', {}).get('text', '')[:100]}..."
        for c in previous_chunks[:5]
    )

    prompt = QUERY_REFINEMENT_PROMPT.format(
        query=original_query,
        chunk_count=len(previous_chunks),
        chunk_summaries=chunk_summaries or "(no chunks found)"
    )

    try:
        messages = [{"role": "user", "content": prompt}]
        refined = call_claude_haiku(messages, temperature=0.3, max_tokens=200).strip()
        if refined and refined != original_query:
            return refined
        return original_query
    except Exception as e:
        print(f"[query_processing] Query refinement failed: {e}")
        return original_query


def expand_for_web_chain_extraction(query: str, gap_description: str) -> list:
    """
    Generate multi-angle queries for web chain extraction.

    When a topic is not covered in the database, we use the same
    multi-dimension expansion logic to search the web from multiple angles.
    This ensures we don't just search with a single BTC-centric query.

    Args:
        query: Original user query
        gap_description: Description of what's missing (from gap detector)

    Returns:
        List of dicts: [{"dimension": "...", "query": "...", "reasoning": "..."}]
    """
    # Combine query context with gap description for better expansion
    combined_topic = f"{query}. Specifically missing: {gap_description}" if gap_description else query

    # Use the complex expansion prompt for multi-angle search
    prompt = f"""You are a query expansion engine for web search on financial/economic topics.

Your task: Generate 3-4 search queries that approach this topic from different angles.
These queries will be used to search the web for logic chains (cause → effect relationships).

## Guidelines
- Each query should target a DIFFERENT ANGLE of the topic
- Use concrete market terms: "equities", "stocks", "CAPEX", "valuation", etc.
- Include relevant entities: company names, sectors, market terms
- Keep queries SHORT and focused (5-8 words max) — fewer terms yield better search results
- DO NOT include specific domain names like "Bitcoin" or "crypto" unless the topic requires it

## Required Angle Coverage (generate 4 queries, one per angle)
1. Direct trigger/catalyst — what specific event or data release caused this
2. Upstream enabler — what CAPEX, infrastructure spending, or capital allocation by the DISRUPTORS (e.g., big-tech hyperscalers, not the disrupted companies) ENABLED or amplified the forces behind this event
3. Counterargument or contradiction — opposing analyst views, "logically impossible" arguments, bearish/bullish disagreements from named institutions
4. Quantitative impact — specific dollar amounts, percentage moves, index levels, drawdowns

Topic to cover: {combined_topic}

## Output Format
DIMENSION: [short name for this angle]
REASONING: [one sentence - why this angle matters]
QUERY: [the search query]

(repeat for each, 3-4 total)"""

    messages = [{"role": "user", "content": prompt}]
    response = call_claude_haiku(messages, temperature=0.3, max_tokens=800)

    print(f"[query_processing] Web chain expansion response:\n{response}")

    # Parse structured output (same logic as expand_query)
    results = []
    current_layer = None
    current_reasoning = None

    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        if "DIMENSION:" in line.upper():
            current_layer = line.split(":", 1)[-1].strip().strip("*").strip()
        elif line.upper().startswith("REASONING:") or "REASONING:" in line:
            current_reasoning = line.split(":", 1)[-1].strip().strip("*").strip()
        elif line.upper().startswith("QUERY:") or "QUERY:" in line:
            query_text = line.split(":", 1)[-1].strip().strip("`").strip("*").strip()
            if query_text:
                results.append({
                    "dimension": current_layer or "general",
                    "reasoning": current_reasoning or "",
                    "query": query_text
                })
                current_layer = None
                current_reasoning = None

    print(f"[query_processing] Parsed {len(results)} web chain queries:")
    for item in results:
        print(f"  [{item['dimension']}] {item['query']}")

    return results


def extract_temporal_reference(query: str) -> dict:
    """
    Extract temporal reference from user query.

    Returns dict with:
        - reference_year: Year mentioned in query (e.g., 2035) or None
        - reference_period: More specific period if found (e.g., "Q1 2026", "Jan 2026")
        - is_future: Whether the reference is in the future
        - is_current: Whether query asks about "current", "now", "today"
    """
    current_year = datetime.now().year

    result = {
        "reference_year": None,
        "reference_period": None,
        "is_future": False,
        "is_current": False
    }

    # Check for "current", "now", "today" references
    current_patterns = r'\b(current|currently|now|today|present|latest|recent)\b'
    if re.search(current_patterns, query, re.IGNORECASE):
        result["is_current"] = True
        result["reference_year"] = current_year

    # Extract explicit year (4 digits, 2020-2099 range)
    year_match = re.search(r'\b(20[2-9]\d)\b', query)
    if year_match:
        year = int(year_match.group(1))
        result["reference_year"] = year
        result["is_future"] = year > current_year
        result["is_current"] = False  # Explicit year overrides "current"

    # Extract more specific period (Q1/Q2/Q3/Q4, month names)
    quarter_match = re.search(r'\b(Q[1-4])\s*(20[2-9]\d)?\b', query, re.IGNORECASE)
    if quarter_match:
        quarter = quarter_match.group(1).upper()
        year = quarter_match.group(2) or result["reference_year"]
        if year:
            result["reference_period"] = f"{quarter} {year}"

    month_match = re.search(
        r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\s*(20[2-9]\d)?\b',
        query, re.IGNORECASE
    )
    if month_match:
        month = month_match.group(1)
        year = month_match.group(2) or result["reference_year"]
        if year:
            result["reference_period"] = f"{month} {year}"

    return result
