"""
Prompts for Variable Normalization Module
"""

# Main prompt for matching a variable to the canonical list
NORMALIZATION_PROMPT = """You are matching a financial variable name to a canonical list of known metrics.

VARIABLE TO MATCH: {raw_name}
CONTEXT: {context}

CANDIDATE LIST (format: normalized_name | variants):
{candidates}

INSTRUCTIONS:
1. Find the BEST match from the candidate list based on semantic similarity
2. Consider abbreviations, synonyms, and related terms
3. The variable might be expressed differently (e.g., "Treasury General Account" = "TGA")
4. If no good match exists, return null

Return ONLY a JSON object:
{{
    "matched_normalized_name": "the_normalized_name_from_list_or_null",
    "matched_variant": "which_variant_matched_or_null",
    "confidence": "high" | "medium" | "low" | "none"
}}

Examples:
- "TGA" matches "tga" with high confidence
- "Treasury balance" might match "tga" with medium confidence
- "random_metric_xyz" has no match, return null with confidence "none"

Return ONLY the JSON, no additional text."""
