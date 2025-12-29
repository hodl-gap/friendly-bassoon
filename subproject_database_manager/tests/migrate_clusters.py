"""
One-time migration script to assign clusters to existing metrics.
Adds 'cluster' and 'raw_data_source' columns to liquidity_metrics_mapping.csv.

Usage:
    python tests/migrate_clusters.py

This script:
1. Loads all existing metrics from CSV
2. Extracts raw_data_source from existing 'sources' column
3. Uses LLM to batch-assign clusters
4. Writes updated CSV with new columns
"""

import csv
import sys
import os

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics_mapping_utils import (
    DEFAULT_MAPPING_PATH,
    assign_clusters_batch
)


def extract_raw_data_source(sources_str: str) -> str:
    """
    Extract raw_data_source from sources column.
    Format is "Institution, data_source" - we want the data_source part.
    Uses first source if multiple (pipe-delimited).
    """
    if not sources_str:
        return ''

    # Get first source
    first_source = sources_str.split('|')[0].strip()

    # Extract data_source (after first comma)
    parts = first_source.split(',', 1)
    if len(parts) > 1:
        return parts[1].strip()

    return ''


def load_existing_metrics(csv_path: str) -> list:
    """Load all metrics from CSV."""
    metrics = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            metrics.append(row)
    return metrics


def migrate_clusters():
    """Main migration function."""
    print("=" * 60)
    print("CLUSTER MIGRATION FOR LIQUIDITY METRICS")
    print("=" * 60)

    # Check if CSV exists
    if not os.path.exists(DEFAULT_MAPPING_PATH):
        print(f"Error: CSV not found at {DEFAULT_MAPPING_PATH}")
        return

    # Load existing metrics
    print("\nStep 1: Loading existing metrics...")
    metrics = load_existing_metrics(DEFAULT_MAPPING_PATH)
    print(f"  Found {len(metrics)} metrics to process")

    # Check if already migrated
    if metrics and 'cluster' in metrics[0] and metrics[0].get('cluster'):
        print("  Warning: cluster column already exists and has values")
        response = input("  Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("  Aborted.")
            return

    # Extract raw_data_source from existing sources column
    print("\nStep 2: Extracting raw_data_source from sources column...")
    for metric in metrics:
        raw_data_source = extract_raw_data_source(metric.get('sources', ''))
        metric['raw_data_source'] = raw_data_source

    sources_count = sum(1 for m in metrics if m.get('raw_data_source'))
    print(f"  Extracted raw_data_source for {sources_count}/{len(metrics)} metrics")

    # Batch assign clusters via LLM
    print("\nStep 3: Assigning clusters via LLM...")
    print("  This may take a few minutes...")

    # Prepare metrics for assignment (need normalized and description)
    metrics_for_assignment = [
        {
            'normalized': m.get('normalized', ''),
            'description': m.get('description', ''),
            'category': m.get('category', '')
        }
        for m in metrics
    ]

    assignments = assign_clusters_batch(metrics_for_assignment, batch_size=50)

    # Apply assignments to metrics
    for metric in metrics:
        normalized = metric.get('normalized', '')
        metric['cluster'] = assignments.get(normalized, 'uncategorized')

    # Write updated CSV
    print("\nStep 4: Writing updated CSV...")
    fieldnames = ['normalized', 'variants', 'category', 'description', 'sources', 'cluster', 'raw_data_source']

    with open(DEFAULT_MAPPING_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metrics)

    print(f"  Written {len(metrics)} metrics to {DEFAULT_MAPPING_PATH}")

    # Print summary
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)

    # Cluster distribution
    cluster_counts = {}
    for m in metrics:
        c = m.get('cluster', 'uncategorized')
        cluster_counts[c] = cluster_counts.get(c, 0) + 1

    print("\nCluster distribution:")
    for cluster, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
        print(f"  {cluster}: {count}")

    print(f"\nTotal clusters: {len(cluster_counts)}")
    print(f"Total metrics: {len(metrics)}")


if __name__ == "__main__":
    migrate_clusters()
