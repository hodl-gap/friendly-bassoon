"""
Data ID Mapping Module

Maps normalized variable names to data source IDs (FRED, Bloomberg, etc.).
This is Step 4 of the 4-step process.

Uses discovered_data_ids.json for mappings.
Auto-discovers mappings for unmapped variables if AUTO_DISCOVER is True.
"""

import json
from pathlib import Path

from states import VariableMapperState
from config import DISCOVERED_MAPPINGS_FILE, AUTO_DISCOVER


def load_discovered_mappings() -> dict:
    """
    Load discovered data ID mappings from JSON file.

    Returns:
        dict: normalized_name -> mapping info
    """
    if not DISCOVERED_MAPPINGS_FILE.exists():
        print(f"[data_id_mapping] No mappings file found at {DISCOVERED_MAPPINGS_FILE}")
        print("[data_id_mapping] Run 'python data_id_discovery.py' to discover mappings")
        return {}

    with open(DISCOVERED_MAPPINGS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    mappings = data.get("mappings", {})
    print(f"[data_id_mapping] Loaded {len(mappings)} discovered mappings")
    return mappings


def map_to_data_ids(state: VariableMapperState) -> VariableMapperState:
    """
    Map normalized variables to data source IDs and build final output.

    Input (from State):
        - normalized_variables: List[Dict] from Step 2
        - missing_variables: List[str] from Step 3
        - chain_dependencies: List[Dict] from Step 3

    Output (to State):
        - mapped_variables: List[Dict] with data IDs
        - unmapped_variables: List[str] - variables without data IDs
        - final_output: Dict - complete structured output
    """
    normalized_variables = state.get("normalized_variables", [])
    missing_variables = state.get("missing_variables", [])
    chain_dependencies = state.get("chain_dependencies", [])

    print(f"[data_id_mapping] Processing {len(normalized_variables)} variables...")

    # Load discovered mappings
    mappings = load_discovered_mappings()

    mapped_variables = []
    unmapped_variables = []

    for var in normalized_variables:
        normalized_name = var.get("normalized_name")
        raw_name = var.get("raw_name", "unknown")

        if normalized_name:
            # Look up in discovered mappings
            mapping = mappings.get(normalized_name.lower())

            if mapping and mapping.get("type") in ("api", "needs_registration") and mapping.get("data_id"):
                # Found valid mapping - include ALL discovery fields
                mapped_var = {
                    **var,
                    **mapping,  # Full mapping: api_url, description, notes, example_indicators, etc.
                }
                mapped_variables.append(mapped_var)
                print(f"[data_id_mapping] Mapped: '{normalized_name}' -> '{mapping.get('data_id')}'")

            elif mapping and mapping.get("type") == "scrape":
                # Scrapable source - include full discovery details
                mapped_var = {
                    **var,
                    **mapping,
                }
                mapped_variables.append(mapped_var)
                unmapped_variables.append(normalized_name)
                print(f"[data_id_mapping] Scrapable: '{normalized_name}' -> {mapping.get('source_url')}")

            else:
                # No mapping found or not_found/failed
                mapped_var = {
                    **var,
                    "data_id": None,
                    "data_source": None,
                }
                mapped_variables.append(mapped_var)
                unmapped_variables.append(normalized_name)
                print(f"[data_id_mapping] Unmapped: '{normalized_name}'")
        else:
            # Variable wasn't normalized (unknown)
            mapped_var = {
                **var,
                "data_id": None,
                "data_source": None,
            }
            mapped_variables.append(mapped_var)
            unmapped_variables.append(raw_name)
            print(f"[data_id_mapping] Unrecognized: '{raw_name}'")

    # Build dependencies list from chain_dependencies
    all_dependencies = []
    for chain_dep in chain_dependencies:
        for step in chain_dep.get("steps", []):
            all_dependencies.append(step)

    # Build final output structure
    final_output = {
        "variables": mapped_variables,
        "unmapped_variables": unmapped_variables,
        "missing_variables": missing_variables,
        "dependencies": all_dependencies
    }

    mapped_count = len(mapped_variables) - len(unmapped_variables)
    print(f"[data_id_mapping] Mapped: {mapped_count}, Unmapped: {len(unmapped_variables)}")

    # Auto-discover unmapped variables if enabled
    if unmapped_variables and AUTO_DISCOVER:
        print(f"[data_id_mapping] AUTO_DISCOVER enabled - discovering {len(unmapped_variables)} unmapped variables...")

        from data_id_discovery import discover_data_ids_sync

        # Run discovery for unmapped variables
        discover_data_ids_sync(unmapped_variables, skip_existing=True, validate=True)

        # Reload mappings after discovery
        mappings = load_discovered_mappings()

        # Re-map the previously unmapped variables
        for i, var in enumerate(mapped_variables):
            if var.get("data_id") is None:
                normalized_name = var.get("normalized_name")
                if normalized_name:
                    mapping = mappings.get(normalized_name.lower())
                    if mapping and mapping.get("type") in ("api", "needs_registration") and mapping.get("data_id"):
                        mapped_variables[i] = {
                            **var,
                            **mapping,  # Full mapping details
                        }
                        print(f"[data_id_mapping] Now mapped: '{normalized_name}' -> '{mapping.get('data_id')}'")
                        if normalized_name in unmapped_variables:
                            unmapped_variables.remove(normalized_name)

        # Update final output
        final_output["variables"] = mapped_variables
        final_output["unmapped_variables"] = unmapped_variables

        mapped_count = len(mapped_variables) - len(unmapped_variables)
        print(f"[data_id_mapping] After discovery - Mapped: {mapped_count}, Unmapped: {len(unmapped_variables)}")

    elif unmapped_variables:
        print(f"[data_id_mapping] TIP: Run 'python data_id_discovery.py -v {','.join(unmapped_variables[:5])}' to discover mappings")

    return {
        **state,
        "mapped_variables": mapped_variables,
        "unmapped_variables": unmapped_variables,
        "final_output": final_output
    }


# For standalone testing
if __name__ == "__main__":
    # Test with sample normalized variables
    test_state = VariableMapperState(
        normalized_variables=[
            {"raw_name": "TGA", "normalized_name": "tga", "category": "direct"},
            {"raw_name": "VIX", "normalized_name": "vix", "category": "indirect"},
            {"raw_name": "unknown_xyz", "normalized_name": None, "category": "unknown"},
        ],
        missing_variables=["fci", "yield_curve"],
        chain_dependencies=[
            {
                "chain": "TGA → liquidity → FCI",
                "variables": ["tga", "liquidity", "fci"],
                "steps": [
                    {"from": "tga", "to": "liquidity", "relationship": "causes"},
                    {"from": "liquidity", "to": "fci", "relationship": "leads_to"}
                ]
            }
        ]
    )

    result = map_to_data_ids(test_state)

    print("\n" + "=" * 50)
    print("FINAL OUTPUT:")
    print("=" * 50)

    print(json.dumps(result.get("final_output", {}), indent=2))
