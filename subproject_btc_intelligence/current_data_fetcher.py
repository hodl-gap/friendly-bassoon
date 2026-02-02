"""
Current Data Fetcher Module

Fetches current/latest values for extracted variables with period-over-period changes.
Self-contained implementation using requests/yfinance directly.
"""

import os
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

from .states import BTCImpactState

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")


# ============================================================================
# Variable to Data Source Mappings
# ============================================================================

FRED_SERIES = {
    "tga": "WTREGEN",
    "rrp": "RRPONTSYD",
    "fed_balance_sheet": "WALCL",
    "reserves": "TOTRESNS",
    "bank_reserves": "TOTRESNS",
    "us02y": "DGS2",
    "us10y": "DGS10",
    "sofr": "SOFR",
    "fed_funds": "FEDFUNDS",
    "vix": "VIXCLS",
}

YAHOO_TICKERS = {
    "spy": "SPY",
    "qqq": "QQQ",
    "gld": "GLD",
    "tlt": "TLT",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dxy": "DX-Y.NYB",
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "gold": "GC=F",
    "usdjpy": "USDJPY=X",
}


def resolve_variable(variable: str) -> Optional[Dict[str, Any]]:
    """Resolve variable name to data source and series ID."""
    var_lower = variable.lower().strip()

    if var_lower in FRED_SERIES:
        return {"source": "FRED", "series_id": FRED_SERIES[var_lower]}

    if var_lower in YAHOO_TICKERS:
        return {"source": "Yahoo", "series_id": YAHOO_TICKERS[var_lower]}

    return None


def fetch_fred_with_history(series_id: str, lookback_days: int = 45) -> Optional[Dict[str, Any]]:
    """
    Fetch data from FRED API with historical values for change calculation.

    Returns dict with:
        - value: latest value
        - date: latest date
        - history: list of (date, value) tuples
    """
    if not FRED_API_KEY:
        print("[FRED] No API key configured")
        return None

    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date.strftime("%Y-%m-%d"),
        "observation_end": end_date.strftime("%Y-%m-%d"),
        "sort_order": "asc",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("observations"):
            # Filter out missing values and build history
            history = []
            for obs in data["observations"]:
                if obs["value"] != ".":
                    history.append((obs["date"], float(obs["value"])))

            if history:
                latest = history[-1]
                return {
                    "value": latest[1],
                    "date": latest[0],
                    "source": "FRED",
                    "series_id": series_id,
                    "history": history
                }
    except Exception as e:
        print(f"[FRED] Error fetching {series_id}: {e}")

    return None


def fetch_yahoo_with_history(ticker: str, lookback_days: int = 45) -> Optional[Dict[str, Any]]:
    """
    Fetch data from Yahoo Finance with historical values for change calculation.

    Returns dict with:
        - value: latest value
        - date: latest date
        - history: list of (date, value) tuples
    """
    try:
        import yfinance as yf

        period = "3mo" if lookback_days > 30 else "1mo"
        t = yf.Ticker(ticker)
        hist = t.history(period=period)

        if not hist.empty:
            history = []
            for idx, row in hist.iterrows():
                date_str = idx.strftime("%Y-%m-%d")
                history.append((date_str, float(row["Close"])))

            if history:
                latest = history[-1]
                return {
                    "value": latest[1],
                    "date": latest[0],
                    "source": "Yahoo",
                    "series_id": ticker,
                    "history": history
                }
    except Exception as e:
        print(f"[Yahoo] Error fetching {ticker}: {e}")

    return None


