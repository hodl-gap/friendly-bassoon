"""
Post-mortem enrichment script for data_opinion entries.

This script:
1. Finds data_opinion entries with ambiguous metrics (empty value/direction)
2. Collects data_updates from the last 7 days as context
3. Calls LLM to fill in exact numbers/direction
4. Updates the processed CSV

Usage:
    python tests/enrich_data_opinions.py --input data/processed/processed_xxx.csv
    python tests/enrich_data_opinions.py --input data/processed/processed_xxx.csv --execute
"""

import sys
import os
import csv
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(PROJECT_DIR)
sys.path.append(os.path.dirname(PROJECT_DIR))

from models import call_gpt41_mini
from metrics_mapping_utils import append_new_metrics


def load_processed_csv(csv_path):
    """Load processed CSV into list of dicts"""
    entries = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)
    return entries


def save_processed_csv(csv_path, entries, fieldnames):
    """Save entries back to CSV"""
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)


def is_ambiguous(entry):
    """
    Check if a data_opinion entry needs enrichment.

    Needs enrichment if:
    1. liquidity_metrics is empty but logic_chains mention data
    2. liquidity_metrics has entries with empty value/direction
    3. used_data is empty but logic_chains exist
    """
    if entry.get('category') != 'data_opinion':
        return False

    if not entry.get('extracted_data'):
        return False

    try:
        extracted = json.loads(entry['extracted_data'])
    except json.JSONDecodeError:
        return False

    metrics = extracted.get('liquidity_metrics', [])
    logic_chains = extracted.get('logic_chains', [])
    used_data = extracted.get('used_data', '')

    # Case 1: Empty metrics but has logic chains (missing numeric context)
    if not metrics and logic_chains:
        return True

    # Case 2: Empty used_data but has logic chains
    if not used_data and logic_chains:
        return True

    # Case 3: Metrics with empty value or direction
    for metric in metrics:
        if not metric.get('value') or not metric.get('direction'):
            return True

    return False


def get_data_updates_context(entries, target_date, days_back=7):
    """
    Get data_update entries from the last N days as context.

    Args:
        entries: All entries from the CSV
        target_date: Date of the target entry (ISO format)
        days_back: Number of days to look back

    Returns:
        List of data_update raw texts
    """
    try:
        # Parse target date (handle various formats)
        if 'T' in target_date:
            target_dt = datetime.fromisoformat(target_date.replace('Z', '+00:00'))
        else:
            target_dt = datetime.strptime(target_date[:10], '%Y-%m-%d')
    except:
        return []

    start_dt = target_dt - timedelta(days=days_back)

    context = []
    for entry in entries:
        if entry.get('category') != 'data_update':
            continue

        try:
            entry_date = entry.get('date', '')
            if 'T' in entry_date:
                entry_dt = datetime.fromisoformat(entry_date.replace('Z', '+00:00'))
            else:
                entry_dt = datetime.strptime(entry_date[:10], '%Y-%m-%d')
        except:
            continue

        if start_dt <= entry_dt <= target_dt:
            context.append({
                'date': entry_date,
                'text': entry.get('raw_text', '')
            })

    # Sort by date
    context.sort(key=lambda x: x['date'])

    return context


def build_enrichment_prompt(entry, context):
    """Build prompt for LLM enrichment"""
    extracted = json.loads(entry['extracted_data'])

    context_str = "\n\n".join([
        f"[{c['date']}]\n{c['text']}" for c in context
    ]) if context else "No recent data updates available."

    return f"""You are enriching a data_opinion extraction with exact numbers from recent data.

## Original Extraction:
{json.dumps(extracted, indent=2, ensure_ascii=False)}

## Recent Data Updates (last 7 days):
{context_str}

## Original Message:
{entry.get('raw_text', '')}

## Task:
Look at the liquidity_metrics in the extraction. For any metric with empty "value" or "direction":
1. Find the relevant numbers from the recent data updates
2. Fill in the exact values and direction

Return the UPDATED extraction JSON with filled-in values. Only modify the liquidity_metrics fields.

**Output (JSON only, no markdown):**"""


