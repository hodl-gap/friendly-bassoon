"""
Data Fetching Module

Resolves variables to data source IDs and fetches historical data.
Uses adapters for FRED, Yahoo Finance, and CoinGecko.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))

from states import DataCollectionState
from config import (
    DISCOVERED_DATA_IDS,
    DEFAULT_LOOKBACK_YEARS,
    AUTO_DISCOVER_MISSING_DATA_IDS
)
from adapters import FREDAdapter, YahooAdapter, CoinGeckoAdapter
from adapters.fred_adapter import COMMON_FRED_SERIES
from adapters.yahoo_adapter import COMMON_YAHOO_TICKERS
from adapters.coingecko_adapter import COMMON_COINGECKO_COINS


def resolve_data_ids(state: DataCollectionState) -> DataCollectionState:
    """
    Resolve variables to data source IDs.

    LangGraph node function.

    Args:
        state: Current workflow state with parsed_claims

    Returns:
        Updated state with resolved_data_ids
    """
    claims = state.get("parsed_claims", [])
    variable_mappings = state.get("variable_mappings", {})

    if not claims:
        print("[data_fetching] No claims to resolve")
        state["resolved_data_ids"] = {}
        return state

    # Collect all unique variables
    variables = set()
    for claim in claims:
        if claim.get("variable_a"):
            variables.add(claim["variable_a"])
        if claim.get("variable_b"):
            variables.add(claim["variable_b"])

    print(f"[data_fetching] Resolving {len(variables)} unique variables")

    # Resolve each variable
    resolved = {}
    unresolved = []

    for var in variables:
        data_id = resolve_single_variable(var, variable_mappings)
        if data_id:
            resolved[var] = data_id
            print(f"[data_fetching] Resolved: {var} -> {data_id['source']}:{data_id['series_id']}")
        else:
            unresolved.append(var)
            print(f"[data_fetching] Unresolved: {var}")

    state["resolved_data_ids"] = resolved

    if unresolved:
        warning = f"Could not resolve data IDs for: {', '.join(unresolved)}"
        state["warnings"] = state.get("warnings", []) + [warning]

    return state


def resolve_single_variable(
    variable: str,
    mappings: Dict[str, Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Resolve a single variable to its data source ID.

    Args:
        variable: Normalized variable name
        mappings: Pre-provided mappings (from variable_mapper)

    Returns:
        Dict with source, series_id, or None if not found
    """
    # 1. Check pre-provided mappings first
    if mappings and variable in mappings:
        mapping = mappings[variable]
        return {
            "source": mapping.get("source", ""),
            "series_id": mapping.get("data_id", "").split(":")[-1],
            "data_id": mapping.get("data_id", "")
        }

    # 2. Check discovered_data_ids.json
    discovered = load_discovered_data_ids()
    if variable in discovered:
        mapping = discovered[variable]
        data_id = mapping.get("data_id", "")
        parts = data_id.split(":")
        return {
            "source": parts[0] if parts else "",
            "series_id": parts[1] if len(parts) > 1 else data_id,
            "data_id": data_id
        }

    # 3. Check common mappings
    # FRED
    if variable in COMMON_FRED_SERIES:
        return {
            "source": "FRED",
            "series_id": COMMON_FRED_SERIES[variable],
            "data_id": f"FRED:{COMMON_FRED_SERIES[variable]}"
        }

    # Yahoo
    if variable in COMMON_YAHOO_TICKERS:
        return {
            "source": "Yahoo",
            "series_id": COMMON_YAHOO_TICKERS[variable],
            "data_id": f"Yahoo:{COMMON_YAHOO_TICKERS[variable]}"
        }

    # CoinGecko
    if variable in COMMON_COINGECKO_COINS:
        return {
            "source": "CoinGecko",
            "series_id": COMMON_COINGECKO_COINS[variable],
            "data_id": f"CoinGecko:{COMMON_COINGECKO_COINS[variable]}"
        }

    # 4. Try to infer source from variable name
    inferred = infer_data_source(variable)
    if inferred:
        return inferred

    return None


def load_discovered_data_ids() -> Dict[str, Any]:
    """
    Load discovered data IDs from variable_mapper.

    Returns:
        Dict of variable -> mapping
    """
    if not DISCOVERED_DATA_IDS.exists():
        return {}

    try:
        with open(DISCOVERED_DATA_IDS, 'r') as f:
            data = json.load(f)
            # Convert list to dict keyed by normalized_name
            if isinstance(data, list):
                return {item.get("normalized_name", ""): item for item in data}
            return data
    except Exception as e:
        print(f"[data_fetching] Error loading discovered_data_ids.json: {e}")
        return {}


