"""
Variable Normalization Module

Matches extracted variable names against liquidity_metrics_mapping.csv
to find canonical normalized names.
This is Step 2 of the 4-step process.
"""

import sys
import json
import csv
from pathlib import Path
from datetime import datetime

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_haiku
from states import VariableMapperState
from normalization_prompts import NORMALIZATION_PROMPT
from config import LIQUIDITY_METRICS_CSV, BUGS_LOG_FILE


# Cache for CSV data
_csv_cache = None


def load_liquidity_csv():
    """
    Load and parse the liquidity_metrics_mapping.csv.
    Returns:
        - variant_to_normalized: Dict mapping each variant (lowercase) to row data
        - all_entries: List of all rows for LLM context
    """
    global _csv_cache

    if _csv_cache is not None:
        return _csv_cache

    variant_to_normalized = {}
    all_entries = []

    if not LIQUIDITY_METRICS_CSV.exists():
        print(f"[normalization] WARNING: CSV not found at {LIQUIDITY_METRICS_CSV}")
        _csv_cache = (variant_to_normalized, all_entries)
        return _csv_cache

    with open(LIQUIDITY_METRICS_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized_name = row.get('normalized', '').strip()
            variants_str = row.get('variants', '')
            category = row.get('category', '')
            is_liquidity = row.get('is_liquidity', 'false').lower() == 'true'

            # Store full row data
            entry = {
                'normalized': normalized_name,
                'variants': variants_str,
                'category': category,
                'is_liquidity': is_liquidity,
                'description': row.get('description', ''),
                'cluster': row.get('cluster', '')
            }
            all_entries.append(entry)

            # Build variant lookup (case-insensitive)
            # Map normalized name itself
            variant_to_normalized[normalized_name.lower()] = entry

            # Map each variant (pipe-separated)
            for variant in variants_str.split('|'):
                variant = variant.strip().lower()
                if variant:
                    variant_to_normalized[variant] = entry

    print(f"[normalization] Loaded {len(all_entries)} entries, {len(variant_to_normalized)} variant mappings")
    _csv_cache = (variant_to_normalized, all_entries)
    return _csv_cache


def log_unknown_variable(raw_name: str, context: str):
    """Log unknown variable to LIQUIDITY_METRICS_BUGS.md"""
    if not BUGS_LOG_FILE.exists():
        return

    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n| {today} | {raw_name} | {context[:50]}... | Consider adding to CSV |\n"

    with open(BUGS_LOG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the "Pending Issues" section and add entry
    if "## Pending Issues" in content and "(No issues logged yet)" in content:
        # First entry - replace placeholder with table
        table_header = """## Pending Issues

| Date | Raw Name | Context | Suggested Action |
|------|----------|---------|------------------|"""
        content = content.replace("## Pending Issues\n\n(No issues logged yet)", table_header + entry)
    elif "## Pending Issues" in content:
        # Add to existing table
        content = content.replace("## Pending Issues", f"## Pending Issues{entry}", 1)

    with open(BUGS_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(content)


def match_with_llm(raw_name: str, context: str, all_entries: list) -> dict:
    """Use LLM to find best match when exact match fails."""
    # Build candidate list (limit to avoid token overflow)
    candidates_lines = []
    for entry in all_entries[:100]:  # Limit candidates
        candidates_lines.append(f"{entry['normalized']} | {entry['variants'][:100]}")

    candidates_str = "\n".join(candidates_lines)

    prompt = NORMALIZATION_PROMPT.format(
        raw_name=raw_name,
        context=context or "No context",
        candidates=candidates_str
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.1, max_tokens=500)
        print(f"[normalization] LLM response for '{raw_name}':\n{response}")

        # Parse JSON response
        clean_response = response.strip()
        if clean_response.startswith("```"):
            lines = clean_response.split("\n")
            clean_response = "\n".join(lines[1:-1])

        result = json.loads(clean_response)
        return result

    except Exception as e:
        print(f"[normalization] LLM match failed for '{raw_name}': {e}")
        return {"matched_normalized_name": None, "confidence": "none"}


def normalize_variables(state: VariableMapperState) -> VariableMapperState:
    """
    Match extracted variables against CSV to find normalized names.

    Input (from State):
        - extracted_variables: List[Dict] from Step 1

    Output (to State):
        - normalized_variables: List[Dict] with normalized names
    """
    extracted = state.get("extracted_variables", [])

    if not extracted:
        print("[normalization] No extracted variables to normalize")
        return {**state, "normalized_variables": []}

    print(f"[normalization] Processing {len(extracted)} variables...")

    # Load CSV data
    variant_to_normalized, all_entries = load_liquidity_csv()

    normalized_variables = []

    for var in extracted:
        raw_name = var.get("name", "")
        context = var.get("context", "")

        # Try exact match (case-insensitive)
        lookup_key = raw_name.lower().strip()
        matched_entry = variant_to_normalized.get(lookup_key)

        if matched_entry:
            # Exact match found
            normalized_var = {
                "raw_name": raw_name,
                "normalized_name": matched_entry['normalized'],
                "category": matched_entry['category'],
                "is_liquidity": matched_entry['is_liquidity'],
                "matched_variant": lookup_key,
                "match_type": "exact",
                # Pass through extraction data
                "threshold": var.get("threshold"),
                "threshold_unit": var.get("threshold_unit"),
                "threshold_condition": var.get("threshold_condition"),
                "context": context
            }
            print(f"[normalization] Exact match: '{raw_name}' -> '{matched_entry['normalized']}'")
        else:
            # Try LLM matching
            llm_result = match_with_llm(raw_name, context, all_entries)

            if llm_result.get("matched_normalized_name"):
                # LLM found a match - look up full entry
                matched_normalized = llm_result["matched_normalized_name"]
                full_entry = variant_to_normalized.get(matched_normalized.lower(), {})

                normalized_var = {
                    "raw_name": raw_name,
                    "normalized_name": matched_normalized,
                    "category": full_entry.get('category', 'unknown'),
                    "is_liquidity": full_entry.get('is_liquidity', False),
                    "matched_variant": llm_result.get("matched_variant"),
                    "match_type": f"llm_{llm_result.get('confidence', 'unknown')}",
                    "threshold": var.get("threshold"),
                    "threshold_unit": var.get("threshold_unit"),
                    "threshold_condition": var.get("threshold_condition"),
                    "context": context
                }
                print(f"[normalization] LLM match: '{raw_name}' -> '{matched_normalized}' ({llm_result.get('confidence')})")
            else:
                # No match found - flag as unknown
                normalized_var = {
                    "raw_name": raw_name,
                    "normalized_name": None,
                    "category": "unknown",
                    "is_liquidity": False,
                    "matched_variant": None,
                    "match_type": "unmatched",
                    "threshold": var.get("threshold"),
                    "threshold_unit": var.get("threshold_unit"),
                    "threshold_condition": var.get("threshold_condition"),
                    "context": context
                }
                print(f"[normalization] No match: '{raw_name}' -> UNKNOWN")
                log_unknown_variable(raw_name, context)

        normalized_variables.append(normalized_var)

    print(f"[normalization] Normalized {len(normalized_variables)} variables")

    return {**state, "normalized_variables": normalized_variables}


# For standalone testing
if __name__ == "__main__":
    # Test with sample extracted variables
    test_state = VariableMapperState(
        extracted_variables=[
            {"name": "TGA", "context": "TGA drawdown schedule", "threshold": "500"},
            {"name": "Fed funds rate", "context": "Fed rate cuts", "threshold": None},
            {"name": "VIX", "context": "elevated vol expected", "threshold": None},
            {"name": "unknown_metric_xyz", "context": "some random context", "threshold": None}
        ]
    )

    result = normalize_variables(test_state)

    print("\n" + "=" * 50)
    print("NORMALIZED VARIABLES:")
    print("=" * 50)

    for var in result.get("normalized_variables", []):
        print(f"\n  Raw: {var.get('raw_name')}")
        print(f"  Normalized: {var.get('normalized_name')}")
        print(f"  Match type: {var.get('match_type')}")
        print(f"  Category: {var.get('category')}")
