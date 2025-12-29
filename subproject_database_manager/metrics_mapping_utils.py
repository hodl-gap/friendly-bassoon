"""
Utility functions for loading and updating the liquidity metrics mapping CSV.
Includes cluster assignment for grouping related metrics.
"""

import csv
import json
import os
import re
import sys
from typing import List, Dict, Optional

# Add parent directory for models.py import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import call_gpt41_mini
from cluster_assignment_prompts import get_cluster_assignment_prompt, get_batch_cluster_assignment_prompt
from metrics_mapping_prompts import get_institution_normalization_prompt


# =============================================================================
# VALIDATION PATTERNS AND CONSTANTS
# =============================================================================

# Patterns that indicate a metric is NOT a liquidity metric
NON_LIQUIDITY_PATTERNS = [
    r'_price_QoQ$',           # Substrate pricing
    r'^ABF_',                 # ABF substrate
    r'^T-glass',              # T-glass materials
    r'_CCL_share',            # PCB market share
    r'_PCB_share',            # PCB market share
    r'_TPU_',                 # TPU metrics
    r'_return$',              # Daily ETF returns
    r'^IPO_',                 # IPO metrics
    r'^revenue',              # Company revenue
    r'^net_loss',             # Company losses
    r'^PSR$',                 # Valuation metric
    r'battery_order',         # Battery metrics
    r'Election probability',  # Political
    r'M&A_Netflix',           # M&A events
    r'headcount_hiring',      # Hiring
    r'^BT_price',             # BT substrate
    r'unmet_orders',          # Supply chain
    r'ABF_shortage',          # Supply chain
    r'ABF_utilization',       # Supply chain
    r'^EMC_',                 # Market share
    r'^TUC_',                 # Market share
    r'^GCE_',                 # Market share
    r'^Google_TPU',           # TPU orders
    r'^META_ASIC',            # ASIC metrics
    r'^DIA_return',           # Daily returns
    r'^SPY_return',           # Daily returns
    r'^QQQ_return',           # Daily returns
    r'^IWM_return',           # Daily returns
    r'^TLT_return',           # Daily returns
    r'^IEF_return',           # Daily returns
    r'^SHY_return',           # Daily returns
    r'^MJ_return',            # Daily returns
    r'^KWEB_return',          # Daily returns
    r'^XLE_return',           # Daily returns
    r'^IBIT_return',          # Daily returns
    r'Reality Labs',          # Company fundamentals
    r'^chip_performance',     # Chip performance
    r'^service_pricing',      # Service pricing
    r'^Foundry growth',       # Company fundamentals
    r'^OpenAI',               # Company fundamentals
    r'^Anthropic',            # Company fundamentals
    r'^MongoDB',              # Company fundamentals
    r'^company_revenue',      # Fundamentals
    r'^Atlas growth',         # Fundamentals
    r'^headcount',            # Hiring
    r'^funding_valuation',    # Funding
    r'^M&A_value',            # M&A
    r'^asset_sale',           # Asset sales
    r'^Goldman_acquisition',  # M&A
    r'^Uber cumulative',      # Company losses
    r'^historical tech',      # Benchmarks
    r'^data_center_project',  # CapEx
    r'^IPO_net_proceeds',     # IPO
    r'^Nvidia data-center',   # Company revenue
    r'^Capex.*bigtech',       # CapEx
    r'^government grant',     # Grants
    r'^large equity stake',   # Equity sales
    r'^crypto market cap',    # Crypto
    r'^silver_price',         # Commodity price
    r'^gold_price',           # Commodity price
    r'^Listing Date',         # Listing
]

# Keyword blocklist for description-based filtering
NON_LIQUIDITY_KEYWORDS = [
    'substrate', 'PCB', 'CCL', 'semiconductor price', 'DRAM price',
    'IPO proceeds', 'revenue growth', 'net loss', 'earnings', 'EPS',
    'battery order', 'election', 'hiring', 'headcount', 'M&A deal',
    'daily return', 'intraday return', 'stock performance',
]


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_metric_name(name: str) -> str:
    """
    Normalize metric name to snake_case format.

    Rules:
    - Convert to lowercase
    - Replace spaces/hyphens with underscores
    - Remove special characters
    - Remove consecutive underscores
    - Truncate to 40 characters

    Args:
        name: Raw metric name

    Returns:
        Normalized snake_case name
    """
    if not name:
        return ''

    # Replace spaces and hyphens with underscores
    name = name.replace(' ', '_')
    name = name.replace('-', '_')

    # Handle camelCase -> snake_case
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)

    # Remove special characters except underscores
    name = re.sub(r'[^\w_]', '', name)

    # Convert to lowercase
    name = name.lower()

    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)

    # Remove leading/trailing underscores
    name = name.strip('_')

    # Truncate to 40 chars
    if len(name) > 40:
        name = name[:40]

    return name


