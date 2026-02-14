"""
Backfill Variable Frequency

One-time script: loads all existing chains, calls record_variables()
for each, saves frequency file.
"""

import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.variable_frequency import VariableFrequencyTracker
from subproject_risk_intelligence import config


def main():
    relationships_path = config.DATA_DIR / "btc_relationships.json"
    freq_path = config.DATA_DIR / "variable_frequency.json"

    # Load existing chains
    with open(relationships_path, "r") as f:
        data = json.load(f)
    chains = data.get("relationships", [])
    print(f"Loaded {len(chains)} chains from {relationships_path}")

    # Build frequency tracker
    tracker = VariableFrequencyTracker.load(freq_path)
    for chain in chains:
        tracker.record_variables(chain)
    tracker.save(freq_path)

    # Print results
    print(f"Tracked {len(tracker.variables)} unique variables")
    candidates = tracker.get_candidates(min_chain_count=3, min_sources=2)
    print(f"{len(candidates)} promotion candidates (>=3 chains, >=2 sources)")
    for c in candidates[:5]:
        print(f"  {c['name']}: {c['chain_count']} chains, {len(c['sources'])} sources")


if __name__ == "__main__":
    main()
