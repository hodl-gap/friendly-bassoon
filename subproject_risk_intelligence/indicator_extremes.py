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
    {"normalized": "vix", "ticker": "^VIX", "source": "Yahoo"},
    {"normalized": "sp500", "ticker": "^GSPC", "source": "Yahoo"},
    {"normalized": "us10y", "ticker": "DGS10", "source": "FRED"},
    {"normalized": "us02y", "ticker": "DGS2", "source": "FRED"},
    {"normalized": "fed_funds", "ticker": "DFF", "source": "FRED"},
    {"normalized": "dxy", "ticker": "DX-Y.NYB", "source": "Yahoo"},
    {"normalized": "gold", "ticker": "GC=F", "source": "Yahoo"},
]


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


def _compute_similarity(conditions_then: dict, current_values: dict) -> float:
    """Compare macro conditions at episode date vs now. Returns 0-1."""
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
    """Mechanical regime label from macro conditions."""
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
    For each mechanical episode, fetch macro conditions at that date
    and compute similarity to current conditions.

    Returns episodes enriched with:
      - conditions: {variable: {value, date}} at episode date
      - similarity_score: float (0-1) vs current conditions
      - regime_label: str (e.g., "high-vol, tight-policy, inverted-curve")
    """
    from .historical_data_fetcher import fetch_conditions_at_date

    # Cap episodes (sorted most-recent-first already)
    to_characterize = episodes[:max_episodes]

    print(f"[IndicatorExtremes] Characterizing {len(to_characterize)} episodes "
          f"with {len(regime_variables)} regime variables...")

    def _fetch_one(episode: dict) -> dict:
        date = episode["date"]
        try:
            conditions = fetch_conditions_at_date(regime_variables, date)
        except Exception as e:
            print(f"[IndicatorExtremes] Error fetching conditions at {date}: {e}")
            conditions = {}
        return {
            "date": date,
            "conditions": conditions,
            "similarity_score": _compute_similarity(conditions, current_values),
            "regime_label": _label_regime(conditions),
        }

    # Parallel fetch (independent API calls per episode)
    results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_one, ep): ep["date"]
            for ep in to_characterize
        }
        for future in as_completed(futures):
            result = future.result()
            results[result["date"]] = result

    # Enrich episodes
    for ep in to_characterize:
        enrichment = results.get(ep["date"], {})
        ep["conditions"] = enrichment.get("conditions", {})
        ep["similarity_score"] = enrichment.get("similarity_score", 0)
        ep["regime_label"] = enrichment.get("regime_label", "unknown")

    # Episodes beyond max_episodes get no regime data
    for ep in episodes[max_episodes:]:
        ep.setdefault("conditions", {})
        ep.setdefault("similarity_score", 0)
        ep.setdefault("regime_label", "unknown")

    print(f"[IndicatorExtremes] Regime characterization complete")
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
        lines.append(
            f"**Most similar to current regime**: {most_similar['date']} "
            f"(similarity: {most_similar['similarity_score']:.2f})"
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
            conditions = ep.get("conditions", {})
            source_tag = " [web-search]" if ep.get("source") == "web_search" else ""

            lines.append(
                f"- **{date}** ({variable_name} {value:.3f}, "
                f"{pct_rank:.0f}th pct) [{regime_label}]{source_tag}"
            )

            # Regime conditions summary line
            cond_parts = []
            for var_name in ["vix", "fed_funds", "us10y", "dxy", "sp500"]:
                entry = conditions.get(var_name, {})
                val = entry.get("value") if isinstance(entry, dict) else None
                if val is not None:
                    label = var_name.upper().replace("_", " ")
                    cond_parts.append(f"{label} {val:.1f}")
            if cond_parts:
                lines.append(f"  Regime: {', '.join(cond_parts)}")

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

    # Regime cluster summary
    regime_clusters = {}
    for ep in episodes:
        label = ep.get("regime_label", "unknown")
        if label == "unknown":
            continue
        if label not in regime_clusters:
            regime_clusters[label] = {"episodes": [], "returns_1mo": []}
        regime_clusters[label]["episodes"].append(ep)
        # Collect primary asset 1mo return
        for asset_name, returns in ep.get("forward_returns", {}).items():
            ret_1mo = returns.get("1mo")
            if ret_1mo is not None:
                regime_clusters[label]["returns_1mo"].append(ret_1mo)
                break  # Only first asset (primary)

    if regime_clusters:
        lines.append("**Regime cluster summary:**")
        for label, cluster in sorted(regime_clusters.items(), key=lambda x: -len(x[1]["episodes"])):
            n = len(cluster["episodes"])
            returns = cluster["returns_1mo"]
            if returns:
                med = median(returns)
                pct_pos = round(sum(1 for r in returns if r > 0) / len(returns) * 100)
                lines.append(
                    f"- {n} episode{'s' if n > 1 else ''} in {label}: "
                    f"median {med:+.1f}% at 1mo ({pct_pos}% positive)"
                )
            else:
                lines.append(f"- {n} episode{'s' if n > 1 else ''} in {label}: no return data")

        # Current regime label — use most recent episode's conditions as
        # best proxy since current_values from Phase 2 may not include all
        # the variables _label_regime needs (e.g., fed_funds is often missing)
        most_recent_conditions = episodes[0].get("conditions", {}) if episodes else {}
        current_label = _label_regime(most_recent_conditions) if most_recent_conditions else _label_regime(current_values)
        lines.append(f"- **Current regime**: {current_label}")

        # Match to cluster
        if current_label in regime_clusters:
            cluster = regime_clusters[current_label]
            returns = cluster["returns_1mo"]
            if returns:
                n = len(cluster["episodes"])
                pct_pos = round(sum(1 for r in returns if r > 0) / len(returns) * 100)
                lines.append(f"  → Aligns with {n}-episode cluster ({pct_pos}% bullish outcomes)")
        lines.append("")

    return "\n".join(lines)