def infer_data_source(variable: str) -> Optional[Dict[str, Any]]:
    """
    Infer data source from variable name patterns.

    Args:
        variable: Normalized variable name

    Returns:
        Inferred mapping or None
    """
    # Crypto patterns
    crypto_keywords = ["btc", "eth", "crypto", "bitcoin", "ethereum", "sol", "ada"]
    if any(kw in variable for kw in crypto_keywords):
        # Try to match to CoinGecko
        for short, full in COMMON_COINGECKO_COINS.items():
            if short in variable:
                return {
                    "source": "CoinGecko",
                    "series_id": full,
                    "data_id": f"CoinGecko:{full}"
                }

    # Index patterns
    if variable in ["spy", "qqq", "tlt", "gld", "hyg"]:
        ticker = variable.upper()
        return {
            "source": "Yahoo",
            "series_id": ticker,
            "data_id": f"Yahoo:{ticker}"
        }

    # Currency patterns
    if "usd" in variable and len(variable) == 6:  # e.g., usdjpy
        ticker = variable.upper() + "=X"
        return {
            "source": "Yahoo",
            "series_id": ticker,
            "data_id": f"Yahoo:{ticker}"
        }

    return None


def fetch_historical_data(state: DataCollectionState) -> DataCollectionState:
    """
    Fetch historical data for resolved variables.

    LangGraph node function.

    Args:
        state: Current workflow state with resolved_data_ids

    Returns:
        Updated state with fetched_data
    """
    resolved = state.get("resolved_data_ids", {})

    if not resolved:
        print("[data_fetching] No resolved data IDs to fetch")
        state["fetched_data"] = {}
        return state

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * DEFAULT_LOOKBACK_YEARS)

    print(f"[data_fetching] Fetching data for {len(resolved)} variables")
    print(f"[data_fetching] Date range: {start_date.date()} to {end_date.date()}")

    # Initialize adapters
    adapters = {
        "FRED": FREDAdapter(),
        "Yahoo": YahooAdapter(),
        "CoinGecko": CoinGeckoAdapter()
    }

    # Fetch data for each variable
    fetched = {}
    errors = []

    for variable, mapping in resolved.items():
        source = mapping.get("source", "")
        series_id = mapping.get("series_id", "")

        if source not in adapters:
            print(f"[data_fetching] Unknown source: {source}")
            errors.append(f"Unknown source '{source}' for {variable}")
            continue

        adapter = adapters[source]

        try:
            data = adapter.fetch(series_id, start_date, end_date)
            fetched[variable] = data
            print(f"[data_fetching] Fetched {data.get('data_points', 0)} points for {variable}")
        except Exception as e:
            print(f"[data_fetching] Error fetching {variable}: {e}")
            errors.append(f"Failed to fetch {variable}: {str(e)}")

    state["fetched_data"] = fetched

    if errors:
        state["errors"] = state.get("errors", []) + errors

    return state


def align_time_series(
    data_a: Dict[str, Any],
    data_b: Dict[str, Any]
) -> tuple:
    """
    Align two time series to common dates.

    Args:
        data_a: First time series data
        data_b: Second time series data

    Returns:
        Tuple of (aligned_dates, values_a, values_b)
    """
    # Create date -> value maps
    map_a = {d: v for d, v in data_a.get("data", [])}
    map_b = {d: v for d, v in data_b.get("data", [])}

    # Find common dates
    common_dates = sorted(set(map_a.keys()) & set(map_b.keys()))

    if not common_dates:
        return [], [], []

    # Extract aligned values
    values_a = [map_a[d] for d in common_dates]
    values_b = [map_b[d] for d in common_dates]

    return common_dates, values_a, values_b


# Testing entry point
if __name__ == "__main__":
    from states import DataCollectionState

    # Test with sample claims
    state = DataCollectionState(
        mode="claim_validation",
        parsed_claims=[
            {
                "claim_text": "BTC follows gold",
                "variable_a": "btc",
                "variable_b": "gold",
                "relationship_type": "correlation"
            }
        ]
    )

    # Test resolve
    state = resolve_data_ids(state)
    print("\nResolved IDs:")
    for var, mapping in state.get("resolved_data_ids", {}).items():
        print(f"  {var}: {mapping}")

    # Test fetch (uncomment to actually fetch data)
    # state = fetch_historical_data(state)
    # print("\nFetched Data:")
    # for var, data in state.get("fetched_data", {}).items():
    #     print(f"  {var}: {data.get('data_points', 0)} points")
