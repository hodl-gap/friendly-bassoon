"""Build scenario skeletons mechanically from Phase 3 data.

No LLM call — pure data transformation from episode clusters and
analog aggregation into structured scenario skeletons that Phase 4
(Opus) fills in with human-readable names and causal mechanisms.
"""

from statistics import median
from typing import Dict, Any, List

from .states import RiskImpactState


def build_scenario_skeleton(state: RiskImpactState) -> Dict[str, Any]:
    """Build scenario skeleton from Phase 3 output.

    Three data paths:
    - Path A: indicator_extremes_data exists → use macro_clusters from characterize_episodes
    - Path B: historical_analogs exists → use aggregate stats, cluster by direction
    - Path C: Neither exists (novel event) → empty skeleton with total_episodes=0
    """
    ha = state.get("historical_analogs", {})
    indicator_data = ha.get("indicator_extremes", {})
    enriched_analogs = ha.get("enriched", [])
    aggregated = ha.get("aggregated", {})

    if indicator_data and indicator_data.get("episodes"):
        return _build_from_indicator_extremes(indicator_data)
    elif enriched_analogs and aggregated:
        return _build_from_analog_aggregation(enriched_analogs, aggregated)
    else:
        return _build_empty_skeleton()


def _build_from_indicator_extremes(indicator_data: Dict[str, Any]) -> Dict[str, Any]:
    """Path A: Build from regime-clustered episodes."""
    episodes = indicator_data.get("episodes", [])
    aggregated = indicator_data.get("aggregated", {})
    total_episodes = len(episodes)

    # Group by macro regime quadrant
    macro_clusters: Dict[str, List[Dict]] = {}
    for ep in episodes:
        regime_detail = ep.get("regime_detail", {})
        macro_label = regime_detail.get("macro", "unknown") if regime_detail else "unknown"
        if macro_label == "unknown":
            macro_label = ep.get("regime_label", "unknown")
        macro_clusters.setdefault(macro_label, []).append(ep)

    scenarios = []
    for label, cluster_eps in sorted(macro_clusters.items(), key=lambda x: -len(x[1])):
        # Compute per-asset forward return stats for this cluster
        forward_returns = _compute_cluster_forward_returns(cluster_eps)
        # Average similarity to current regime
        similarities = [ep.get("similarity_score", 0.5) for ep in cluster_eps]
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.5
        # Representative dates
        dates = [ep.get("date", "") for ep in cluster_eps if ep.get("date")]

        scenarios.append({
            "cluster_label": label,
            "analog_count": len(cluster_eps),
            "total_episodes": total_episodes,
            "representative_dates": dates[:4],
            "forward_returns": forward_returns,
            "regime_similarity_to_current": round(avg_similarity, 2),
        })

    # Base rates from aggregated data
    base_rates = _extract_base_rates(aggregated, total_episodes)

    # Distinguishing variables: variables with highest variance across clusters
    distinguishing = _find_distinguishing_variables(macro_clusters)

    return {
        "scenarios": scenarios,
        "base_rates": base_rates,
        "distinguishing_variables": distinguishing,
    }


def _build_from_analog_aggregation(
    enriched_analogs: List[Dict[str, Any]],
    aggregated: Dict[str, Any],
) -> Dict[str, Any]:
    """Path B: Build from N-analog aggregation, cluster by direction."""
    total_episodes = len(enriched_analogs)
    dd = aggregated.get("direction_distribution", {})

    # Cluster analogs by their primary direction
    direction_clusters: Dict[str, List[Dict]] = {}
    for analog in enriched_analogs:
        direction = analog.get("direction", "neutral")
        direction_clusters.setdefault(direction, []).append(analog)

    scenarios = []
    for direction, cluster_analogs in sorted(direction_clusters.items(), key=lambda x: -len(x[1])):
        dates = [a.get("start_date", "") or a.get("period", {}).get("start", "") for a in cluster_analogs]
        scenarios.append({
            "cluster_label": direction,
            "analog_count": len(cluster_analogs),
            "total_episodes": total_episodes,
            "representative_dates": [d for d in dates if d][:4],
            "forward_returns": {},
            "regime_similarity_to_current": 0.5,
        })

    magnitude = aggregated.get("magnitude", {})
    base_rates = {
        "direction_positive_pct": round(dd.get("bullish", 0) / max(total_episodes, 1) * 100),
        "magnitude_median": magnitude.get("median_change", 0),
        "magnitude_range": [magnitude.get("min_change", 0), magnitude.get("max_change", 0)],
        "recovery_median_days": aggregated.get("timing", {}).get("median_recovery_days"),
    }

    return {
        "scenarios": scenarios,
        "base_rates": base_rates,
        "distinguishing_variables": [],
    }


def _build_empty_skeleton() -> Dict[str, Any]:
    """Path C: No historical data — novel event."""
    return {
        "scenarios": [],
        "base_rates": {
            "direction_positive_pct": None,
            "magnitude_median": None,
            "magnitude_range": None,
            "recovery_median_days": None,
        },
        "distinguishing_variables": [],
    }


