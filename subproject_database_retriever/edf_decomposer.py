"""EDF (Epistemic Decomposition Framework) query decomposition.

Phase 0 of the retrieval pipeline: decomposes a query into a structured
knowledge tree that guides targeted retrieval across 7 knowledge dimensions.
"""

import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from models import call_claude_opus
from edf_decomposer_prompts import EDF_DECOMPOSITION_PROMPT


# Priority weights for scoring
PRIORITY_WEIGHTS = {"ESSENTIAL": 1.0, "IMPORTANT": 0.5, "SUPPLEMENTARY": 0.25}


def decompose_query(query: str) -> dict:
    """
    Decompose a research query into an EDF knowledge tree.

    Single Opus call that extracts keywords and produces per-keyword
    decomposition across 7 knowledge types.

    Returns:
        {
            "keywords": [
                {
                    "id": "K1",
                    "keyword": "...",
                    "why_extracted": "...",
                    "items": [
                        {
                            "id": "T1.01",
                            "knowledge_type": "...",
                            "description": "...",
                            "priority": "ESSENTIAL|IMPORTANT|SUPPLEMENTARY",
                            "source_hint": "research_db|web_search|data_api|parametric",
                            "searchable_query": "..."
                        }
                    ]
                }
            ]
        }
    """
    from shared.debug_logger import debug_log
    print(f"\n[EDF Decomposer] Decomposing query: {query[:100]}...")

    prompt = EDF_DECOMPOSITION_PROMPT.format(query=query)

    response = call_claude_opus(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=8000,
    )

    print(f"[EDF Decomposer] Raw response length: {len(response)} chars")
    debug_log("EDF_DECOMPOSER", f"Raw response:\n{response}")

    tree = _parse_knowledge_tree(response)

    if tree and tree.get("keywords"):
        _print_tree_summary(tree)
    else:
        print("[EDF Decomposer] WARNING: Failed to parse knowledge tree, returning empty tree")
        tree = {"keywords": []}

    return tree


