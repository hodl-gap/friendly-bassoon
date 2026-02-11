"""
Historical Data Fetcher Module

Fetches historical market data for detected events and calculates metrics.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import math

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .states import BTCImpactState


def fetch_historical_event_data(
    instruments: List[Dict[str, str]],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """
    Fetch data and calculate metrics for each instrument.

    Args:
        instruments: List of instrument dicts [{"ticker": "...", "source": "...", "role": "..."}]
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        {
            "instruments": {
                "USDJPY": {
                    "ticker": "USDJPY=X",
                    "role": "Yen exchange rate",
                    "data": [(date, value), ...],
                    "metrics": {
                        "peak_to_trough_pct": -12.5,
                        "peak_date": "2024-07-31",
                        "peak_value": 161.5,
                        "trough_date": "2024-08-05",
                        "trough_value": 141.7,
                        "recovery_days": 10,
                        "max_single_day_move_pct": -3.4,
                        "total_return_pct": -8.2
                    }
                },
                ...
            },
            "correlations": {
                "USDJPY_vs_BTC": 0.82,
                ...
            },
            "period": {
                "start": "2024-07-25",
                "end": "2024-08-15"
            }
        }
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    print(f"[Historical Data] Fetching data for {len(instruments)} instruments")
    print(f"[Historical Data] Period: {start_date} to {end_date}")

    result = {
        "instruments": {},
        "correlations": {},
        "period": {
            "start": start_date,
            "end": end_date
        }
    }

    # Fetch data for each instrument
    for inst in instruments:
        ticker = inst.get("ticker", "")
        source = inst.get("source", "Yahoo")
        role = inst.get("role", "")

        if not ticker:
            continue

        # Create readable name from ticker
        name = _ticker_to_name(ticker)

        try:
            if source == "Yahoo":
                data = _fetch_yahoo_data(ticker, start_dt, end_dt)
            elif source == "FRED":
                data = _fetch_fred_data(ticker, start_dt, end_dt)
            else:
                print(f"[Historical Data] Unknown source {source} for {ticker}")
                continue

            if not data:
                print(f"[Historical Data] No data for {ticker}")
                continue

            # Calculate metrics
            metrics = _calculate_metrics(data)

            result["instruments"][name] = {
                "ticker": ticker,
                "role": role,
                "data": data,
                "metrics": metrics
            }

            print(f"[Historical Data] {name}: {len(data)} points, {metrics.get('peak_to_trough_pct', 0):.1f}% drawdown")

        except Exception as e:
            print(f"[Historical Data] Error fetching {ticker}: {e}")
            continue

    # Calculate pairwise correlations
    if len(result["instruments"]) >= 2:
        result["correlations"] = _calculate_correlations(result["instruments"])

    return result


def _ticker_to_name(ticker: str) -> str:
    """Convert ticker symbol to readable name."""
    mapping = {
        "BTC-USD": "BTC",
        "ETH-USD": "ETH",
        "^VIX": "VIX",
        "^GSPC": "SP500",
        "^IXIC": "NASDAQ",
        "^TNX": "US10Y",
        "USDJPY=X": "USDJPY",
        "EURUSD=X": "EURUSD",
        "DX-Y.NYB": "DXY",
        "GC=F": "GOLD",
        "CL=F": "OIL",
        "QQQ": "QQQ",
        "SPY": "SPY",
    }
    return mapping.get(ticker, ticker.replace("=X", "").replace("-USD", "").replace("^", ""))