def calculate_changes(history: List[Tuple[str, float]]) -> Dict[str, Any]:
    """
    Calculate period-over-period changes from history.

    Returns:
        - change_1w: (absolute, percentage, direction)
        - change_1m: (absolute, percentage, direction)
    """
    if not history or len(history) < 2:
        return {}

    latest_value = history[-1][1]
    latest_date = datetime.strptime(history[-1][0], "%Y-%m-%d")

    changes = {}

    # Find value from ~1 week ago (5-9 days)
    week_ago_value = None
    for date_str, value in reversed(history):
        date = datetime.strptime(date_str, "%Y-%m-%d")
        days_diff = (latest_date - date).days
        if 5 <= days_diff <= 10:
            week_ago_value = value
            break

    if week_ago_value and week_ago_value != 0:
        abs_change = latest_value - week_ago_value
        pct_change = (abs_change / week_ago_value) * 100
        direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
        changes["change_1w"] = {
            "absolute": abs_change,
            "percentage": pct_change,
            "direction": direction
        }

    # Find value from ~1 month ago (25-35 days)
    month_ago_value = None
    for date_str, value in reversed(history):
        date = datetime.strptime(date_str, "%Y-%m-%d")
        days_diff = (latest_date - date).days
        if 25 <= days_diff <= 40:
            month_ago_value = value
            break

    if month_ago_value and month_ago_value != 0:
        abs_change = latest_value - month_ago_value
        pct_change = (abs_change / month_ago_value) * 100
        direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
        changes["change_1m"] = {
            "absolute": abs_change,
            "percentage": pct_change,
            "direction": direction
        }

    return changes


def fetch_current_data(state: BTCImpactState) -> BTCImpactState:
    """
    Fetch current values for extracted variables with period-over-period changes.

    Updates state with:
    - current_values: Dict of variable -> {value, date, source, changes}
    - btc_price: Current BTC price
    - fetch_errors: List of failed variables
    """
    variables = state.get("extracted_variables", [])

    if not variables:
        print("[Current Data] No variables to fetch")
        state["current_values"] = {}
        state["fetch_errors"] = []
        return state

    var_names = list(set(v.get("normalized", "") for v in variables if v.get("normalized")))
    print(f"[Current Data] Fetching current values for {len(var_names)} variables")

    current_values = {}
    fetch_errors = []

    for var_name in var_names:
        mapping = resolve_variable(var_name)

        if not mapping:
            print(f"[Current Data] Could not resolve: {var_name}")
            fetch_errors.append(var_name)
            continue

        source = mapping["source"]
        series_id = mapping["series_id"]

        result = None
        if source == "FRED":
            result = fetch_fred_with_history(series_id)
        elif source == "Yahoo":
            result = fetch_yahoo_with_history(series_id)

        if result:
            # Calculate changes
            history = result.pop("history", [])
            changes = calculate_changes(history)
            result["changes"] = changes

            current_values[var_name] = result

            # Log with change info
            change_str = ""
            if changes.get("change_1w"):
                c = changes["change_1w"]
                change_str = f" ({c['direction']}{abs(c['percentage']):.1f}% 1w)"
            print(f"[Current Data] {var_name}: {result['value']}{change_str} from {source}")
        else:
            print(f"[Current Data] No data for {var_name}")
            fetch_errors.append(var_name)

        # Small delay between requests
        time.sleep(0.2)

    state["current_values"] = current_values
    state["fetch_errors"] = fetch_errors

    if "btc" in current_values:
        state["btc_price"] = current_values["btc"]["value"]

    print(f"[Current Data] Fetched {len(current_values)} values, {len(fetch_errors)} errors")
    return state


def format_current_values_for_prompt(current_values: Dict[str, Any]) -> str:
    """Format current values with changes for inclusion in LLM prompt."""
    if not current_values:
        return "(No current data available)"

    lines = []
    categories = {
        "Crypto": ["btc", "eth"],
        "Liquidity": ["tga", "bank_reserves", "reserves", "fed_balance_sheet", "rrp"],
        "Rates": ["sofr", "fed_funds", "us10y", "us02y"],
        "Markets": ["dxy", "vix", "sp500", "gold", "spy", "qqq"],
    }

    for category, vars in categories.items():
        category_values = []
        for var in vars:
            if var in current_values:
                val = current_values[var]
                formatted = format_value_with_changes(var, val)
                category_values.append(formatted)
        if category_values:
            lines.append(f"**{category}**:")
            for cv in category_values:
                lines.append(f"  - {cv}")

    # Add any uncategorized values
    categorized = set(v for vars in categories.values() for v in vars)
    uncategorized = []
    for var, val in current_values.items():
        if var not in categorized:
            formatted = format_value_with_changes(var, val)
            uncategorized.append(formatted)
    if uncategorized:
        lines.append("**Other**:")
        for uv in uncategorized:
            lines.append(f"  - {uv}")

    return "\n".join(lines)


