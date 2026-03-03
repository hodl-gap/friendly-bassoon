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
            "source": "csv_mechanical",
        })

    # Hybrid selection: top N most extreme + top N most recent (deduplicated)
    # This avoids recency bias that would discard informative historical episodes
    # (e.g., 2008 crisis, 2020 COVID, 2022 Q4 extremes)
    half = max(max_episodes // 2, 1)

    # Top N by extremity (absolute value for above, inverse for below)
    by_extremity = sorted(result, key=lambda e: abs(e["value"]), reverse=True)
    extreme_picks = by_extremity[:half]
    extreme_dates = {e["date"] for e in extreme_picks}

    # Top N by recency (excluding already-picked)
    by_recency = sorted(result, key=lambda e: e["date"], reverse=True)
    recent_picks = [e for e in by_recency if e["date"] not in extreme_dates][:max_episodes - len(extreme_picks)]

    # Merge and sort by date for display
    selected = extreme_picks + recent_picks
    selected.sort(key=lambda e: e["date"], reverse=True)
    return selected


def validate_external_dates(
    series: List[Tuple[str, float]],
    external_dates: List[str],
    percentile_threshold: float = 75,
    direction: str = "above",
    date_tolerance_days: int = 5,
) -> List[Dict[str, Any]]:
    """
    Validate external dates against the actual indicator series.

    For each date, find the nearest trading day in the series,
    look up the actual value, compute percentile rank, and return
    only dates where the indicator was genuinely extreme.

    Returns episodes in the same format as find_extreme_dates().
    """
    if len(series) < 20:
        return []

    # Sorted dates for nearest-match search
    series_dates = [datetime.strptime(d, "%Y-%m-%d") for d, _ in series]

    # Sorted values for percentile computation
    sorted_values = sorted(v for _, v in series)
    n = len(sorted_values)

    validated = []
    for ext_date_str in external_dates:
        try:
            ext_dt = datetime.strptime(ext_date_str, "%Y-%m-%d")
        except ValueError:
            print(f"[IndicatorExtremes] Skipping invalid date: {ext_date_str}")
            continue

        # Find nearest trading day within tolerance
        best_match = None
        best_gap = None
        for i, s_dt in enumerate(series_dates):
            gap = abs((s_dt - ext_dt).days)
            if gap <= date_tolerance_days:
                if best_gap is None or gap < best_gap:
                    best_match = i
                    best_gap = gap

        if best_match is None:
            print(f"[IndicatorExtremes] {ext_date_str}: no trading day within "
                  f"{date_tolerance_days} days — skipped")
            continue

        matched_date = series[best_match][0]
        matched_value = series[best_match][1]

        # Compute percentile rank
        rank = bisect.bisect_right(sorted_values, matched_value) / n * 100

        # Check if extreme enough
        if direction == "above":
            is_extreme = rank >= percentile_threshold
        else:
            is_extreme = rank <= (100 - percentile_threshold)

        if not is_extreme:
            print(f"[IndicatorExtremes] {ext_date_str} (matched {matched_date}): "
                  f"value={matched_value:.3f}, percentile {rank:.0f} — below threshold, rejected")
            continue

        print(f"[IndicatorExtremes] {ext_date_str} (matched {matched_date}): "
              f"value={matched_value:.3f}, percentile {rank:.0f} — VALIDATED")

        validated.append({
            "date": matched_date,
            "value": matched_value,
            "percentile_rank": round(rank, 1),
            "episode_start": matched_date,
            "episode_end": matched_date,
            "days_in_episode": 1,
            "source": "web_search",
        })

    return validated


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
            source_tag = " [web-search]" if ep.get("source") == "web_search" else ""

            lines.append(
                f"- **{date}**: value={value:.3f} (percentile {pct_rank:.0f}%, "
                f"{days}-day episode){source_tag}"
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


# =============================================================================
# Mechanical Episode Characterization (Regime Context)
# =============================================================================

CORE_REGIME_VARIABLES = [
    # Existing
    {"normalized": "vix", "ticker": "^VIX", "source": "Yahoo"},
    {"normalized": "sp500", "ticker": "^GSPC", "source": "Yahoo"},
    {"normalized": "us10y", "ticker": "DGS10", "source": "FRED"},
    {"normalized": "us02y", "ticker": "DGS2", "source": "FRED"},
    {"normalized": "fed_funds", "ticker": "DFF", "source": "FRED"},
    {"normalized": "dxy", "ticker": "DX-Y.NYB", "source": "Yahoo"},
    {"normalized": "gold", "ticker": "GC=F", "source": "Yahoo"},
    # New: growth/inflation for macro 2x2
    {"normalized": "oecd_cli", "ticker": "USALOLITONOSTSAM", "source": "FRED"},
    {"normalized": "breakeven_inflation", "ticker": "T5YIFR", "source": "FRED"},
    # New: credit for risk appetite
    {"normalized": "hy_corporate_yield", "ticker": "BAMLH0A0HYM2EY", "source": "FRED"},
]

# Variable → regime dimension mapping for z-score similarity
VARIABLE_DIMENSION_MAP = {
    "oecd_cli": "macro",
    "breakeven_inflation": "macro",
    "fed_funds": "policy",
    "vix": "risk",
    "hy_corporate_yield": "risk",
    "us10y": "curve",
    "us02y": "curve",
    "sp500": "general",
    "dxy": "general",
    "gold": "general",
}


def build_regime_variables(extracted_variables: list) -> list:
    """
    Core 7 + query-specific variables from Phase 2.

    Phase 2 (data grounding agent) already extracted and resolved
    variables relevant to this query (e.g., for a PCR query it may
    have extracted 'vvix', 'hyg', 'qqq', 'iwm'). We reuse those
    so the regime fingerprint is adaptive per query without an
    extra LLM call.
    """
    core_names = {v["normalized"] for v in CORE_REGIME_VARIABLES}
    combined = list(CORE_REGIME_VARIABLES)

    for var in extracted_variables:
        normalized = var.get("normalized", "")
        if normalized and normalized not in core_names:
            from .current_data_fetcher import resolve_variable
            resolved = resolve_variable(normalized)
            if resolved:
                combined.append({
                    "normalized": normalized,
                    "ticker": resolved["series_id"],
                    "source": resolved["source"],
                })
                core_names.add(normalized)

    return combined


def _prefetch_regime_histories(
    regime_variables: list,
) -> Dict[str, List[Tuple[str, float]]]:
    """Fetch full history for each regime variable once.

    Returns {normalized_name: [(date, value), ...]} sorted chronologically.
    Uses fetch_full_series() for FRED/Yahoo/CSV routing.
    """
    histories = {}

    def _fetch_one(var: dict) -> Tuple[str, List[Tuple[str, float]]]:
        name = var["normalized"]
        source = var["source"]
        ticker = var["ticker"]
        try:
            if source == "FRED":
                data = fetch_full_fred_series(ticker, start_year=1960)
            elif source == "Yahoo":
                data = fetch_full_yahoo_series(ticker, start_year=1990)
            elif source == "CSV":
                data = fetch_full_csv_series(ticker)
            else:
                data = []
        except Exception as e:
            print(f"[RegimePreFetch] Error fetching {name}: {e}")
            data = []
        return name, data

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_fetch_one, v): v["normalized"] for v in regime_variables}
        for future in as_completed(futures):
            name, data = future.result()
            if data:
                histories[name] = data
                print(f"[RegimePreFetch] {name}: {len(data)} points "
                      f"({data[0][0]} to {data[-1][0]})")
            else:
                print(f"[RegimePreFetch] {name}: no data")

    return histories


