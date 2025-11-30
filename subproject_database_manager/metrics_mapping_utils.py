"""
Utility functions for loading and updating the liquidity metrics mapping CSV.
"""

import csv
import os
import sys
from typing import List, Dict

# Add parent directory for models.py import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import call_gpt41_mini

# Default path to mapping file
DEFAULT_MAPPING_PATH = os.path.join(os.path.dirname(__file__), "data", "processed", "liquidity_metrics", "liquidity_metrics_mapping.csv")


def load_metrics_mapping(csv_path: str = None) -> str:
    """
    Load mapping CSV and format as text for prompt injection.

    Args:
        csv_path: Path to the CSV file. Uses default if not provided.

    Returns:
        Formatted string of the mapping table for LLM context.
    """
    if csv_path is None:
        csv_path = DEFAULT_MAPPING_PATH

    if not os.path.exists(csv_path):
        return "No mapping file found. Extract metrics with is_new=true for all."

    lines = ["LIQUIDITY METRICS MAPPING TABLE:", ""]
    lines.append("| Normalized Name | Known Variants | Category | Description |")
    lines.append("|-----------------|----------------|----------|-------------|")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = row.get('normalized', '')
            variants = row.get('variants', '')
            category = row.get('category', '')
            description = row.get('description', '')
            lines.append(f"| {normalized} | {variants} | {category} | {description} |")

    lines.append("")
    lines.append("INSTRUCTIONS:")
    lines.append("- If a metric matches any variant above, use the corresponding 'normalized' name")
    lines.append("- If a metric is NOT in this table, set is_new=true and suggest normalized name, category, and description")

    return "\n".join(lines)


def append_new_metrics(metrics: List[Dict], csv_path: str = None) -> List[Dict]:
    """
    Append new metrics (is_new=True) to the CSV file and update sources for existing metrics.
    Sources are additive - if a metric appears from a new data_source, that source is appended.

    Args:
        metrics: List of metric dicts from extraction output.
                Each should have: raw, normalized, is_new, suggested_category, suggested_description, sources
        csv_path: Path to the CSV file. Uses default if not provided.

    Returns:
        List of metrics that were actually added (after deduplication).
    """
    if csv_path is None:
        csv_path = DEFAULT_MAPPING_PATH

    if not metrics:
        return []

    # Load existing data for deduplication and source updates
    existing_rows = []
    existing_normalized_map = {}  # normalized.lower() -> row index

    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                existing_rows.append(row)
                existing_normalized_map[row.get('normalized', '').lower()] = i

    added_metrics = []
    sources_updated = False

    for metric in metrics:
        normalized = metric.get('normalized', '')
        normalized_lower = normalized.lower()
        new_sources = metric.get('sources', [])

        if normalized_lower in existing_normalized_map:
            # Existing metric - update sources if new ones found
            row_idx = existing_normalized_map[normalized_lower]
            existing_sources_str = existing_rows[row_idx].get('sources', '')
            existing_sources = [s.strip() for s in existing_sources_str.split('|') if s.strip()]

            # Add new sources that don't exist
            for src in new_sources:
                if src and src not in existing_sources:
                    existing_sources.append(src)
                    sources_updated = True

            existing_rows[row_idx]['sources'] = ' | '.join(existing_sources)

        elif metric.get('is_new', False):
            # New metric - add to list
            added_metrics.append(metric)
            existing_normalized_map[normalized_lower] = len(existing_rows)
            existing_rows.append({
                'normalized': normalized,
                'variants': metric.get('raw', ''),
                'category': metric.get('suggested_category', ''),
                'description': metric.get('suggested_description', ''),
                'sources': ' | '.join(new_sources) if new_sources else ''
            })

    # Rewrite file if we added new metrics or updated sources
    if added_metrics or sources_updated:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['normalized', 'variants', 'category', 'description', 'sources'])
            writer.writeheader()
            writer.writerows(existing_rows)

    return added_metrics


def collect_new_metrics_from_extractions(extractions: List[Dict]) -> List[Dict]:
    """
    Collect all metrics from a list of extraction outputs, tracking sources.
    For new metrics (is_new=True), collects them for addition to CSV.
    For existing metrics, collects sources for potential update.

    Args:
        extractions: List of extraction dicts, each containing 'liquidity_metrics' field
                    and 'data_source' field for the source attribution.

    Returns:
        List of metrics with their sources across all extractions.
    """
    metrics_with_sources = {}  # normalized -> metric dict with sources list

    for extraction in extractions:
        # Build combined source: "Institution, data_source" (e.g., "UBS, Global equity strategy")
        source = extraction.get('source', '').strip()
        data_source = extraction.get('data_source', '').strip()

        if source and data_source:
            combined_source = f"{source}, {data_source}"
        elif source:
            combined_source = source
        elif data_source:
            combined_source = data_source
        else:
            combined_source = ''

        metrics = extraction.get('liquidity_metrics', [])
        for metric in metrics:
            normalized = metric.get('normalized', '').lower()
            if not normalized:
                continue

            if normalized not in metrics_with_sources:
                # First time seeing this metric
                metric_copy = metric.copy()
                metric_copy['sources'] = [combined_source] if combined_source else []
                metrics_with_sources[normalized] = metric_copy
            else:
                # Add source if not already present
                if combined_source and combined_source not in metrics_with_sources[normalized]['sources']:
                    metrics_with_sources[normalized]['sources'].append(combined_source)

    return list(metrics_with_sources.values())


