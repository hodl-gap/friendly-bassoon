"""
Indicator Extremes Module

Programmatically finds dates when an indicator hit extreme percentile readings,
fetches real forward returns from Yahoo/FRED for correlated assets, and returns
verified numbers. Zero LLM calls — pure mechanical computation.
"""

import sys
import bisect
import csv as csv_module
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import median, mean

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Full-History Fetchers
# =============================================================================

def fetch_full_csv_series(series_id: str) -> List[Tuple[str, float]]:
    """Read entire CSV series file. Returns [(date, value), ...]."""
    csv_path = (
        Path(__file__).parent.parent
        / "subproject_data_collection" / "data" / "csv_series"
        / f"{series_id}.csv"
    )

    if not csv_path.exists():
        print(f"[IndicatorExtremes] CSV file not found: {csv_path}")
        return []

    history = []
    with open(csv_path, newline="") as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            date_str = row.get("date", "").strip()
            value_str = row.get("value", "").strip()
            if not date_str or not value_str:
                continue
            try:
                history.append((date_str, float(value_str)))
            except ValueError:
                continue

    return history


def fetch_full_fred_series(series_id: str, start_year: int = 1990) -> List[Tuple[str, float]]:
    """Fetch entire FRED series from start_year to now."""
    from .historical_data_fetcher import _fetch_fred_data

    start_dt = datetime(start_year, 1, 1)
    end_dt = datetime.now()

    return _fetch_fred_data(series_id, start_dt, end_dt)


def fetch_full_yahoo_series(ticker: str, start_year: int = 1990) -> List[Tuple[str, float]]:
    """Fetch entire Yahoo series from start_year to now."""
    from .historical_data_fetcher import _fetch_yahoo_data

    start_dt = datetime(start_year, 1, 1)
    end_dt = datetime.now()

    return _fetch_yahoo_data(ticker, start_dt, end_dt)


def fetch_full_series(variable_name: str) -> Tuple[List[Tuple[str, float]], str]:
    """
    Resolve variable and fetch full history.

    Returns:
        (history, source_label) where history is [(date, value), ...]
    """
    from .current_data_fetcher import resolve_variable

    resolved = resolve_variable(variable_name)
    if not resolved:
        print(f"[IndicatorExtremes] Cannot resolve variable: {variable_name}")
        return [], ""

    source = resolved["source"]
    series_id = resolved["series_id"]

    if source == "CSV":
        history = fetch_full_csv_series(series_id)
        label = f"CSV:{series_id}"
    elif source == "FRED":
        history = fetch_full_fred_series(series_id)
        label = f"FRED:{series_id}"
    elif source == "Yahoo":
        history = fetch_full_yahoo_series(series_id)
        label = f"Yahoo:{series_id}"
    else:
        print(f"[IndicatorExtremes] Unknown source: {source}")
        return [], ""

    print(f"[IndicatorExtremes] Fetched {len(history)} points for {variable_name} from {label}")
    return history, label


# =============================================================================
# Extreme Detection
# =============================================================================

def find_extreme_dates(
    series: List[Tuple[str, float]],
    percentile: float = 95,
    direction: str = "above",
    cluster_gap_days: int = 10,
    max_episodes: int = 15,
) -> List[Dict[str, Any]]:
    """
    Find dates when the indicator hit extreme percentile readings.

    Args:
        series: [(date_str, value), ...] sorted chronologically
        percentile: e.g. 95 = top 5% (or bottom 5% if direction="below")
        direction: "above" (high extremes) or "below" (low extremes)
        cluster_gap_days: trading days gap to cluster adjacent extremes
        max_episodes: maximum episodes to return

    Returns:
        List of episode dicts sorted most-recent-first, each containing:
        - date, value, percentile_rank, episode_start, episode_end, days_in_episode
    """
    if len(series) < 20:
        print(f"[IndicatorExtremes] Series too short ({len(series)} points)")
        return []

    values = [v for _, v in series]
    sorted_values = sorted(values)
    n = len(sorted_values)

    # Compute threshold
    if direction == "above":
        threshold_idx = min(int(n * percentile / 100), n - 1)
        threshold = sorted_values[threshold_idx]
    else:  # below
        threshold_idx = max(int(n * (100 - percentile) / 100), 0)
        threshold = sorted_values[threshold_idx]

    # Find all dates exceeding threshold
    extreme_points = []
    for i, (date_str, value) in enumerate(series):
        is_extreme = (
            (direction == "above" and value >= threshold) or
            (direction == "below" and value <= threshold)
        )
        if is_extreme:
            rank = bisect.bisect_right(sorted_values, value) / n * 100
            extreme_points.append({
                "idx": i,
                "date": date_str,
                "value": value,
                "percentile_rank": round(rank, 1),
            })

    if not extreme_points:
        return []

    # Cluster adjacent extreme days into episodes
    episodes = []
    current_cluster = [extreme_points[0]]

    for i in range(1, len(extreme_points)):
        gap = extreme_points[i]["idx"] - extreme_points[i - 1]["idx"]
        if gap <= cluster_gap_days:
            current_cluster.append(extreme_points[i])
        else:
            episodes.append(current_cluster)
            current_cluster = [extreme_points[i]]
    episodes.append(current_cluster)

    # Represent each episode by its most extreme reading
    result = []
    for cluster in episodes:
        if direction == "above":
            peak = max(cluster, key=lambda p: p["value"])
        else:
            peak = min(cluster, key=lambda p: p["value"])

        result.append({
            "date": peak["date"],
            "value": peak["value"],
            "percentile_rank": peak["percentile_rank"],
            "episode_start": cluster[0]["date"],
            "episode_end": cluster[-1]["date"],
            "days_in_episode": len(cluster),
        })

    # Sort most-recent-first, cap at max_episodes
    result.sort(key=lambda e: e["date"], reverse=True)
    return result[:max_episodes]