def _lookup_value_at_date(
    history: List[Tuple[str, float]],
    target_date: str,
    window_days: int = 7,
) -> Optional[float]:
    """Binary search for nearest value within +/-window_days."""
    if not history:
        return None

    # Binary search for target date position
    dates = [d for d, _ in history]
    idx = bisect.bisect_left(dates, target_date)

    # Search around the insertion point for closest match within window
    best_val = None
    best_gap = window_days + 1
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")

    for i in range(max(0, idx - window_days), min(len(history), idx + window_days + 1)):
        try:
            dt = datetime.strptime(history[i][0], "%Y-%m-%d")
        except ValueError:
            continue
        gap = abs((dt - target_dt).days)
        if gap <= window_days and gap < best_gap:
            best_gap = gap
            best_val = history[i][1]

    return best_val


def _percentile_rank(value: float, sorted_values: List[float]) -> float:
    """Compute percentile rank (0-100) of value in sorted distribution."""
    if not sorted_values:
        return 50.0
    return bisect.bisect_right(sorted_values, value) / len(sorted_values) * 100


def _is_rising(
    history: List[Tuple[str, float]],
    target_date: str,
    short_window: int = 63,
    long_window: int = 126,
    max_staleness_days: int = 90,
) -> Optional[bool]:
    """Determine if a series is rising using EIB direction approach.

    Compares short-term trailing average vs long-term trailing average.
    "Rising" = short MA > long MA (recent trend above longer trend).

    This is the standard institutional approach (EIB 2019, Bridgewater):
    regime = direction of change, not absolute level.

    Args:
        history: Full sorted history [(date, value), ...]
        target_date: Date to evaluate direction at
        short_window: Trading days for short MA (~3 months = 63)
        long_window: Trading days for long MA (~6 months = 126)
        max_staleness_days: If the most recent data point is older than
            this many days before target_date, return None (stale data).

    Returns:
        True if rising, False if falling, None if insufficient or stale data.
    """
    # Get all entries up to target_date
    entries_before = [(d, v) for d, v in history if d <= target_date]
    if len(entries_before) < long_window:
        return None
    # Check staleness: most recent data point must be within max_staleness_days
    last_date_str = entries_before[-1][0]
    try:
        last_dt = datetime.strptime(last_date_str, "%Y-%m-%d")
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        if (target_dt - last_dt).days > max_staleness_days:
            return None
    except ValueError:
        pass
    vals_before = [v for _, v in entries_before]
    short_ma = mean(vals_before[-short_window:])
    long_ma = mean(vals_before[-long_window:])
    return short_ma > long_ma