def normalize_sources_in_csv(csv_path: str = None) -> int:
    """
    Batch normalize all institution names in the sources column of the CSV.
    Runs LLM once with all unique institutions for efficiency.

    Args:
        csv_path: Path to the CSV file. Uses default if not provided.

    Returns:
        Number of sources that were normalized.
    """
    if csv_path is None:
        csv_path = DEFAULT_MAPPING_PATH

    if not os.path.exists(csv_path):
        print("No CSV file found to normalize.")
        return 0

    # Load CSV
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Extract all unique institutions from sources
    all_institutions = set()
    for row in rows:
        sources_str = row.get('sources', '')
        if not sources_str:
            continue
        for source in sources_str.split('|'):
            source = source.strip()
            if not source:
                continue
            # Extract institution (before first comma)
            parts = source.split(',', 1)
            institution = parts[0].strip()
            if institution:
                all_institutions.add(institution)

    if not all_institutions:
        print("No institutions found to normalize.")
        return 0

    print(f"Found {len(all_institutions)} unique institutions to normalize...")

    # Batch normalize with LLM
    institution_mapping = _batch_normalize_institutions(list(all_institutions))

    # Apply normalization to CSV
    changes = 0
    for row in rows:
        sources_str = row.get('sources', '')
        if not sources_str:
            continue

        new_sources = []
        for source in sources_str.split('|'):
            source = source.strip()
            if not source:
                continue

            parts = source.split(',', 1)
            institution = parts[0].strip()
            data_source = parts[1].strip() if len(parts) > 1 else ""

            # Apply normalization
            normalized_inst = institution_mapping.get(institution, institution)
            if normalized_inst != institution:
                changes += 1

            if data_source:
                new_sources.append(f"{normalized_inst}, {data_source}")
            else:
                new_sources.append(normalized_inst)

        # Deduplicate sources after normalization
        seen = set()
        deduped = []
        for s in new_sources:
            if s not in seen:
                seen.add(s)
                deduped.append(s)

        row['sources'] = ' | '.join(deduped)

    # Write back
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['normalized', 'variants', 'category', 'description', 'sources'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Normalized {changes} institution references.")
    return changes


def _batch_normalize_institutions(institutions: List[str]) -> Dict[str, str]:
    """
    Use LLM to normalize a batch of institution names to canonical forms.

    Args:
        institutions: List of institution names to normalize

    Returns:
        Dict mapping original name -> normalized name
    """
    if not institutions:
        return {}

    institutions_list = "\n".join(f"- {inst}" for inst in institutions)

    prompt = f"""Normalize these financial institution names to their canonical forms.

INPUT INSTITUTIONS:
{institutions_list}

NORMALIZATION RULES:
- GS, Goldman, GS FICC, GS FICC Desk, Goldman Sachs FICC, Goldman Sachs Global Investment Research → "Goldman Sachs"
- SocGen, Societe Generale, SG → "Societe Generale"
- UBS, UBS Global Research → "UBS"
- JPM, JP Morgan, JPMorgan Chase → "JPMorgan"
- MS, Morgan Stanley → "Morgan Stanley"
- BofA, Bank of America, BAML, Bank of America Merrill Lynch → "Bank of America"
- Citi, Citigroup, Citibank → "Citi"
- DB, Deutsche Bank → "Deutsche Bank"
- CS, Credit Suisse → "Credit Suisse"
- HSBC stays "HSBC"
- Barclays stays "Barclays"
- Bloomberg stays "Bloomberg"
- Franklin Templeton stays "Franklin Templeton"
- TS Lombard stays "TS Lombard"
- ICE BofA stays as data source, not institution
- For unknown institutions, keep original name

OUTPUT FORMAT (JSON):
Return a JSON object mapping each input institution to its normalized form.
Example: {{"GS FICC": "Goldman Sachs", "UBS": "UBS", "SocGen": "Societe Generale"}}

Output ONLY the JSON object, nothing else."""

    messages = [{"role": "user", "content": prompt}]
    result = call_gpt41_mini(messages, temperature=0, max_tokens=2000)

    # Parse JSON response
    import json
    try:
        # Clean up response if needed
        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        mapping = json.loads(result)
        print(f"LLM normalized {len(mapping)} institutions")
        return mapping
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM response: {e}")
        print(f"Raw response: {result[:500]}")
        return {inst: inst for inst in institutions}


if __name__ == "__main__":
    # Run one-time cleanup
    print("Running source normalization on metrics CSV...")
    normalize_sources_in_csv()