def _fetch_yahoo_data(ticker: str, start_dt: datetime, end_dt: datetime) -> List[Tuple[str, float]]:
    """Fetch data from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        print("[Historical Data] yfinance not installed")
        return []

    try:
        t = yf.Ticker(ticker)
        df = t.history(
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=True
        )

        if df.empty:
            return []

        data = []
        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            data.append((date_str, float(row["Close"])))

        return data

    except Exception as e:
        print(f"[Historical Data] Yahoo error for {ticker}: {e}")
        return []


def _fetch_fred_data(series_id: str, start_dt: datetime, end_dt: datetime) -> List[Tuple[str, float]]:
    """Fetch data from FRED API."""
    import os
    import requests
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.getenv("FRED_API_KEY", "")

    if not api_key:
        print("[Historical Data] No FRED API key")
        return []

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_dt.strftime("%Y-%m-%d"),
            "observation_end": end_dt.strftime("%Y-%m-%d"),
            "sort_order": "asc",
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = []
        for obs in data.get("observations", []):
            if obs["value"] != ".":
                result.append((obs["date"], float(obs["value"])))

        return result

    except Exception as e:
        print(f"[Historical Data] FRED error for {series_id}: {e}")
        return []


def _calculate_metrics(data: List[Tuple[str, float]]) -> Dict[str, Any]:
    """
    Calculate event metrics from price data.

    Returns:
        {
            "peak_to_trough_pct": Drawdown percentage (negative for down),
            "peak_date": Date of peak,
            "peak_value": Value at peak,
            "trough_date": Date of trough,
            "trough_value": Value at trough,
            "recovery_days": Days from trough to 50% recovery (or end),
            "max_single_day_move_pct": Largest single-day percentage move,
            "total_return_pct": Start to end return
        }
    """
    if not data or len(data) < 2:
        return {}

    values = [v for _, v in data]
    dates = [d for d, _ in data]

    # Find peak and trough
    peak_idx = values.index(max(values))
    trough_idx = values.index(min(values))

    peak_value = values[peak_idx]
    peak_date = dates[peak_idx]
    trough_value = values[trough_idx]
    trough_date = dates[trough_idx]

    # Calculate drawdown (from peak to trough in the data)
    # If trough comes before peak, this is a rally not a crash
    if peak_idx < trough_idx:
        # Crash scenario: peak then trough
        drawdown_pct = ((trough_value - peak_value) / peak_value) * 100
    else:
        # Rally scenario: trough then peak
        drawdown_pct = ((peak_value - trough_value) / trough_value) * 100

    # Calculate max single-day move
    daily_returns = []
    for i in range(1, len(values)):
        if values[i - 1] != 0:
            daily_ret = ((values[i] - values[i - 1]) / values[i - 1]) * 100
            daily_returns.append((dates[i], daily_ret))

    max_daily = max(daily_returns, key=lambda x: abs(x[1])) if daily_returns else (None, 0)

    # Calculate recovery (days to recover 50% of the drawdown)
    recovery_days = None
    if peak_idx < trough_idx and trough_value < peak_value:
        # Crash scenario - look for recovery after trough
        half_recovery_level = trough_value + (peak_value - trough_value) * 0.5
        for i in range(trough_idx + 1, len(values)):
            if values[i] >= half_recovery_level:
                recovery_days = i - trough_idx
                break

    # Total return
    total_return_pct = ((values[-1] - values[0]) / values[0]) * 100 if values[0] != 0 else 0

    return {
        "peak_to_trough_pct": round(drawdown_pct, 2),
        "peak_date": peak_date,
        "peak_value": round(peak_value, 2),
        "trough_date": trough_date,
        "trough_value": round(trough_value, 2),
        "recovery_days": recovery_days,
        "max_single_day_move_pct": round(max_daily[1], 2) if max_daily[0] else None,
        "max_single_day_date": max_daily[0],
        "total_return_pct": round(total_return_pct, 2)
    }


def _calculate_correlations(instruments: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculate pairwise correlations between instruments.

    Returns dict like {"BTC_vs_VIX": 0.82, "BTC_vs_USDJPY": 0.75}
    """
    correlations = {}

    names = list(instruments.keys())
    if len(names) < 2:
        return correlations

    # Get BTC data as the base for comparisons (or first instrument)
    base_name = "BTC" if "BTC" in names else names[0]
    base_data = instruments[base_name]["data"]
    base_dates = {d: v for d, v in base_data}

    for name in names:
        if name == base_name:
            continue

        other_data = instruments[name]["data"]
        other_dates = {d: v for d, v in other_data}

        # Find overlapping dates
        common_dates = sorted(set(base_dates.keys()) & set(other_dates.keys()))

        if len(common_dates) < 5:
            continue

        base_values = [base_dates[d] for d in common_dates]
        other_values = [other_dates[d] for d in common_dates]

        corr = _pearson_correlation(base_values, other_values)
        if corr is not None:
            key = f"{base_name}_vs_{name}"
            correlations[key] = round(corr, 2)

    return correlations