def is_liquidity_metric(metric: Dict) -> bool:
    """
    Check if a metric is actually a liquidity metric (not company fundamentals, etc.)

    Uses pattern matching on normalized name and keyword matching on description.

    Args:
        metric: Dict with normalized, suggested_description, suggested_category

    Returns:
        True if this appears to be a legitimate liquidity metric
    """
    normalized = metric.get('normalized', '')
    description = metric.get('suggested_description', '')

    # Check name against non-liquidity patterns
    for pattern in NON_LIQUIDITY_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return False

    # Check description against keyword blocklist
    description_lower = description.lower()
    for keyword in NON_LIQUIDITY_KEYWORDS:
        if keyword.lower() in description_lower:
            # Allow if it's clearly about market liquidity
            if 'liquidity' in description_lower or 'flow' in description_lower:
                continue
            return False

    return True


def fuzzy_match_metric(new_normalized: str, existing_rows: List[Dict]) -> Optional[str]:
    """
    Check if a new metric fuzzy-matches an existing one.

    Checks:
    1. Exact match on normalized name (case-insensitive)
    2. Match in variants column
    3. Word overlap > 70%
    4. Levenshtein distance < 3 for short names

    Args:
        new_normalized: The new metric's normalized name
        existing_rows: List of existing CSV rows

    Returns:
        Existing normalized name if match found, else None
    """
    if not new_normalized:
        return None

    new_lower = new_normalized.lower()
    new_words = set(new_lower.replace('_', ' ').split())

    for row in existing_rows:
        existing_normalized = row.get('normalized', '')
        existing_lower = existing_normalized.lower()

        # 1. Exact match
        if new_lower == existing_lower:
            return existing_normalized

        # 2. Check variants column
        variants = row.get('variants', '')
        if variants:
            for variant in variants.split('|'):
                variant = variant.strip().lower()
                if new_lower in variant or variant in new_lower:
                    return existing_normalized

        # 3. Word overlap check
        existing_words = set(existing_lower.replace('_', ' ').split())
        if new_words and existing_words:
            overlap = len(new_words & existing_words)
            total = len(new_words | existing_words)
            if total > 0 and overlap / total > 0.7:
                return existing_normalized

        # 4. Levenshtein distance for short names (< 15 chars)
        if len(new_lower) < 15 and len(existing_lower) < 15:
            dist = _levenshtein_distance(new_lower, existing_lower)
            if dist <= 2:
                return existing_normalized

    return None


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

# Default path to mapping file
DEFAULT_MAPPING_PATH = os.path.join(os.path.dirname(__file__), "data", "processed", "liquidity_metrics", "liquidity_metrics_mapping.csv")


