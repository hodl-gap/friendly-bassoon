"""
Backfill Chain Triggers

One-time script: loads all chains from relationships.json,
extracts chain-specific trigger conditions using Haiku + tool_use,
saves back to relationships.json.
"""

import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from subproject_risk_intelligence import config
from subproject_risk_intelligence.relationship_store import extract_chain_triggers


def main():
    relationships_path = config.DATA_DIR / "relationships.json"

    if not relationships_path.exists():
        print(f"No relationships file at {relationships_path}")
        return

    # Load existing chains
    with open(relationships_path, "r") as f:
        data = json.load(f)
    chains = data.get("relationships", [])
    print(f"Loaded {len(chains)} chains from {relationships_path}")

    # Extract triggers for chains that don't have them
    updated = 0
    skipped = 0
    failed = 0

    for i, chain in enumerate(chains):
        if chain.get("trigger_conditions"):
            skipped += 1
            continue

        print(f"\n[{i+1}/{len(chains)}] Processing chain: {chain.get('logic_chain', {}).get('chain_summary', '?')[:60]}...")

        try:
            triggers = extract_chain_triggers(chain)
            if triggers:
                chain["trigger_conditions"] = triggers
                updated += 1
                for t in triggers:
                    print(f"  -> {t['variable']}: {t['condition_type']} {t['condition_direction']} {t['condition_value']} ({t.get('timeframe_days', 7)}d)")
            else:
                print("  -> No triggers extracted")
                failed += 1
        except Exception as e:
            print(f"  -> Error: {e}")
            failed += 1

    # Save back
    if updated > 0:
        with open(relationships_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {relationships_path}")

    print(f"\nResults: {updated} updated, {skipped} already had triggers, {failed} failed")


if __name__ == "__main__":
    main()