def _label_regime_multi(
    conditions: dict,
    histories: dict,
) -> Dict[str, str]:
    """Multi-dimensional regime label using EIB direction-based approach.

    Macro 2×2 uses direction of change (3m MA vs 6m MA), not percentile
    level. This follows Bridgewater All Weather / EIB 2019: regime is
    defined by whether growth and inflation are rising or falling.

    Policy/risk/curve dimensions use 20-year rolling window percentiles
    for level classification (these are supplementary context, not the
    core regime definition).

    Returns:
        {
            "macro": "goldilocks|reflation|stagflation|deflation",
            "policy": "easy|neutral|tight",
            "risk": "risk-on|neutral|risk-off",
            "curve": "inverted|flat|normal|steep",
        }
    """
    def _val(name):
        entry = conditions.get(name, {})
        return entry.get("value") if isinstance(entry, dict) else None

    def _pct(name, value, window_years=20):
        """Get percentile rank from pre-fetched history.

        Uses trailing window_years of data to avoid dilution from
        structurally different regimes (e.g., 1970s/80s rates).
        """
        hist = histories.get(name, [])
        if not hist or value is None:
            return None
        if window_years and len(hist) > 100:
            cutoff_year = datetime.now().year - window_years
            cutoff_date = f"{cutoff_year}-01-01"
            recent = [v for d, v in hist if d >= cutoff_date]
            if len(recent) >= 50:
                sorted_vals = sorted(recent)
                return _percentile_rank(value, sorted_vals)
        sorted_vals = sorted(v for _, v in hist)
        return _percentile_rank(value, sorted_vals)

    # Infer episode date from conditions (for direction computation)
    episode_date = None
    for name in conditions:
        entry = conditions[name]
        if isinstance(entry, dict) and entry.get("date"):
            episode_date = entry["date"]
            break
    if not episode_date:
        episode_date = datetime.now().strftime("%Y-%m-%d")

    result = {}

    # --- Macro 2×2: growth × inflation (direction-based, EIB approach) ---
    #
    # Growth: OECD CLI direction (primary), yield curve spread direction (fallback)
    # Inflation: breakeven inflation direction
    # "Rising" = 3-month MA > 6-month MA

    # Growth direction
    growth_rising = None
    cli_hist = histories.get("oecd_cli", [])
    if cli_hist:
        growth_rising = _is_rising(cli_hist, episode_date)

    if growth_rising is None:
        # Fallback: yield curve spread direction as growth proxy
        hist_10y = histories.get("us10y", [])
        hist_02y = histories.get("us02y", [])
        if hist_10y and hist_02y:
            dates_02y = dict(hist_02y)
            spread_series = [(d, v10 - dates_02y[d])
                             for d, v10 in hist_10y
                             if d in dates_02y]
            if spread_series:
                growth_rising = _is_rising(spread_series, episode_date)

    # Inflation direction
    inflation_rising = None
    be_hist = histories.get("breakeven_inflation", [])
    if be_hist:
        inflation_rising = _is_rising(be_hist, episode_date)

    if growth_rising is not None and inflation_rising is not None:
        if growth_rising and not inflation_rising:
            result["macro"] = "goldilocks"
        elif growth_rising and inflation_rising:
            result["macro"] = "reflation"
        elif not growth_rising and inflation_rising:
            result["macro"] = "stagflation"
        else:
            result["macro"] = "deflation"
    else:
        result["macro"] = "unknown"

    # --- Policy: fed_funds percentile (20-year window) ---
    ff_val = _val("fed_funds")
    ff_pct = _pct("fed_funds", ff_val, window_years=20)
    if ff_pct is not None:
        if ff_pct < 20:
            result["policy"] = "easy"
        elif ff_pct > 80:
            result["policy"] = "tight"
        else:
            result["policy"] = "neutral"
    else:
        result["policy"] = "unknown"

    # --- Risk: VIX percentile ---
    vix_val = _val("vix")
    vix_pct = _pct("vix", vix_val)
    if vix_pct is not None:
        if vix_pct < 25:
            result["risk"] = "risk-on"
        elif vix_pct > 75:
            result["risk"] = "risk-off"
        else:
            result["risk"] = "neutral"
    else:
        result["risk"] = "unknown"

    # --- Curve: (us10y - us02y) percentile ---
    us10y_val = _val("us10y")
    us02y_val = _val("us02y")
    if us10y_val is not None and us02y_val is not None:
        spread = us10y_val - us02y_val
        # Compute spread percentile from paired histories
        hist_10y = histories.get("us10y", [])
        hist_02y = histories.get("us02y", [])
        if hist_10y and hist_02y:
            # Build spread history from overlapping dates
            dates_02y = dict(hist_02y)
            spread_vals = []
            for d, v10 in hist_10y:
                v02 = dates_02y.get(d)
                if v02 is not None:
                    spread_vals.append(v10 - v02)
            if spread_vals:
                sorted_spreads = sorted(spread_vals)
                spread_pct = _percentile_rank(spread, sorted_spreads)
                if spread_pct < 10:
                    result["curve"] = "inverted"
                elif spread_pct < 40:
                    result["curve"] = "flat"
                elif spread_pct < 75:
                    result["curve"] = "normal"
                else:
                    result["curve"] = "steep"
            else:
                result["curve"] = "unknown"
        else:
            result["curve"] = "unknown"
    else:
        result["curve"] = "unknown"

    return result