def format_value_with_changes(var_name: str, val: Dict[str, Any]) -> str:
    """Format a value with its changes."""
    value = val["value"]
    date = val["date"]
    changes = val.get("changes", {})

    # Format the base value
    formatted_value = format_value(var_name, value)

    # Build change string
    change_parts = []

    if changes.get("change_1w"):
        c = changes["change_1w"]
        abs_formatted = format_change_value(var_name, c["absolute"])
        change_parts.append(f"{c['direction']}{abs_formatted} / {c['percentage']:+.1f}% 1w")

    if changes.get("change_1m"):
        c = changes["change_1m"]
        abs_formatted = format_change_value(var_name, c["absolute"])
        change_parts.append(f"{c['direction']}{abs_formatted} / {c['percentage']:+.1f}% 1m")

    result = f"{var_name.upper()}: {formatted_value}"
    if change_parts:
        result += f" ({'; '.join(change_parts)})"

    return result


def format_value(var_name: str, value: float) -> str:
    """Format a value based on variable type."""
    # FRED series use different units:
    # - WTREGEN (TGA), WALCL (Fed BS): Millions of dollars
    # - TOTRESNS (reserves), RRPONTSYD (RRP): Billions of dollars

    # Series reported in billions
    if var_name in ["bank_reserves", "reserves", "rrp"]:
        # FRED data is in billions, so 2941.7 = $2.94T
        if abs(value) >= 1e3:  # Trillions (in billions)
            return f"${value/1e3:.2f}T"
        return f"${value:.0f}B"

    # Series reported in millions
    if var_name in ["tga", "fed_balance_sheet"]:
        # FRED data is in millions, so value of 923042 = $923B
        if abs(value) >= 1e6:  # Trillions (in millions)
            return f"${value/1e6:.2f}T"
        elif abs(value) >= 1e3:  # Billions (in millions)
            return f"${value/1e3:.0f}B"
        return f"${value:.0f}M"

    if var_name in ["btc", "eth", "gold"]:
        return f"${value:,.2f}"

    if var_name in ["sofr", "fed_funds", "us10y", "us02y", "vix"]:
        return f"{value:.2f}%"

    if var_name in ["dxy", "sp500", "spy", "qqq"]:
        return f"{value:.2f}"

    return f"{value:,.2f}"


def format_change_value(var_name: str, change: float) -> str:
    """Format a change value based on variable type."""
    # FRED series in billions
    if var_name in ["bank_reserves", "reserves", "rrp"]:
        if abs(change) >= 1e3:  # Trillions
            return f"${abs(change)/1e3:.2f}T"
        return f"${abs(change):.0f}B"

    # FRED series in millions
    if var_name in ["tga", "fed_balance_sheet"]:
        if abs(change) >= 1e3:  # Billions
            return f"${abs(change)/1e3:.0f}B"
        return f"${abs(change):.0f}M"

    if var_name in ["btc", "eth", "gold"]:
        return f"${abs(change):,.0f}"

    if var_name in ["sofr", "fed_funds", "us10y", "us02y", "vix"]:
        return f"{abs(change):.2f}pp"  # percentage points

    if var_name in ["dxy", "sp500", "spy", "qqq"]:
        return f"{abs(change):.2f}"

    return f"{abs(change):,.2f}"