def _compute_cluster_forward_returns(episodes: List[Dict]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Compute per-asset, per-window stats for a cluster of episodes."""
    # Collect all returns: asset_name -> window_label -> [values]
    all_returns: Dict[str, Dict[str, List[float]]] = {}
    for ep in episodes:
        for asset_name, windows in ep.get("forward_returns", {}).items():
            if asset_name not in all_returns:
                all_returns[asset_name] = {}
            for wl, val in windows.items():
                if val is not None:
                    all_returns[asset_name].setdefault(wl, []).append(val)

    result = {}
    for asset_name, windows in all_returns.items():
        result[asset_name] = {}
        for wl, vals in windows.items():
            if vals:
                result[asset_name][wl] = {
                    "median": round(median(vals), 1),
                    "pct_positive": round(sum(1 for v in vals if v > 0) / len(vals) * 100),
                    "min": round(min(vals), 1),
                    "max": round(max(vals), 1),
                }
    return result


def _extract_base_rates(aggregated: Dict[str, Any], total_episodes: int) -> Dict[str, Any]:
    """Extract base rates from aggregated statistics."""
    per_asset = aggregated.get("per_asset", {})

    # Use first asset's 1mo data as the headline
    all_1mo_medians = []
    all_1mo_pct_pos = []
    all_1mo_mins = []
    all_1mo_maxes = []
    for asset_name, windows in per_asset.items():
        stats = windows.get("1mo", {})
        if stats:
            all_1mo_medians.append(stats.get("median", 0))
            all_1mo_pct_pos.append(stats.get("pct_positive", 50))
            all_1mo_mins.append(stats.get("min", 0))
            all_1mo_maxes.append(stats.get("max", 0))

    return {
        "direction_positive_pct": round(median(all_1mo_pct_pos)) if all_1mo_pct_pos else None,
        "magnitude_median": round(median(all_1mo_medians), 1) if all_1mo_medians else None,
        "magnitude_range": [round(min(all_1mo_mins), 1), round(max(all_1mo_maxes), 1)] if all_1mo_mins else None,
        "recovery_median_days": None,  # Not tracked in indicator_extremes path
    }


def _find_distinguishing_variables(macro_clusters: Dict[str, List[Dict]]) -> List[str]:
    """Find variables whose forward returns vary most across clusters."""
    if len(macro_clusters) < 2:
        return []

    # Collect per-cluster median 1mo return for each asset
    cluster_medians: Dict[str, Dict[str, float]] = {}
    for label, eps in macro_clusters.items():
        for ep in eps:
            for asset_name, windows in ep.get("forward_returns", {}).items():
                ret = windows.get("1mo")
                if ret is not None:
                    cluster_medians.setdefault(asset_name, {}).setdefault(label, []).append(ret)

    # Compute variance of medians across clusters per asset
    asset_variance = {}
    for asset_name, label_vals in cluster_medians.items():
        medians = [median(vals) for vals in label_vals.values() if vals]
        if len(medians) >= 2:
            mean_val = sum(medians) / len(medians)
            var = sum((m - mean_val) ** 2 for m in medians) / len(medians)
            asset_variance[asset_name] = var

    # Also check regime conditions for distinguishing variables
    regime_vars: Dict[str, Dict[str, List[float]]] = {}
    for label, eps in macro_clusters.items():
        for ep in eps:
            conditions = ep.get("conditions", {})
            for var_name, val in conditions.items():
                if isinstance(val, (int, float)):
                    regime_vars.setdefault(var_name, {}).setdefault(label, []).append(val)

    for var_name, label_vals in regime_vars.items():
        medians = [median(vals) for vals in label_vals.values() if vals]
        if len(medians) >= 2:
            mean_val = sum(medians) / len(medians)
            var = sum((m - mean_val) ** 2 for m in medians) / len(medians)
            asset_variance[var_name] = var

    sorted_vars = sorted(asset_variance.items(), key=lambda x: -x[1])
    return [name for name, _ in sorted_vars[:5]]


def format_skeleton_for_prompt(skeleton: Dict[str, Any]) -> str:
    """Format scenario skeleton for inclusion in the Phase 4 prompt."""
    scenarios = skeleton.get("scenarios", [])
    base_rates = skeleton.get("base_rates", {})
    distinguishing = skeleton.get("distinguishing_variables", [])

    if not scenarios:
        return (
            "## SCENARIO SKELETON\n"
            "No historical episodes found. Generate scenarios from causal chain analysis only.\n"
            "Tag each scenario with: NO HISTORICAL GROUNDING.\n"
        )

    lines = ["## SCENARIO SKELETON (from historical data — do NOT change structure)"]

    # Base rates
    total = scenarios[0].get("total_episodes", 0) if scenarios else 0
    dir_pct = base_rates.get("direction_positive_pct")
    mag_med = base_rates.get("magnitude_median")
    mag_range = base_rates.get("magnitude_range")
    lines.append(f"\nBase rates ({total} episodes):")
    if dir_pct is not None:
        lines.append(f"  Direction: {dir_pct}% positive")
    if mag_med is not None:
        lines.append(f"  Magnitude (1mo median): {mag_med:+.1f}%")
    if mag_range:
        lines.append(f"  Range: [{mag_range[0]:+.1f}% to {mag_range[1]:+.1f}%]")

    # Per-scenario
    for i, s in enumerate(scenarios, 1):
        lines.append(f"\nScenario {i} — cluster: {s['cluster_label']} ({s['analog_count']}/{s['total_episodes']} analogs)")
        lines.append(f"  Regime similarity to current: {s['regime_similarity_to_current']:.0%}")
        if s.get("representative_dates"):
            lines.append(f"  Representative dates: {', '.join(s['representative_dates'][:3])}")
        fr = s.get("forward_returns", {})
        for asset_name, windows in fr.items():
            parts = []
            for wl in ["1mo", "3mo", "6mo"]:
                stats = windows.get(wl)
                if stats:
                    parts.append(f"{wl}: {stats['median']:+.1f}% ({stats['pct_positive']}% pos)")
            if parts:
                lines.append(f"  {asset_name}: {', '.join(parts)}")

    if distinguishing:
        lines.append(f"\nDistinguishing variables (what determines which scenario): {', '.join(distinguishing)}")

    return "\n".join(lines)