def _format_regime_label(regime_detail: Dict[str, str]) -> str:
    """Format multi-dimensional regime dict as a display string."""
    parts = []
    for dim in ["macro", "policy", "risk", "curve"]:
        val = regime_detail.get(dim, "unknown")
        if val != "unknown":
            parts.append(f"{dim}:{val}")
    return ", ".join(parts) if parts else "unknown"


def _compute_similarity_zscore(
    conditions_then: dict,
    current_conditions: dict,
    histories: dict,
) -> Dict[str, float]:
    """Z-score normalized similarity, per-dimension + overall.

    For each variable:
    1. Compute z-score: (value - mean) / stddev from full history
    2. Similarity per variable: max(0, 1 - |z_then - z_now| / 4)
    3. Group variables into dimensions, average within dimension
    4. Overall = average of dimension scores

    Returns:
        {
            "macro": 0.85,
            "policy": 0.92,
            "risk": 0.71,
            "curve": 0.88,
            "overall": 0.84,
        }
    """
    # Compute z-scores for each variable using 20-year window
    var_similarities = {}
    cutoff_year = datetime.now().year - 20
    cutoff_date = f"{cutoff_year}-01-01"

    for name in set(list(conditions_then.keys()) + list(current_conditions.keys())):
        then_entry = conditions_then.get(name, {})
        then_val = then_entry.get("value") if isinstance(then_entry, dict) else None
        now_entry = current_conditions.get(name, {})
        now_val = now_entry.get("value") if isinstance(now_entry, dict) else None

        hist = histories.get(name, [])
        if then_val is None or now_val is None or not hist or len(hist) < 20:
            continue

        # Use 20-year window if enough data, else full history
        recent = [v for d, v in hist if d >= cutoff_date]
        values = recent if len(recent) >= 50 else [v for _, v in hist]
        mu = mean(values)
        variance = sum((v - mu) ** 2 for v in values) / len(values)
        sigma = variance ** 0.5

        if sigma < 1e-10:
            continue

        z_then = (then_val - mu) / sigma
        z_now = (now_val - mu) / sigma
        sim = max(0.0, 1.0 - abs(z_then - z_now) / 4.0)
        var_similarities[name] = sim

    if not var_similarities:
        return {"overall": 0.0}

    # Group by dimension
    dim_scores = {}
    for name, sim in var_similarities.items():
        dim = VARIABLE_DIMENSION_MAP.get(name, "general")
        if dim not in dim_scores:
            dim_scores[dim] = []
        dim_scores[dim].append(sim)

    result = {}
    for dim, scores in dim_scores.items():
        result[dim] = round(mean(scores), 2)

    # Overall = average of all dimension scores
    if result:
        result["overall"] = round(mean(result.values()), 2)
    else:
        result["overall"] = 0.0

    return result


