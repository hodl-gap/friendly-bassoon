"""
Asset Configuration Registry

Per-asset configuration for multi-asset impact analysis.
Each asset class defines its priority variables, keywords, instruments,
file paths, and prompt fragments.
"""

from typing import Dict, Any


ASSET_CONFIGS: Dict[str, Dict[str, Any]] = {
    "btc": {
        "name": "Bitcoin",
        "ticker": "BTC-USD",
        "priority_variables": [
            "btc", "tga", "dxy", "vix", "us10y", "fed_balance_sheet", "bank_reserves",
        ],
        "always_include_variable": "btc",
        "chain_keywords": ["btc", "bitcoin", "crypto"],
        "default_instruments": [
            {"ticker": "BTC-USD", "source": "Yahoo", "role": "Bitcoin price"},
            {"ticker": "^VIX", "source": "Yahoo", "role": "Volatility index"},
        ],
        "relationships_file": "btc_relationships.json",
        "regime_file": "regime_state.json",
        "prompt_asset_line": "analyze the impact on Bitcoin.",
        "relevant_themes": ["liquidity", "risk_appetite", "crypto_specific", "rates"],
    },
    "equity": {
        "name": "US Equities",
        "ticker": "SPY",
        "priority_variables": [
            "sp500", "vix", "us10y", "dxy", "fed_balance_sheet", "tga", "nasdaq",
        ],
        "always_include_variable": "sp500",
        "chain_keywords": ["equity", "equities", "stock", "stocks", "sp500", "s&p", "nasdaq"],
        "default_instruments": [
            {"ticker": "^GSPC", "source": "Yahoo", "role": "S&P 500 index"},
            {"ticker": "^VIX", "source": "Yahoo", "role": "Volatility index"},
        ],
        "relationships_file": "equity_relationships.json",
        "regime_file": "equity_regime_state.json",
        "prompt_asset_line": "analyze the impact on US equities (S&P 500 / broad equity market).",
        "relevant_themes": ["liquidity", "positioning", "rates", "risk_appetite"],
    },
}


def get_asset_config(asset_class: str) -> Dict[str, Any]:
    """Get configuration for a given asset class.

    Args:
        asset_class: Asset class identifier (e.g., "btc", "equity")

    Returns:
        Asset configuration dict

    Raises:
        ValueError: If asset_class is not recognized
    """
    asset = asset_class.lower()
    if asset not in ASSET_CONFIGS:
        raise ValueError(f"Unknown asset class: {asset}. Available: {list(ASSET_CONFIGS.keys())}")
    return ASSET_CONFIGS[asset]
