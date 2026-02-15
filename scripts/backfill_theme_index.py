"""
Backfill Theme Index

One-time script: loads all chains from relationships.json,
calls ThemeIndex.rebuild_from_chains(), saves theme_index.json.
"""

import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.theme_index import ThemeIndex
from subproject_risk_intelligence import config


def main():
    relationships_path = config.DATA_DIR / "relationships.json"
    theme_index_path = config.DATA_DIR / "theme_index.json"

    # Load existing chains
    with open(relationships_path, "r") as f:
        data = json.load(f)
    chains = data.get("relationships", [])
    print(f"Loaded {len(chains)} chains from {relationships_path}")

    # Build theme index
    index = ThemeIndex.load(theme_index_path)
    index.rebuild_from_chains(chains)
    index.save(theme_index_path)

    # Print results
    total_indexed = 0
    for name, theme in index.themes.items():
        count = len(theme.get("chain_ids", []))
        total_indexed += count
        print(f"  {name}: {count} chains")
    print(f"Indexed {len(chains)} chains across {len(index.themes)} themes")
    print(f"  (total assignments: {total_indexed}, some chains appear in multiple themes)")


if __name__ == "__main__":
    main()