# Keep old functions as thin wrappers for any external callers
def _compute_similarity(conditions_then: dict, current_values: dict) -> float:
    """Compare macro conditions at episode date vs now. Returns 0-1.

    Legacy wrapper — delegates to _compute_similarity_zscore when histories
    are not available (falls back to simple percentage difference).
    """
    matches = 0
    total = 0
    for name in conditions_then:
        then_entry = conditions_then.get(name, {})
        then_val = then_entry.get("value") if isinstance(then_entry, dict) else None
        now_entry = current_values.get(name, {})
        now_val = now_entry.get("value") if isinstance(now_entry, dict) else None
        if then_val is not None and now_val is not None and then_val != 0:
            pct_diff = abs(then_val - now_val) / abs(then_val)
            matches += max(0, 1 - pct_diff)
            total += 1
    return matches / total if total > 0 else 0


def _label_regime(conditions: dict) -> str:
    """Mechanical regime label from macro conditions.

    Legacy wrapper — used when histories are not available.
    """
    def _val(name):
        entry = conditions.get(name, {})
        return entry.get("value", 0) if isinstance(entry, dict) else 0

    vix = _val("vix")
    ff = _val("fed_funds")
    us10y = _val("us10y")
    us02y = _val("us02y")

    parts = []
    if vix > 30:
        parts.append("high-vol")
    elif vix < 15:
        parts.append("low-vol")

    if ff > 4:
        parts.append("tight-policy")
    elif ff < 1:
        parts.append("ZIRP")
    elif ff < 2.5:
        parts.append("easy-policy")

    if us10y - us02y < 0:
        parts.append("inverted-curve")
    elif us10y - us02y > 1.5:
        parts.append("steep-curve")

    return ", ".join(parts) if parts else "neutral"