def _parse_knowledge_tree(response: str) -> dict:
    """Parse JSON knowledge tree from Opus response."""
    # Try direct JSON parse first
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the outermost JSON object
    # Find first { and last }
    first_brace = response.find('{')
    last_brace = response.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(response[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


def _print_tree_summary(tree: dict):
    """Print a summary of the knowledge tree."""
    keywords = tree.get("keywords", [])
    total_items = sum(len(kw.get("items", [])) for kw in keywords)

    print(f"\n[EDF Decomposer] Knowledge tree: {len(keywords)} keywords, {total_items} items")

    priority_counts = {"ESSENTIAL": 0, "IMPORTANT": 0, "SUPPLEMENTARY": 0}
    source_counts = {}
    type_counts = {}

    for kw in keywords:
        kw_id = kw.get("id", "?")
        items = kw.get("items", [])
        print(f"  {kw_id}: {kw.get('keyword', '?')} ({len(items)} items)")
        for item in items:
            p = item.get("priority", "UNKNOWN")
            priority_counts[p] = priority_counts.get(p, 0) + 1
            s = item.get("source_hint", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1
            t = item.get("knowledge_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

    max_score = sum(
        PRIORITY_WEIGHTS.get(item.get("priority", ""), 0)
        for kw in keywords
        for item in kw.get("items", [])
    )

    print(f"\n  Priority: {priority_counts}")
    print(f"  Sources: {source_counts}")
    print(f"  Types: {type_counts}")
    print(f"  Max weighted score: {max_score:.1f}")


def get_data_api_items(tree: dict) -> list:
    """Extract items with source_hint='data_api' from EDF tree.

    Used by Phase 2 (data grounding) to know which variables to prioritize.
    """
    items = []
    for kw in tree.get("keywords", []):
        for item in kw.get("items", []):
            if item.get("source_hint") == "data_api":
                items.append(item)
    return items


def get_historical_items(tree: dict) -> list:
    """Extract items with knowledge_type='historical_analogs' from EDF tree.

    Used by Phase 3 (historical context) to know which precedents to search for.
    """
    items = []
    for kw in tree.get("keywords", []):
        for item in kw.get("items", []):
            if item.get("knowledge_type") == "historical_analogs":
                items.append(item)
    return items


def get_query_type_hint(tree: dict) -> str:
    """Determine if query is indicator-driven or event-driven from EDF item distribution.

    Used by Phase 3 to choose between find_indicator_extremes path vs detect_analogs path.
    Heuristic: if data_api items >= 2, the query centers on specific indicators.
    """
    data_api_count = 0
    for kw in tree.get("keywords", []):
        for item in kw.get("items", []):
            if item.get("source_hint") == "data_api":
                data_api_count += 1
    return "indicator-driven" if data_api_count >= 2 else "event-driven"


def get_search_plan(tree: dict) -> dict:
    """
    Extract a search plan from the knowledge tree, grouped by source_hint.

    Returns:
        {
            "research_db": [{"id": "T1.01", "query": "...", "priority": "..."}, ...],
            "web_search": [...],
            "data_api": [...],
            "parametric": [...]
        }
    """
    plan = {
        "research_db": [],
        "web_search": [],
        "data_api": [],
        "parametric": [],
    }

    for kw in tree.get("keywords", []):
        for item in kw.get("items", []):
            source = item.get("source_hint", "web_search")
            entry = {
                "id": item.get("id", ""),
                "query": item.get("searchable_query", item.get("description", "")),
                "priority": item.get("priority", "IMPORTANT"),
                "description": item.get("description", ""),
                "knowledge_type": item.get("knowledge_type", ""),
            }
            if source in plan:
                plan[source].append(entry)
            else:
                plan["web_search"].append(entry)

    return plan


def format_search_plan_for_agent(tree: dict) -> str:
    """Format the knowledge tree as a search plan for the retrieval agent's initial message."""
    plan = get_search_plan(tree)

    lines = []

    # Research DB queries (for Pinecone)
    if plan["research_db"]:
        lines.append("## Pinecone Database Queries (use search_pinecone)")
        essential = [q for q in plan["research_db"] if q["priority"] == "ESSENTIAL"]
        important = [q for q in plan["research_db"] if q["priority"] == "IMPORTANT"]
        for q in essential:
            lines.append(f"  [ESSENTIAL] {q['id']}: {q['query']}")
        for q in important:
            lines.append(f"  [IMPORTANT] {q['id']}: {q['query']}")

    # Web search queries
    if plan["web_search"]:
        lines.append("\n## Web Queries (use web_search or extract_web_chains)")
        essential = [q for q in plan["web_search"] if q["priority"] == "ESSENTIAL"]
        important = [q for q in plan["web_search"] if q["priority"] == "IMPORTANT"]
        for q in essential:
            lines.append(f"  [ESSENTIAL] {q['id']}: {q['query']}")
        for q in important:
            lines.append(f"  [IMPORTANT] {q['id']}: {q['query']}")

    # Data API items (deferred)
    if plan["data_api"]:
        data_items = ", ".join(q["query"] for q in plan["data_api"][:5])
        lines.append(f"\n## Data API Items (deferred to Phase 2): {data_items}")

    # Parametric items (no retrieval needed)
    if plan["parametric"]:
        lines.append(f"\n## Parametric Knowledge (no retrieval needed): {len(plan['parametric'])} items")

    return "\n".join(lines)


def format_tree_items_for_scoring(tree: dict) -> str:
    """Format the knowledge tree items for the coverage scoring prompt.

    Excludes data_api and parametric items — those are filled in Phase 2
    (data grounding) or already known by the LLM. Phase 1 coverage scoring
    should only assess what retrieval (Pinecone + web) can provide.
    """
    lines = []
    skipped = 0

    for kw in tree.get("keywords", []):
        kw_id = kw.get("id", "?")
        kw_items = []
        for item in kw.get("items", []):
            source = item.get("source_hint", "?")
            if source in ("data_api", "parametric"):
                skipped += 1
                continue
            item_id = item.get("id", "?")
            priority = item.get("priority", "?")
            ktype = item.get("knowledge_type", "?")
            desc = item.get("description", "?")
            kw_items.append(f"  {item_id} [{priority}] ({ktype}, {source}): {desc}")
        if kw_items:
            lines.append(f"\n### {kw_id}: {kw.get('keyword', '?')}")
            lines.extend(kw_items)

    if skipped:
        lines.append(f"\n(Excluded {skipped} data_api/parametric items — filled in later phases)")

    return "\n".join(lines)


def compute_coverage_score(tree: dict, scores: dict) -> dict:
    """
    Compute a weighted coverage score from item-level scores.

    Args:
        tree: The knowledge tree
        scores: {item_id: "Y"|"P"|"N"} mapping

    Returns:
        {
            "score": float,
            "max_score": float,
            "percentage": float,
            "essential_gaps": [item_ids],
            "important_gaps": [item_ids],
            "by_type": {knowledge_type: {"covered": int, "total": int}},
        }
    """
    score_map = {"Y": 1.0, "P": 0.5, "N": 0.0}

    total_score = 0.0
    max_score = 0.0
    essential_gaps = []
    important_gaps = []
    by_type = {}

    for kw in tree.get("keywords", []):
        for item in kw.get("items", []):
            # Skip data_api and parametric items — filled in later phases
            source = item.get("source_hint", "")
            if source in ("data_api", "parametric"):
                continue

            item_id = item.get("id", "")
            priority = item.get("priority", "IMPORTANT")
            ktype = item.get("knowledge_type", "unknown")
            weight = PRIORITY_WEIGHTS.get(priority, 0.5)

            item_score_str = scores.get(item_id, "N")
            item_score = score_map.get(item_score_str, 0.0)

            total_score += weight * item_score
            max_score += weight

            # Track gaps
            if item_score_str == "N":
                if priority == "ESSENTIAL":
                    essential_gaps.append(item_id)
                elif priority == "IMPORTANT":
                    important_gaps.append(item_id)

            # By type tracking
            if ktype not in by_type:
                by_type[ktype] = {"covered": 0, "partial": 0, "missing": 0, "total": 0}
            by_type[ktype]["total"] += 1
            if item_score_str == "Y":
                by_type[ktype]["covered"] += 1
            elif item_score_str == "P":
                by_type[ktype]["partial"] += 1
            else:
                by_type[ktype]["missing"] += 1

    percentage = (total_score / max_score * 100) if max_score > 0 else 0

    return {
        "score": round(total_score, 2),
        "max_score": round(max_score, 2),
        "percentage": round(percentage, 1),
        "essential_gaps": essential_gaps,
        "important_gaps": important_gaps,
        "by_type": by_type,
    }