def enrich_entry(entry, context):
    """Call LLM to enrich a single entry"""
    prompt = build_enrichment_prompt(entry, context)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_gpt41_mini(messages)

        # Parse response
        response_text = response.strip()
        if response_text.startswith("```"):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        enriched = json.loads(response_text)
        return enriched
    except Exception as e:
        print(f"    Error enriching entry: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Enrich data_opinion entries with exact numbers')
    parser.add_argument('--input', required=True, help='Path to processed CSV')
    parser.add_argument('--execute', action='store_true', help='Actually apply changes (default: dry run)')
    parser.add_argument('--days', type=int, default=7, help='Days of context to use (default: 7)')
    args = parser.parse_args()

    csv_path = Path(args.input)
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        return

    print("=" * 60)
    print("DATA OPINION ENRICHMENT")
    print("=" * 60)
    print(f"Input: {csv_path}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Context window: {args.days} days")
    print()

    # Load entries
    entries = load_processed_csv(csv_path)
    print(f"Loaded {len(entries)} entries")

    # Find ambiguous entries
    ambiguous = [(i, e) for i, e in enumerate(entries) if is_ambiguous(e)]
    print(f"Found {len(ambiguous)} ambiguous data_opinion entries")

    if not ambiguous:
        print("\nNo entries need enrichment.")
        return

    print()

    # Process each ambiguous entry
    enriched_count = 0
    for idx, entry in ambiguous:
        print(f"\n[{idx}] {entry.get('date', 'N/A')[:10]}")
        print(f"    Raw: {entry.get('raw_text', '')[:80]}...")

        # Get context
        context = get_data_updates_context(entries, entry.get('date', ''), args.days)
        print(f"    Context: {len(context)} data_updates from last {args.days} days")

        if not context:
            print("    SKIP: No context available")
            continue

        if args.execute:
            # Actually enrich
            enriched = enrich_entry(entry, context)
            if enriched:
                entries[idx]['extracted_data'] = json.dumps(enriched, ensure_ascii=False)
                enriched_count += 1
                print("    ENRICHED")

                # Show updated metrics
                for m in enriched.get('liquidity_metrics', []):
                    print(f"      - {m.get('normalized')}: value={m.get('value')}, direction={m.get('direction')}")
        else:
            print("    WOULD ENRICH (dry run)")

    # Save if execute mode
    if args.execute and enriched_count > 0:
        # Backup original
        backup_path = csv_path.with_suffix('.csv.bak')
        import shutil
        shutil.copy(csv_path, backup_path)
        print(f"\nBackup saved: {backup_path}")

        # Save enriched
        fieldnames = list(entries[0].keys()) if entries else []
        save_processed_csv(csv_path, entries, fieldnames)
        print(f"Saved {enriched_count} enriched entries to {csv_path}")

        # Collect and add new metrics to dictionary
        all_new_metrics = []
        for entry in entries:
            if entry.get('category') == 'data_opinion' and entry.get('extracted_data'):
                try:
                    extracted = json.loads(entry['extracted_data'])
                    for m in extracted.get('liquidity_metrics', []):
                        metric_name = m.get('metric') or m.get('normalized') or m.get('raw')
                        if metric_name:
                            all_new_metrics.append({
                                'raw': metric_name,
                                'normalized': metric_name,
                                'is_new': True,
                                'suggested_category': 'direct',
                                'suggested_description': f"Enriched metric: {m.get('direction', '')} {m.get('value', '')} {m.get('unit', '')}",
                                'suggested_cluster': 'money_markets',
                                'sources': ['Enrichment script']
                            })
                except json.JSONDecodeError:
                    pass

        if all_new_metrics:
            print(f"\nAdding {len(all_new_metrics)} metrics to dictionary...")
            added = append_new_metrics(all_new_metrics)
            if added:
                print(f"Added {len(added)} new metrics:")
                for m in added:
                    print(f"  + {m.get('normalized')}")

    print("\n" + "=" * 60)
    print("ENRICHMENT SUMMARY")
    print("=" * 60)
    print(f"Total entries: {len(entries)}")
    print(f"Ambiguous entries: {len(ambiguous)}")
    print(f"Enriched: {enriched_count if args.execute else 'N/A (dry run)'}")


if __name__ == "__main__":
    main()