def characterize_mechanical_episodes(
    episodes: List[Dict[str, Any]],
    current_values: Dict[str, Any],
    regime_variables: List[Dict[str, str]],
    max_episodes: int = 20,
) -> List[Dict[str, Any]]:
    """
    For each mechanical episode, look up macro conditions from pre-fetched
    histories and compute multi-dimensional regime labels + z-score similarity.

    Pre-fetches full history once (~10 API calls total) instead of
    per-episode fetches (previously N_episodes x N_variables calls).

    Returns episodes enriched with:
      - conditions: {variable: {value, date, source}} at episode date
      - similarity_score: float (0-1) vs current conditions (backward compat)
      - similarity_detail: {dimension: score} per-dimension similarity
      - regime_label: str formatted from multi-dimensional label (backward compat)
      - regime_detail: {macro, policy, risk, curve} per-dimension labels
    """
    # Cap episodes (sorted most-recent-first already)
    to_characterize = episodes[:max_episodes]

    print(f"[IndicatorExtremes] Characterizing {len(to_characterize)} episodes "
          f"with {len(regime_variables)} regime variables...")
    print(f"[IndicatorExtremes] Pre-fetching full histories (one-time)...")

    # Step 1: Pre-fetch all histories once
    histories = _prefetch_regime_histories(regime_variables)

    print(f"[IndicatorExtremes] Pre-fetch complete: {len(histories)} variables with data")

    # Build current conditions dict from current_values for similarity
    current_conditions = {}
    for name, hist in histories.items():
        # Use the most recent value from pre-fetched history as fallback
        entry = current_values.get(name, {})
        if isinstance(entry, dict) and entry.get("value") is not None:
            current_conditions[name] = entry
        elif hist:
            # Fallback to latest from history
            current_conditions[name] = {"value": hist[-1][1], "date": hist[-1][0], "source": "history"}

    # Current regime from pre-fetched histories
    current_regime_detail = _label_regime_multi(current_conditions, histories)
    current_regime_label = _format_regime_label(current_regime_detail)
    print(f"[IndicatorExtremes] Current regime: {current_regime_label}")

    # Step 2: For each episode, look up conditions in-memory
    for ep in to_characterize:
        date = ep["date"]
        conditions = {}

        for var in regime_variables:
            name = var["normalized"]
            hist = histories.get(name)
            if not hist:
                continue
            val = _lookup_value_at_date(hist, date)
            if val is not None:
                conditions[name] = {
                    "value": val,
                    "date": date,
                    "source": var["source"],
                }

        # Multi-dimensional regime label
        regime_detail = _label_regime_multi(conditions, histories)
        regime_label = _format_regime_label(regime_detail)

        # Z-score similarity
        similarity_detail = _compute_similarity_zscore(conditions, current_conditions, histories)
        similarity_score = similarity_detail.get("overall", 0)

        ep["conditions"] = conditions
        ep["similarity_score"] = similarity_score
        ep["similarity_detail"] = similarity_detail
        ep["regime_label"] = regime_label
        ep["regime_detail"] = regime_detail

    # Episodes beyond max_episodes get no regime data
    for ep in episodes[max_episodes:]:
        ep.setdefault("conditions", {})
        ep.setdefault("similarity_score", 0)
        ep.setdefault("similarity_detail", {})
        ep.setdefault("regime_label", "unknown")
        ep.setdefault("regime_detail", {})

    # Store current regime info on the list itself for format_episodes_with_regime
    # (Python allows setting attrs on lists, but cleaner to return via episodes[0])
    if to_characterize:
        # Stash current regime in a way the formatter can access
        episodes[0]["_current_regime_detail"] = current_regime_detail
        episodes[0]["_current_regime_label"] = current_regime_label

    print(f"[IndicatorExtremes] Regime characterization complete "
          f"({len(to_characterize)} episodes characterized)")
    return episodes