# =============================================================================
# Forward Return Computation
# =============================================================================

FORWARD_WINDOWS = {"1wk": 5, "2wk": 10, "1mo": 21, "3mo": 63}


def compute_forward_returns(
    episode_date: str,
    asset_ticker: str,
    windows: Dict[str, int] = None,
) -> Dict[str, Optional[float]]:
    """
    Compute forward returns from episode_date for an asset.

    Args:
        episode_date: YYYY-MM-DD
        asset_ticker: Yahoo ticker (e.g., "SPY", "QQQ")
        windows: {label: trading_days} e.g. {"1wk": 5, "1mo": 21}

    Returns:
        {window_label: pct_return} e.g. {"1wk": -2.3, "1mo": 3.2}
    """
    if windows is None:
        windows = FORWARD_WINDOWS

    from .historical_data_fetcher import _fetch_yahoo_data

    max_days = max(windows.values())
    start_dt = datetime.strptime(episode_date, "%Y-%m-%d")
    # Fetch enough calendar days to cover max trading days + buffer
    end_dt = start_dt + timedelta(days=int(max_days * 1.6) + 10)

    data = _fetch_yahoo_data(asset_ticker, start_dt, end_dt)
    if not data or len(data) < 2:
        return {label: None for label in windows}

    base_price = data[0][1]
    if base_price == 0:
        return {label: None for label in windows}

    returns = {}
    for label, trading_days in windows.items():
        if trading_days < len(data):
            end_price = data[trading_days][1]
            returns[label] = round((end_price - base_price) / base_price * 100, 2)
        else:
            returns[label] = None

    return returns


def compute_all_forward_returns(
    episodes: List[Dict[str, Any]],
    asset_tickers: List[str],
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """
    Compute forward returns for all episodes x assets in parallel.

    Enriches each episode dict with forward_returns keyed by asset name.
    """
    from .historical_data_fetcher import _ticker_to_name

    def _fetch_one(episode_date: str, ticker: str) -> Tuple[str, str, Dict]:
        try:
            returns = compute_forward_returns(episode_date, ticker)
        except Exception as e:
            print(f"[IndicatorExtremes] Forward return error {ticker} @ {episode_date}: {e}")
            returns = {label: None for label in FORWARD_WINDOWS}
        name = _ticker_to_name(ticker)
        return episode_date, name, returns

    # Build tasks
    tasks = []
    for ep in episodes:
        for ticker in asset_tickers:
            tasks.append((ep["date"], ticker))

    # Execute in parallel
    results = {}  # (date, asset_name) -> returns
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_one, date, ticker): (date, ticker)
            for date, ticker in tasks
        }
        for future in as_completed(futures):
            ep_date, asset_name, returns = future.result()
            results[(ep_date, asset_name)] = returns

    # Enrich episodes
    for ep in episodes:
        ep["forward_returns"] = {}
        for ticker in asset_tickers:
            name = _ticker_to_name(ticker)
            ep["forward_returns"][name] = results.get((ep["date"], name), {})

    return episodes


# =============================================================================
# Aggregation
# =============================================================================