def load_metrics_mapping(csv_path: str = None) -> str:
    """
    Load mapping CSV and format as text for prompt injection.
    Includes cluster column for grouping context.

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
    lines.append("| Normalized Name | Known Variants | Category | Description | Cluster |")
    lines.append("|-----------------|----------------|----------|-------------|---------|")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = row.get('normalized', '')
            variants = row.get('variants', '')
            category = row.get('category', '')
            description = row.get('description', '')
            cluster = row.get('cluster', '')
            lines.append(f"| {normalized} | {variants} | {category} | {description} | {cluster} |")

    lines.append("")
    lines.append("INSTRUCTIONS:")
    lines.append("- If a metric matches any variant above, use the corresponding 'normalized' name")
    lines.append("- If a metric is NOT in this table, set is_new=true and suggest normalized name, category, description, and cluster")

    return "\n".join(lines)


def get_existing_clusters(csv_path: str = None) -> List[str]:
    """
    Extract unique cluster names from existing CSV.

    Args:
        csv_path: Path to the CSV file. Uses default if not provided.

    Returns:
        List of unique cluster names.
    """
    if csv_path is None:
        csv_path = DEFAULT_MAPPING_PATH

    if not os.path.exists(csv_path):
        return []

    clusters = set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cluster = row.get('cluster', '').strip()
            if cluster:
                clusters.add(cluster)

    return sorted(list(clusters))


def assign_cluster_to_metric(metric: Dict, existing_clusters: List[str] = None) -> str:
    """
    Use LLM to assign a cluster to a single new metric.

    Args:
        metric: Dict with normalized, description, category, sources
        existing_clusters: List of existing cluster names (optional, will load if not provided)

    Returns:
        Cluster name string.
    """
    if existing_clusters is None:
        existing_clusters = get_existing_clusters()

    prompt = get_cluster_assignment_prompt(metric, existing_clusters)
    messages = [{"role": "user", "content": prompt}]

    try:
        result = call_gpt41_mini(messages, temperature=0, max_tokens=500)
        result = result.strip()

        # Parse JSON response
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]

        assignment = json.loads(result)
        cluster = assignment.get('cluster', 'uncategorized')
        print(f"  Assigned cluster '{cluster}' to metric '{metric.get('normalized', '')}'")
        return cluster

    except (json.JSONDecodeError, Exception) as e:
        print(f"  Failed to assign cluster for '{metric.get('normalized', '')}': {e}")
        return 'uncategorized'


def assign_clusters_batch(metrics: List[Dict], batch_size: int = 50) -> Dict[str, str]:
    """
    Batch assign clusters to multiple metrics using LLM.
    More efficient for migration of existing metrics.

    Args:
        metrics: List of metric dicts with normalized, description, category
        batch_size: Number of metrics to process per LLM call

    Returns:
        Dict mapping normalized name -> cluster name.
    """
    if not metrics:
        return {}

    all_assignments = {}
    existing_clusters = get_existing_clusters()

    # Seed with common clusters if none exist
    if not existing_clusters:
        existing_clusters = [
            'CTA_positioning', 'ETF_flows', 'Fed_balance_sheet', 'FX_liquidity',
            'credit_spreads', 'equity_flows', 'volatility_metrics', 'positioning_leverage',
            'rate_expectations', 'corporate_fundamentals', 'macro_indicators'
        ]

    # Process in batches
    for i in range(0, len(metrics), batch_size):
        batch = metrics[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(metrics) + batch_size - 1) // batch_size
        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} metrics)...")

        prompt = get_batch_cluster_assignment_prompt(batch, existing_clusters)
        messages = [{"role": "user", "content": prompt}]

        try:
            result = call_gpt41_mini(messages, temperature=0, max_tokens=4000)
            result = result.strip()

            # Parse JSON response
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]

            assignments = json.loads(result)

            for assignment in assignments:
                idx = assignment.get('metric_index', 0) - 1
                if 0 <= idx < len(batch):
                    metric_name = batch[idx].get('normalized', '')
                    cluster = assignment.get('cluster', 'uncategorized')
                    all_assignments[metric_name] = cluster

                    # Track new clusters
                    if cluster and cluster not in existing_clusters:
                        existing_clusters.append(cluster)

        except (json.JSONDecodeError, Exception) as e:
            print(f"  Failed to parse batch {batch_num}: {e}")
            # Assign uncategorized to failed batch
            for m in batch:
                all_assignments[m.get('normalized', '')] = 'uncategorized'

    print(f"  Assigned clusters to {len(all_assignments)} metrics")
    return all_assignments


def append_new_metrics(metrics: List[Dict], csv_path: str = None) -> List[Dict]:
    """
    Append new metrics (is_new=True) to the CSV file and update sources for existing metrics.
    Sources are additive - if a metric appears from a new data_source, that source is appended.
    New metrics are assigned a cluster via LLM if not provided.

    Args:
        metrics: List of metric dicts from extraction output.
                Each should have: raw, normalized, is_new, suggested_category, suggested_description, sources
                Optionally: suggested_cluster, raw_data_source
        csv_path: Path to the CSV file. Uses default if not provided.

    Returns:
        List of metrics that were actually added (after deduplication).
    """
    if csv_path is None:
        csv_path = DEFAULT_MAPPING_PATH

    if not metrics:
        return []

    # Define fieldnames with new columns (including is_liquidity)
    fieldnames = ['normalized', 'variants', 'category', 'description', 'sources', 'cluster', 'raw_data_source', 'is_liquidity']

    # Load existing data for deduplication and source updates
    existing_rows = []
    existing_normalized_map = {}  # normalized.lower() -> row index

    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                # Ensure new columns exist for backward compatibility
                if 'cluster' not in row:
                    row['cluster'] = ''
                if 'raw_data_source' not in row:
                    row['raw_data_source'] = ''
                if 'is_liquidity' not in row:
                    row['is_liquidity'] = 'true'  # Default to true for legacy entries
                existing_rows.append(row)
                existing_normalized_map[row.get('normalized', '').lower()] = i

    # Get existing clusters for assignment context
    existing_clusters = get_existing_clusters(csv_path)

    added_metrics = []
    skipped_non_liquidity = []
    skipped_fuzzy_match = []
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
            # === VALIDATION STEP 1: Check if it's actually a liquidity metric ===
            if not is_liquidity_metric(metric):
                skipped_non_liquidity.append(normalized)
                print(f"  Skipped non-liquidity metric: {normalized}")
                continue

            # === VALIDATION STEP 2: Check for fuzzy duplicates ===
            existing_match = fuzzy_match_metric(normalized, existing_rows)
            if existing_match:
                # Treat as existing metric - just update sources
                row_idx = existing_normalized_map.get(existing_match.lower())
                if row_idx is not None:
                    existing_sources_str = existing_rows[row_idx].get('sources', '')
                    existing_sources = [s.strip() for s in existing_sources_str.split('|') if s.strip()]
                    for src in new_sources:
                        if src and src not in existing_sources:
                            existing_sources.append(src)
                            sources_updated = True
                    existing_rows[row_idx]['sources'] = ' | '.join(existing_sources)
                skipped_fuzzy_match.append((normalized, existing_match))
                print(f"  Fuzzy matched '{normalized}' -> '{existing_match}'")
                continue

            # === VALIDATION STEP 3: Normalize the metric name ===
            normalized = validate_metric_name(normalized)
            normalized_lower = normalized.lower()

            # Double-check after normalization that it's not a duplicate
            if normalized_lower in existing_normalized_map:
                row_idx = existing_normalized_map[normalized_lower]
                existing_sources_str = existing_rows[row_idx].get('sources', '')
                existing_sources = [s.strip() for s in existing_sources_str.split('|') if s.strip()]
                for src in new_sources:
                    if src and src not in existing_sources:
                        existing_sources.append(src)
                        sources_updated = True
                existing_rows[row_idx]['sources'] = ' | '.join(existing_sources)
                continue

            # New metric - assign cluster if not provided
            cluster = metric.get('suggested_cluster', '')
            if not cluster:
                cluster = assign_cluster_to_metric(metric, existing_clusters)
                if cluster and cluster not in existing_clusters:
                    existing_clusters.append(cluster)

            # Get raw_data_source from metric
            raw_data_source = metric.get('raw_data_source', '')

            added_metrics.append(metric)
            existing_normalized_map[normalized_lower] = len(existing_rows)
            existing_rows.append({
                'normalized': normalized,
                'variants': metric.get('raw', ''),
                'category': metric.get('suggested_category', ''),
                'description': metric.get('suggested_description', ''),
                'sources': ' | '.join(new_sources) if new_sources else '',
                'cluster': cluster,
                'raw_data_source': raw_data_source,
                'is_liquidity': 'true'  # New metrics are validated as liquidity metrics
            })

    # Print summary of validation
    if skipped_non_liquidity:
        print(f"  Skipped {len(skipped_non_liquidity)} non-liquidity metrics")
    if skipped_fuzzy_match:
        print(f"  Merged {len(skipped_fuzzy_match)} fuzzy-matched metrics")

    # Rewrite file if we added new metrics or updated sources
    if added_metrics or sources_updated:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_rows)

    return added_metrics


def collect_new_metrics_from_extractions(extractions: List[Dict]) -> List[Dict]:
    """
    Collect all metrics from a list of extraction outputs, tracking sources.
    For new metrics (is_new=True), collects them for addition to CSV.
    For existing metrics, collects sources for potential update.
    Also captures raw_data_source for data reproduction purposes.

    Args:
        extractions: List of extraction dicts, each containing 'liquidity_metrics' field
                    and 'data_source' field for the source attribution.

    Returns:
        List of metrics with their sources and raw_data_source across all extractions.
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
                # Capture raw_data_source from extraction's data_source field
                metric_copy['raw_data_source'] = data_source
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

    # Write back with all columns including new ones
    fieldnames = ['normalized', 'variants', 'category', 'description', 'sources', 'cluster', 'raw_data_source', 'is_liquidity']
    # Ensure all rows have the new columns
    for row in rows:
        if 'cluster' not in row:
            row['cluster'] = ''
        if 'raw_data_source' not in row:
            row['raw_data_source'] = ''
        if 'is_liquidity' not in row:
            row['is_liquidity'] = 'true'

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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

    prompt = get_institution_normalization_prompt(institutions)

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