def format_episodes_with_regime(
    variable_name: str,
    percentile: float,
    direction: str,
    episodes: List[Dict[str, Any]],
    aggregated: Dict[str, Any],
    current_values: Dict[str, Any],
) -> str:
    """Format regime-annotated episodes as a prompt section."""
    # Find most similar episode
    characterized = [e for e in episodes if e.get("similarity_score", 0) > 0]
    most_similar = max(characterized, key=lambda e: e["similarity_score"]) if characterized else None

    lines = [
        "## MECHANICAL EPISODE ANALYSIS",
        "",
        f"**Indicator**: {variable_name} (top {100 - percentile:.0f}% {direction} readings)",
        f"**Episodes found**: {aggregated.get('episode_count', len(episodes))}",
        f"**Summary**: {aggregated.get('summary', '')}",
    ]

    if most_similar:
        sim_detail = most_similar.get("similarity_detail", {})
        sim_parts = []
        for dim in ["macro", "policy", "risk", "curve"]:
            if dim in sim_detail:
                sim_parts.append(f"{dim} {sim_detail[dim]:.2f}")
        sim_str = ", ".join(sim_parts) if sim_parts else f"{most_similar['similarity_score']:.2f}"
        lines.append(
            f"**Most similar to current regime**: {most_similar['date']} "
            f"(similarity: {sim_str} → overall {most_similar['similarity_score']:.2f})"
        )
    lines.append("")

    # Aggregate table
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

    # Per-episode detail with regime context (show all characterized episodes)
    display_episodes = [e for e in episodes if e.get("regime_label") and e.get("regime_label") != "unknown"]
    if display_episodes:
        lines.append(f"**Per-episode detail with macro regime ({len(display_episodes)} episodes):**")
        lines.append("")

        for ep in display_episodes:
            date = ep["date"]
            value = ep["value"]
            pct_rank = ep["percentile_rank"]
            regime_label = ep.get("regime_label", "unknown")
            similarity = ep.get("similarity_score", 0)
            similarity_detail = ep.get("similarity_detail", {})
            source_tag = " [web-search]" if ep.get("source") == "web_search" else ""

            lines.append(
                f"- **{date}** ({variable_name} {value:.3f}, "
                f"{pct_rank:.0f}th pct) [{regime_label}]{source_tag}"
            )

            # Per-dimension similarity line
            sim_parts = []
            for dim in ["macro", "policy", "risk", "curve"]:
                if dim in similarity_detail:
                    sim_parts.append(f"{dim} {similarity_detail[dim]:.2f}")
            if sim_parts:
                lines.append(f"  Similarity: {', '.join(sim_parts)} → overall {similarity:.2f}")
            else:
                lines.append(f"  Similarity to now: {similarity:.2f}")

            # Forward returns
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

    # Regime cluster summary — group by macro quadrant (primary dimension)
    macro_clusters = {}
    for ep in episodes:
        regime_detail = ep.get("regime_detail", {})
        macro_label = regime_detail.get("macro", "unknown") if regime_detail else "unknown"
        # Fall back to full regime_label if no regime_detail
        if macro_label == "unknown":
            macro_label = ep.get("regime_label", "unknown")
        if macro_label == "unknown":
            continue
        if macro_label not in macro_clusters:
            macro_clusters[macro_label] = {"episodes": [], "returns_1mo": []}
        macro_clusters[macro_label]["episodes"].append(ep)
        # Collect primary asset 1mo return
        for asset_name, returns in ep.get("forward_returns", {}).items():
            ret_1mo = returns.get("1mo")
            if ret_1mo is not None:
                macro_clusters[macro_label]["returns_1mo"].append(ret_1mo)
                break  # Only first asset (primary)

    if macro_clusters:
        lines.append("**Regime cluster summary (grouped by macro quadrant):**")
        for label, cluster in sorted(macro_clusters.items(), key=lambda x: -len(x[1]["episodes"])):
            n = len(cluster["episodes"])
            returns = cluster["returns_1mo"]
            if returns:
                med = median(returns)
                pct_pos = round(sum(1 for r in returns if r > 0) / len(returns) * 100)
                lines.append(
                    f"- {n} episode{'s' if n > 1 else ''} in **{label}**: "
                    f"median {med:+.1f}% at 1mo ({pct_pos}% positive)"
                )
            else:
                lines.append(f"- {n} episode{'s' if n > 1 else ''} in **{label}**: no return data")

        # Current regime — use multi-dimensional label stashed during characterization
        current_label = episodes[0].get("_current_regime_label", "") if episodes else ""
        current_detail = episodes[0].get("_current_regime_detail", {}) if episodes else {}
        if not current_label:
            # Fallback to legacy label
            most_recent_conditions = episodes[0].get("conditions", {}) if episodes else {}
            current_label = _label_regime(most_recent_conditions) if most_recent_conditions else _label_regime(current_values)
        lines.append(f"- **Current regime**: {current_label}")

        # Match current macro quadrant to cluster
        current_macro = current_detail.get("macro", "")
        if current_macro and current_macro in macro_clusters:
            cluster = macro_clusters[current_macro]
            returns = cluster["returns_1mo"]
            if returns:
                n = len(cluster["episodes"])
                pct_pos = round(sum(1 for r in returns if r > 0) / len(returns) * 100)
                lines.append(f"  → Current macro quadrant ({current_macro}) aligns with "
                             f"{n}-episode cluster ({pct_pos}% bullish outcomes)")
        lines.append("")

    return "\n".join(lines)