def aggregate_extreme_episodes(
    episodes: List[Dict[str, Any]],
    primary_asset: str = "SPY",
) -> Dict[str, Any]:
    """
    Aggregate forward returns across all episodes.

    Returns per-asset window stats, direction signal, and summary string.
    """
    per_asset = {}

    # Collect all asset names from episodes
    asset_names = set()
    for ep in episodes:
        for name in ep.get("forward_returns", {}).keys():
            asset_names.add(name)

    for asset_name in sorted(asset_names):
        per_asset[asset_name] = {}
        for window_label in FORWARD_WINDOWS.keys():
            values = []
            for ep in episodes:
                ret = ep.get("forward_returns", {}).get(asset_name, {}).get(window_label)
                if ret is not None:
                    values.append(ret)

            if values:
                per_asset[asset_name][window_label] = {
                    "median": round(median(values), 2),
                    "mean": round(mean(values), 2),
                    "pct_positive": round(sum(1 for v in values if v > 0) / len(values) * 100),
                    "count": len(values),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                }

    # Direction signal from primary asset 1mo median
    direction_signal = "neutral"
    primary_1mo = per_asset.get(primary_asset, {}).get("1mo", {})
    if primary_1mo:
        med = primary_1mo["median"]
        if med < -3:
            direction_signal = "bearish"
        elif med > 3:
            direction_signal = "bullish"

    # Summary string
    ep_count = len(episodes)
    primary_stats = per_asset.get(primary_asset, {}).get("1mo", {})
    if primary_stats:
        summary = (
            f"{ep_count} extreme episodes; {primary_asset} median "
            f"{primary_stats['median']:+.1f}% at 1mo "
            f"({primary_stats['pct_positive']}% positive)"
        )
    else:
        summary = f"{ep_count} extreme episodes; no {primary_asset} data"

    return {
        "per_asset": per_asset,
        "direction_signal": direction_signal,
        "summary": summary,
        "episode_count": ep_count,
    }


# =============================================================================
# Prompt Formatting
# =============================================================================

def format_extremes_for_prompt(
    variable_name: str,
    percentile: float,
    direction: str,
    episodes: List[Dict[str, Any]],
    aggregated: Dict[str, Any],
) -> str:
    """Format indicator extremes as a prompt section."""
    lines = [
        "## DATA-VERIFIED INDICATOR EXTREMES",
        "",
        f"**Indicator**: {variable_name} (top {100 - percentile:.0f}% {direction} readings)",
        f"**Episodes found**: {aggregated['episode_count']}",
        f"**Direction signal**: {aggregated['direction_signal']}",
        f"**Summary**: {aggregated['summary']}",
        "",
    ]

    # Aggregate table: asset x window
    per_asset = aggregated.get("per_asset", {})
    if per_asset:
        lines.append("**Aggregate forward returns (median / pct positive):**")
        lines.append("")

        window_labels = list(FORWARD_WINDOWS.keys())
        header = "| Asset | " + " | ".join(window_labels) + " |"
        separator = "|-------|" + "|".join(["-------"] * len(window_labels)) + "|"
        lines.append(header)
        lines.append(separator)

        for asset_name, windows in per_asset.items():
            cells = []
            for wl in window_labels:
                stats = windows.get(wl, {})
                if stats:
                    cells.append(f"{stats['median']:+.1f}% ({stats['pct_positive']}%+)")
                else:
                    cells.append("N/A")
            lines.append(f"| {asset_name} | " + " | ".join(cells) + " |")

        lines.append("")

    # Per-episode detail (8 most recent)
    display_episodes = episodes[:8]
    if display_episodes:
        lines.append(f"**Per-episode detail ({len(display_episodes)} most recent):**")
        lines.append("")

        for ep in display_episodes:
            date = ep["date"]
            value = ep["value"]
            pct_rank = ep["percentile_rank"]
            days = ep["days_in_episode"]

            lines.append(
                f"- **{date}**: value={value:.3f} (percentile {pct_rank:.0f}%, "
                f"{days}-day episode)"
            )

            for asset_name, returns in ep.get("forward_returns", {}).items():
                parts = []
                for wl in FORWARD_WINDOWS.keys():
                    ret = returns.get(wl)
                    if ret is not None:
                        parts.append(f"{wl}: {ret:+.1f}%")
                    else:
                        parts.append(f"{wl}: N/A")
                lines.append(f"  {asset_name}: {', '.join(parts)}")

        lines.append("")

    return "\n".join(lines)
