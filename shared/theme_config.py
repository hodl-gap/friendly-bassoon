"""
Theme Configuration

Defines the 6 macro themes with anchor variables, data sources, and query templates.
Each theme groups related causal chains for organized monitoring.
"""

from typing import Dict, List, Any


THEME_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "liquidity": {
        "name": "US Liquidity",
        "description": "Federal Reserve balance sheet, Treasury General Account, reverse repo, and bank reserves",
        "anchor_variables": ["tga", "rrp", "bank_reserves", "sofr", "fed_balance_sheet"],
        "query_template": "Current US liquidity conditions TGA reserves RRP Fed balance sheet",
    },
    "positioning": {
        "name": "Market Positioning",
        "description": "Institutional positioning, prime book data, CTA flows, ETF flows, futures open interest",
        "anchor_variables": ["gs_prime_book", "cta_positioning", "etf_flows", "futures_oi"],
        "query_template": "Current market positioning data prime book leverage CTA",
    },
    "rates": {
        "name": "Interest Rates & Policy",
        "description": "Fed funds rate, SOFR, treasury yields, rate expectations, FOMC decisions",
        "anchor_variables": ["fed_funds", "sofr", "treasury_yields", "rate_expectations", "us10y"],
        "query_template": "Current interest rate environment Fed policy SOFR treasury yields",
    },
    "risk_appetite": {
        "name": "Risk Appetite",
        "description": "VIX, DXY, credit spreads, high yield spreads, risk-on/risk-off indicators",
        "anchor_variables": ["vix", "dxy", "credit_spreads", "high_yield"],
        "query_template": "Current risk appetite VIX DXY credit spreads",
    },
    "crypto_specific": {
        "name": "Crypto-Specific",
        "description": "BTC ETF flows, stablecoin supply, exchange reserves, crypto-native indicators",
        "anchor_variables": ["btc_etf_flows", "stablecoin_supply", "exchange_reserves", "btc"],
        "query_template": "Bitcoin ETF flows stablecoin supply crypto-specific indicators",
    },
    "event_calendar": {
        "name": "Event Calendar",
        "description": "Upcoming macro events: FOMC, CPI, NFP, options expiration",
        "anchor_variables": ["fomc", "cpi", "nfp", "opex"],
        "query_template": "Upcoming macro events FOMC CPI NFP options expiration",
    },
}


def get_theme(name: str) -> Dict[str, Any]:
    """Get a theme definition by name.

    Args:
        name: Theme name (e.g., "liquidity", "positioning")

    Returns:
        Theme definition dict

    Raises:
        ValueError: If theme name is not recognized
    """
    if name not in THEME_DEFINITIONS:
        raise ValueError(f"Unknown theme: {name}. Available: {list(THEME_DEFINITIONS.keys())}")
    return THEME_DEFINITIONS[name]


def get_all_themes() -> Dict[str, Dict[str, Any]]:
    """Get all theme definitions."""
    return THEME_DEFINITIONS


def get_all_anchor_variables() -> List[Dict[str, Any]]:
    """Get a flat list of all anchor variables across all themes.

    Returns:
        List of dicts with normalized_name and theme info.
        Deduplicates variables that appear in multiple themes.
    """
    import json
    from pathlib import Path

    # Load anchor_variables.json for data source info
    anchor_path = Path(__file__).parent / "data" / "anchor_variables.json"
    anchor_data = {}
    if anchor_path.exists():
        with open(anchor_path, "r") as f:
            anchor_data = json.load(f)

    seen = set()
    result = []
    for theme_name, theme in THEME_DEFINITIONS.items():
        for var_name in theme["anchor_variables"]:
            if var_name not in seen:
                seen.add(var_name)
                entry = anchor_data.get(var_name, {})
                result.append({
                    "normalized_name": var_name,
                    "data_source": entry.get("source", None),
                    "series_id": entry.get("series_id", None),
                    "fetch_frequency": entry.get("frequency", None),
                    "themes": [theme_name],
                })
            else:
                # Variable already seen, add this theme to its themes list
                for r in result:
                    if r["normalized_name"] == var_name:
                        r["themes"].append(theme_name)
                        break
    return result
