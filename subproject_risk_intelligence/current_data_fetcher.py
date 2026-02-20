"""
Current Data Fetcher Module

Fetches current/latest values for extracted variables with period-over-period changes.
Self-contained implementation using requests/yfinance directly.

Uses shared/variable_resolver.py for centralized variable resolution
instead of hard-coded mappings.
"""

import os
import sys
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.variable_resolver import resolve_variable as _resolve_variable
from . import config

# RiskImpactState imported lazily inside fetch_current_data() to allow
# standalone imports of utility functions (resolve_variable, fetch_*_with_history)
# from outside the package context

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")


# ============================================================================
# Variable Resolution (uses shared/variable_resolver.py)
# ============================================================================
# Hard-coded FRED_SERIES and YAHOO_TICKERS dictionaries have been removed.
# Resolution now uses discovered_data_ids.json as the source of truth.
# See shared/variable_resolver.py for the centralized implementation.

# Additional FRED series not in discovered_data_ids.json
# These are common series used in BTC analysis but not yet discovered
ADDITIONAL_FRED_SERIES = {
    "rrp": "RRPONTSYD",
    "fed_balance_sheet": "WALCL",
    "reserves": "TOTRESNS",
    "bank_reserves": "TOTRESNS",
    "us02y": "DGS2",
    "us10y": "DGS10",
    "sofr": "SOFR",
    "fed_funds": "FEDFUNDS",
    "breakeven_inflation": "T5YIFR",
    "ig_corporate_yield": "BAMLC0A4CBBBEY",   # ICE BofA BBB Corporate Yield
    "hy_corporate_yield": "BAMLH0A0HYM2EY",   # ICE BofA US High Yield Effective Yield
    "m2": "M2SL",                               # M2 Money Supply
}

# FRED series that are released monthly (need extended lookback for change calculations)
# Monthly series need ~90 days lookback to get 3 data points for proper change calc
MONTHLY_FRED_SERIES = {
    "TOTRESNS",    # Total Reserves - monthly
    "FEDFUNDS",    # Fed Funds Rate - monthly
    "M2SL",        # M2 Money Supply - monthly
}

# Default lookback days (45 for daily/weekly, 120 for monthly)
DEFAULT_LOOKBACK_DAYS = 45
MONTHLY_LOOKBACK_DAYS = 120


# ============================================================================
# Derived Metrics (Gap 2: standard macro spreads)
# ============================================================================

DERIVED_METRICS = {
    "term_premium": {
        "formula": "us10y - us02y",
        "inputs": ["us10y", "us02y"],
    },
    "real_yield_10y": {
        "formula": "us10y - breakeven_inflation",
        "inputs": ["us10y", "breakeven_inflation"],
    },
    "sofr_spread": {
        "formula": "sofr - fed_funds",
        "inputs": ["sofr", "fed_funds"],
    },
    "equity_risk_premium": {
        "formula": "sp500_earnings_yield - us10y",
        "inputs": ["sp500_earnings_yield", "us10y"],
    },
    "credit_spread_ig": {
        "formula": "ig_corporate_yield - us10y",
        "inputs": ["ig_corporate_yield", "us10y"],
    },
    "credit_spread_hy": {
        "formula": "hy_corporate_yield - us10y",
        "inputs": ["hy_corporate_yield", "us10y"],
    },
    "real_fed_funds": {
        "formula": "fed_funds - breakeven_inflation",
        "inputs": ["fed_funds", "breakeven_inflation"],
    },
    "money_supply_velocity_proxy": {
        "formula": "nominal_gdp_proxy - m2",
        "inputs": ["nominal_gdp_proxy", "m2"],
    },
}


def compute_derived_metrics(current_values: dict) -> dict:
    """
    Compute derived macro metrics from raw values.

    Computes standard macro spreads that traders use:
    - term_premium: us10y - us02y (yield curve slope)
    - real_yield_10y: us10y - breakeven_inflation
    - sofr_spread: sofr - fed_funds

    Args:
        current_values: Dict of variable -> {value, date, source, ...}

    Returns:
        Dict of derived variable -> {value, date, source: "derived", changes}
    """
    derived = {}

    for metric_name, definition in DERIVED_METRICS.items():
        inputs = definition["inputs"]

        if not all(inp in current_values for inp in inputs):
            continue

        input_a = current_values[inputs[0]]
        input_b = current_values[inputs[1]]

        val_a = input_a.get("value")
        val_b = input_b.get("value")

        if val_a is None or val_b is None:
            continue

        derived_value = val_a - val_b

        # Use most recent date from inputs
        date_a = input_a.get("date", "")
        date_b = input_b.get("date", "")
        derived_date = max(date_a, date_b) if date_a and date_b else date_a or date_b

        result = {
            "value": round(derived_value, 4),
            "date": derived_date,
            "source": "derived",
            "formula": definition["formula"],
        }

        # Compute derived changes if both inputs have change data
        changes = {}
        for period in ["change_1w", "change_1m"]:
            change_a = input_a.get("changes", {}).get(period)
            change_b = input_b.get("changes", {}).get(period)
            if change_a and change_b:
                abs_change = change_a["absolute"] - change_b["absolute"]
                # Compute prior derived value for percentage
                prior_value = derived_value - abs_change
                pct_change = (abs_change / abs(prior_value)) * 100 if prior_value != 0 else 0.0
                direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
                changes[period] = {
                    "absolute": round(abs_change, 4),
                    "percentage": round(pct_change, 2),
                    "direction": direction,
                }
        result["changes"] = changes

        derived[metric_name] = result
        print(f"[current_data] {metric_name}: {result['value']:.4f} (derived: {definition['formula']})")

    return derived


