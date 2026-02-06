"""
Variable Resolver Module

Centralized variable resolution using discovered_data_ids.json as the source of truth.
Replaces hard-coded mappings in BTC Intelligence with dynamic lookup.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .data_id_utils import parse_data_id, format_data_id

# Path to discovered mappings (source of truth)
MAPPINGS_PATH = Path(__file__).parent.parent / "subproject_variable_mapper" / "mappings" / "discovered_data_ids.json"

# Fallback mappings for Yahoo tickers (not in discovered_data_ids.json)
# These are market tickers that don't go through the discovery process
YAHOO_FALLBACK = {
    # Major indices
    "spy": {"source": "Yahoo", "series_id": "SPY"},
    "qqq": {"source": "Yahoo", "series_id": "QQQ"},
    "sp500": {"source": "Yahoo", "series_id": "^GSPC"},
    "nasdaq": {"source": "Yahoo", "series_id": "^IXIC"},
    "dow": {"source": "Yahoo", "series_id": "^DJI"},
    "russell2000": {"source": "Yahoo", "series_id": "^RUT"},

    # Sector ETFs (for belief-space analysis)
    "igv": {"source": "Yahoo", "series_id": "IGV"},          # iShares Expanded Tech-Software Sector
    "xlk": {"source": "Yahoo", "series_id": "XLK"},          # Technology Select Sector SPDR
    "smh": {"source": "Yahoo", "series_id": "SMH"},          # VanEck Semiconductor
    "soxx": {"source": "Yahoo", "series_id": "SOXX"},        # iShares Semiconductor
    "xly": {"source": "Yahoo", "series_id": "XLY"},          # Consumer Discretionary
    "xlf": {"source": "Yahoo", "series_id": "XLF"},          # Financials
    "xle": {"source": "Yahoo", "series_id": "XLE"},          # Energy
    "xlu": {"source": "Yahoo", "series_id": "XLU"},          # Utilities

    # Big Tech (for CAPEX/earnings analysis)
    "googl": {"source": "Yahoo", "series_id": "GOOGL"},      # Alphabet
    "amzn": {"source": "Yahoo", "series_id": "AMZN"},        # Amazon
    "msft": {"source": "Yahoo", "series_id": "MSFT"},        # Microsoft
    "meta": {"source": "Yahoo", "series_id": "META"},        # Meta
    "aapl": {"source": "Yahoo", "series_id": "AAPL"},        # Apple
    "nvda": {"source": "Yahoo", "series_id": "NVDA"},        # Nvidia
    "orcl": {"source": "Yahoo", "series_id": "ORCL"},        # Oracle

    # Fixed Income & Commodities
    "gld": {"source": "Yahoo", "series_id": "GLD"},
    "tlt": {"source": "Yahoo", "series_id": "TLT"},
    "gold": {"source": "Yahoo", "series_id": "GC=F"},

    # FX & Crypto
    "dxy": {"source": "Yahoo", "series_id": "DX-Y.NYB"},
    "btc": {"source": "Yahoo", "series_id": "BTC-USD"},
    "eth": {"source": "Yahoo", "series_id": "ETH-USD"},
    "usdjpy": {"source": "Yahoo", "series_id": "USDJPY=X"},
    "eurusd": {"source": "Yahoo", "series_id": "EURUSD=X"},

    # Volatility
    "vix": {"source": "Yahoo", "series_id": "^VIX"},
    "vvix": {"source": "Yahoo", "series_id": "^VVIX"},
}

# Cache for loaded mappings
_mappings_cache: Optional[Dict[str, Any]] = None


def load_mappings() -> Dict[str, Any]:
    """
    Load discovered data ID mappings from JSON file.

    Returns:
        Dict with 'metadata' and 'mappings' keys
    """
    global _mappings_cache

    if _mappings_cache is not None:
        return _mappings_cache

    if not MAPPINGS_PATH.exists():
        print(f"[variable_resolver] Warning: Mappings file not found at {MAPPINGS_PATH}")
        _mappings_cache = {"metadata": {}, "mappings": {}}
        return _mappings_cache

    try:
        with open(MAPPINGS_PATH, 'r') as f:
            _mappings_cache = json.load(f)
        return _mappings_cache
    except Exception as e:
        print(f"[variable_resolver] Error loading mappings: {e}")
        _mappings_cache = {"metadata": {}, "mappings": {}}
        return _mappings_cache


def clear_cache():
    """Clear the mappings cache (useful for testing)."""
    global _mappings_cache
    _mappings_cache = None


def resolve_variable(variable: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a variable name to its data source information.

    Looks up the variable in discovered_data_ids.json first,
    then falls back to Yahoo tickers for market data.

    Args:
        variable: Variable name (e.g., "tga", "btc", "spy")

    Returns:
        Dict with:
        - source: Data source name (e.g., "FRED", "Yahoo")
        - series_id: Series identifier (e.g., "WTREGEN", "BTC-USD")
        - data_id: Full data_id in "SOURCE:SERIES" format
        - metadata: Additional info from discovered_data_ids.json (if available)

        Returns None if variable cannot be resolved.

    Examples:
        >>> result = resolve_variable("tga")
        >>> result["source"]
        'FRED'
        >>> result["series_id"]
        'WTREGEN'

        >>> result = resolve_variable("btc")
        >>> result["source"]
        'Yahoo'
        >>> result["series_id"]
        'BTC-USD'
    """
    var_lower = variable.lower().strip()

    # Step 1: Check discovered_data_ids.json (source of truth)
    mappings = load_mappings()
    discovered = mappings.get("mappings", {})

    if var_lower in discovered:
        mapping = discovered[var_lower]
        data_id = mapping.get("data_id")

        # Skip entries with type "not_found" or null data_id
        if mapping.get("type") == "not_found" or not data_id or data_id == "N/A":
            pass  # Fall through to Yahoo fallback
        else:
            source, series_id = parse_data_id(data_id)
            return {
                "source": source,
                "series_id": series_id,
                "data_id": data_id,
                "metadata": {
                    "description": mapping.get("description", ""),
                    "frequency": mapping.get("frequency", ""),
                    "type": mapping.get("type", ""),
                    "api_url": mapping.get("api_url"),
                    "notes": mapping.get("notes", ""),
                }
            }

    # Step 2: Check Yahoo fallback for market tickers
    if var_lower in YAHOO_FALLBACK:
        fallback = YAHOO_FALLBACK[var_lower]
        source = fallback["source"]
        series_id = fallback["series_id"]
        return {
            "source": source,
            "series_id": series_id,
            "data_id": format_data_id(source, series_id),
            "metadata": {
                "description": f"Yahoo Finance ticker: {series_id}",
                "frequency": "daily",
                "type": "api",
                "api_url": None,
                "notes": "Market data from Yahoo Finance",
            }
        }

    # Not found
    return None


def get_all_mappings() -> Dict[str, Dict[str, Any]]:
    """
    Get all available variable mappings (discovered + Yahoo fallback).

    Returns:
        Dict mapping variable names to their resolution info
    """
    result = {}

    # Add discovered mappings
    mappings = load_mappings()
    for name, mapping in mappings.get("mappings", {}).items():
        if mapping.get("type") != "not_found" and mapping.get("data_id"):
            source, series_id = parse_data_id(mapping["data_id"])
            result[name] = {
                "source": source,
                "series_id": series_id,
                "data_id": mapping["data_id"],
            }

    # Add Yahoo fallback (won't overwrite discovered)
    for name, fallback in YAHOO_FALLBACK.items():
        if name not in result:
            source = fallback["source"]
            series_id = fallback["series_id"]
            result[name] = {
                "source": source,
                "series_id": series_id,
                "data_id": format_data_id(source, series_id),
            }

    return result


def list_known_variables() -> list:
    """
    List all known variable names.

    Returns:
        Sorted list of variable names
    """
    return sorted(get_all_mappings().keys())