def _pearson_correlation(x: List[float], y: List[float]) -> Optional[float]:
    """Calculate Pearson correlation coefficient."""
    if len(x) != len(y) or len(x) < 2:
        return None

    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    # Calculate covariance and standard deviations
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x) / n)
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y) / n)

    if std_x == 0 or std_y == 0:
        return None

    return cov / (std_x * std_y)


def compare_to_current(
    historical_data: Dict[str, Any],
    current_values: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare historical event data to current market values.

    Args:
        historical_data: Output from fetch_historical_event_data()
        current_values: Current market values from state

    Returns:
        {
            "comparisons": {
                "USDJPY": {
                    "then": {"peak": 161.5, "trough": 141.7, "change_pct": -12.5},
                    "now": {"current": 154.3, "change_1m_pct": 3.2},
                    "similar": False,
                    "note": "Current move (+3%) much smaller than Aug 2024 crash (-12.5%)"
                },
                ...
            }
        }
    """
    comparisons = {}

    for name, inst_data in historical_data.get("instruments", {}).items():
        metrics = inst_data.get("metrics", {})

        # Find current value for this instrument
        current = None
        current_name_lower = name.lower()

        for cv_name, cv_data in current_values.items():
            if cv_name.lower() == current_name_lower:
                current = cv_data
                break

        if not current:
            continue

        then_change = metrics.get("peak_to_trough_pct", 0)
        now_change = current.get("changes", {}).get("change_1m", {}).get("percentage", 0)

        # Determine if magnitudes are similar
        similar = abs(abs(then_change) - abs(now_change)) < 5  # Within 5pp

        if abs(then_change) > abs(now_change) * 2:
            note = f"Current move ({now_change:+.1f}%) much smaller than historical ({then_change:+.1f}%)"
        elif abs(now_change) > abs(then_change) * 2:
            note = f"Current move ({now_change:+.1f}%) larger than historical ({then_change:+.1f}%)"
        elif similar:
            note = f"Similar magnitude: then {then_change:+.1f}%, now {now_change:+.1f}%"
        else:
            note = f"Then: {then_change:+.1f}%, Now: {now_change:+.1f}%"

        comparisons[name] = {
            "then": {
                "peak": metrics.get("peak_value"),
                "trough": metrics.get("trough_value"),
                "change_pct": then_change
            },
            "now": {
                "current": current.get("value"),
                "change_1m_pct": now_change
            },
            "similar": similar,
            "note": note
        }

    return {"comparisons": comparisons}


def format_historical_data_for_prompt(historical_event_data: Dict[str, Any]) -> str:
    """
    Format historical event data for inclusion in the LLM impact analysis prompt.

    Args:
        historical_event_data: Full historical event data from state

    Returns:
        Formatted string for prompt
    """
    if not historical_event_data or not historical_event_data.get("event_detected"):
        return ""

    event_name = historical_event_data.get("event_name", "Historical Event")
    period = historical_event_data.get("period", {})
    instruments = historical_event_data.get("instruments", {})
    correlations = historical_event_data.get("correlations", {})
    comparisons = historical_event_data.get("comparison_to_current", {}).get("comparisons", {})

    lines = [
        "## HISTORICAL EVENT COMPARISON (Data-Driven)",
        "",
        f"**Event:** {event_name}",
        f"**Period:** {period.get('start', '?')} to {period.get('end', '?')}",
        "",
        "**What the DATA shows:**"
    ]

    for name, data in instruments.items():
        metrics = data.get("metrics", {})
        change = metrics.get("peak_to_trough_pct", 0)
        peak_date = metrics.get("peak_date", "?")
        trough_date = metrics.get("trough_date", "?")
        role = data.get("role", "")

        line = f"- {name}: {change:+.1f}% (peak {peak_date}, trough {trough_date})"
        if role:
            line += f" [{role}]"
        lines.append(line)

    if correlations:
        lines.append("")
        lines.append("**Correlations during event:**")
        for pair, corr in correlations.items():
            lines.append(f"- {pair.replace('_', ' ')}: {corr:.2f}")

    if comparisons:
        lines.append("")
        lines.append("**Then vs Now:**")
        for name, comp in comparisons.items():
            lines.append(f"- {name}: {comp.get('note', '')}")

    lines.append("")

    return "\n".join(lines)