def resolve_variable(variable: str) -> Optional[Dict[str, Any]]:
    """
    Resolve variable name to data source and series ID.

    Uses shared/variable_resolver.py as primary source (discovered_data_ids.json).
    Falls back to ADDITIONAL_FRED_SERIES for common series not yet discovered.
    """
    var_lower = variable.lower().strip()

    # Try shared resolver first (uses discovered_data_ids.json + Yahoo fallback)
    result = _resolve_variable(var_lower)
    if result:
        return {"source": result["source"], "series_id": result["series_id"]}

    # Fallback for additional FRED series not yet in discovered_data_ids.json
    if var_lower in ADDITIONAL_FRED_SERIES:
        return {"source": "FRED", "series_id": ADDITIONAL_FRED_SERIES[var_lower]}

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

        # Debug log full FRED response
        try:
            from shared.debug_logger import debug_log_data_fetch
            debug_log_data_fetch("FRED", url, params, data)
        except Exception:
            pass

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

            # Debug log full Yahoo response
            try:
                from shared.debug_logger import debug_log_data_fetch
                debug_log_data_fetch("Yahoo", ticker, {"period": period}, {
                    "rows": len(hist),
                    "history": history,
                })
            except Exception:
                pass

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
        - change_1w: (absolute, percentage, direction) - or previous period for monthly data
        - change_1m: (absolute, percentage, direction)
    """
    if not history or len(history) < 2:
        # Even with only 1 point, we can't calculate changes
        return {}

    latest_value = history[-1][1]
    latest_date_str = history[-1][0]
    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")

    changes = {}

    # Detect if this is monthly data (few points over long period)
    is_monthly = len(history) <= 3

    # Find value from ~1 week ago (5-10 days) for weekly data
    # For monthly data, use previous data point as "prior period"
    week_ago_value = None
    week_ago_date = None

    if is_monthly:
        # For monthly series, use the previous data point
        if len(history) >= 2:
            week_ago_value = history[-2][1]
            week_ago_date = history[-2][0]
    else:
        # For weekly/daily series, look for data 5-10 days ago
        for date_str, value in reversed(history):
            date = datetime.strptime(date_str, "%Y-%m-%d")
            days_diff = (latest_date - date).days
            if 5 <= days_diff <= 10:
                week_ago_value = value
                week_ago_date = date_str
                break

    if week_ago_value and week_ago_value != 0:
        abs_change = latest_value - week_ago_value
        pct_change = (abs_change / week_ago_value) * 100
        direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
        label = "prev" if is_monthly else "1w"
        changes[f"change_{label}"] = {
            "absolute": abs_change,
            "percentage": pct_change,
            "direction": direction,
            "from_date": week_ago_date
        }
        # Also store as change_1w for compatibility
        if is_monthly:
            changes["change_1w"] = changes[f"change_{label}"]

    # Find value from ~1 month ago (25-40 days)
    # For monthly data, try to find data 2 periods back
    month_ago_value = None
    month_ago_date = None

    if is_monthly:
        # For monthly series, use 2 periods back if available
        if len(history) >= 3:
            month_ago_value = history[-3][1]
            month_ago_date = history[-3][0]
    else:
        for date_str, value in reversed(history):
            date = datetime.strptime(date_str, "%Y-%m-%d")
            days_diff = (latest_date - date).days
            if 25 <= days_diff <= 40:
                month_ago_value = value
                month_ago_date = date_str
                break

    if month_ago_value and month_ago_value != 0:
        abs_change = latest_value - month_ago_value
        pct_change = (abs_change / month_ago_value) * 100
        direction = "↑" if abs_change > 0 else "↓" if abs_change < 0 else "→"
        changes["change_1m"] = {
            "absolute": abs_change,
            "percentage": pct_change,
            "direction": direction,
            "from_date": month_ago_date
        }

    return changes


def fetch_current_data(state: "RiskImpactState") -> "RiskImpactState":
    """
    Fetch current values for extracted variables with period-over-period changes.

    Updates state with:
    - current_values: Dict of variable -> {value, date, source, changes}
    - btc_price: Current BTC price
    - fetch_errors: List of failed variables
    """
    # Lazy import to allow standalone imports from outside package context
    from .states import RiskImpactState  # noqa: F401

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

    def fetch_single(var_name):
        """Fetch a single variable's data. Thread-safe."""
        mapping = resolve_variable(var_name)
        if not mapping:
            return (var_name, None, f"Could not resolve: {var_name}")

        source = mapping["source"]
        series_id = mapping["series_id"]

        # Use extended lookback for monthly FRED series
        lookback = MONTHLY_LOOKBACK_DAYS if series_id in MONTHLY_FRED_SERIES else DEFAULT_LOOKBACK_DAYS

        result = None
        if source == "FRED":
            result = fetch_fred_with_history(series_id, lookback)
        elif source == "Yahoo":
            result = fetch_yahoo_with_history(series_id, lookback)

        if result:
            history = result.pop("history", [])
            changes = calculate_changes(history)
            result["changes"] = changes
            return (var_name, result, None)
        else:
            return (var_name, None, f"No data for {var_name}")

    # Parallel fetch with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_single, v): v for v in var_names}
        for future in as_completed(futures):
            var_name, result, error = future.result()
            if result:
                current_values[var_name] = result
                change_str = ""
                changes = result.get("changes", {})
                if changes.get("change_1w"):
                    c = changes["change_1w"]
                    change_str = f" ({c['direction']}{abs(c['percentage']):.1f}% 1w)"
                print(f"[current_data] {var_name}: {result['value']}{change_str}")
            else:
                print(f"[current_data] {error}")
                fetch_errors.append(var_name)

    # Auto-discover unmapped variables (Gap 4)
    if fetch_errors and config.AUTO_DISCOVER_UNMAPPED:
        try:
            unresolved = fetch_errors[:config.MAX_AUTO_DISCOVERIES]
            if unresolved:
                print(f"[Current Data] Auto-discovering {len(unresolved)} unmapped variables: {unresolved}")
                from subproject_variable_mapper.data_id_discovery import discover_data_ids_sync
                for var_name in unresolved:
                    try:
                        discovered = discover_data_ids_sync([var_name])
                        if discovered:
                            # Retry fetch
                            mapping = resolve_variable(var_name)
                            if mapping:
                                source = mapping["source"]
                                series_id = mapping["series_id"]
                                lookback = MONTHLY_LOOKBACK_DAYS if series_id in MONTHLY_FRED_SERIES else DEFAULT_LOOKBACK_DAYS
                                result = None
                                if source == "FRED":
                                    result = fetch_fred_with_history(series_id, lookback)
                                elif source == "Yahoo":
                                    result = fetch_yahoo_with_history(series_id, lookback)
                                if result:
                                    history = result.pop("history", [])
                                    result["changes"] = calculate_changes(history)
                                    current_values[var_name] = result
                                    fetch_errors.remove(var_name)
                                    print(f"[Current Data] Auto-discovered and fetched: {var_name}")
                    except Exception as e:
                        print(f"[Current Data] Auto-discovery failed for {var_name}: {e}")
        except ImportError:
            print("[Current Data] Variable mapper not available for auto-discovery")
        except Exception as e:
            print(f"[Current Data] Auto-discovery error: {e}")

    # Compute derived metrics from raw values (Gap 2)
    derived = compute_derived_metrics(current_values)
    current_values.update(derived)

    state["current_values"] = current_values
    state["fetch_errors"] = fetch_errors

    # Set asset_price for the target asset class
    from .asset_configs import get_asset_config
    asset_cfg = get_asset_config(state.get("asset_class", "btc"))
    primary_var = asset_cfg["always_include_variable"]
    if primary_var in current_values:
        state["asset_price"] = current_values[primary_var]["value"]
    # Backwards compat: also set btc_price if BTC data available
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
        "Rates": ["sofr", "fed_funds", "us10y", "us02y", "term_premium", "real_yield_10y", "sofr_spread",
                  "equity_risk_premium", "credit_spread_ig", "credit_spread_hy", "real_fed_funds", "money_supply_velocity_proxy"],
        "Indices": ["sp500", "nasdaq", "dow", "russell2000", "spy", "qqq"],
        "Sectors": ["igv", "xlk", "smh", "soxx", "xly", "xlf", "xle"],
        "Big Tech": ["googl", "amzn", "msft", "meta", "aapl", "nvda", "orcl"],
        "FX & Commodities": ["dxy", "usdjpy", "eurusd", "gold", "gld"],
        "Volatility": ["vix", "vvix"],
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

    if var_name in ["sofr", "fed_funds", "us10y", "us02y", "vix", "term_premium", "real_yield_10y", "sofr_spread",
                     "equity_risk_premium", "credit_spread_ig", "credit_spread_hy", "real_fed_funds"]:
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

    if var_name in ["sofr", "fed_funds", "us10y", "us02y", "vix", "term_premium", "real_yield_10y", "sofr_spread",
                     "equity_risk_premium", "credit_spread_ig", "credit_spread_hy", "real_fed_funds"]:
        return f"{abs(change):.2f}pp"  # percentage points

    if var_name in ["dxy", "sp500", "spy", "qqq"]:
        return f"{abs(change):.2f}"

    return f"{abs(change):,.2f}"
