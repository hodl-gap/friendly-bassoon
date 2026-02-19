"""
Prediction Tracker Module (Gap 5)

Tracks predictions made by the system and evaluates them against actual outcomes.
Provides confidence calibration data for chain-level hit rates.
"""

import json
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from . import config
from .asset_configs import get_asset_config


def extract_predictions(state: Dict[str, Any], asset_class: str) -> List[Dict[str, Any]]:
    """
    Parse InsightTrack output into structured predictions.

    Args:
        state: RiskImpactState dict containing insight_output
        asset_class: Asset class being analyzed

    Returns:
        List of prediction dicts
    """
    insight_output = state.get("insight_output", {})
    tracks = insight_output.get("tracks", [])
    query = state.get("query", "")
    created_date = datetime.now().strftime("%Y-%m-%d")

    # Collect all available chains for linkage
    all_chains = list(state.get("logic_chains", []))
    all_chains.extend(state.get("historical_chains", []))

    predictions = []

    for track in tracks:
        title = track.get("title", "")
        implications = track.get("asset_implications", [])
        if not implications:
            continue

        # Use first implication for primary prediction
        first_impl = implications[0]
        direction = first_impl.get("direction", "")
        magnitude_range_str = first_impl.get("magnitude_range", "")
        confidence = track.get("confidence", 0)
        causal_mechanism = track.get("causal_mechanism", "")
        monitoring_variables = track.get("monitoring_variables", [])
        time_horizon_str = track.get("time_horizon", "")

        # Parse magnitude range (e.g., "-20% to -30%", "5% to 10%")
        magnitude_min, magnitude_max = _parse_magnitude_range(magnitude_range_str)

        # Parse time horizon to days (e.g., "1-3 months" -> 60 days)
        time_horizon_days = _parse_time_horizon(time_horizon_str)

        # Generate prediction ID
        id_string = f"{query}{asset_class}{title}{created_date}"
        prediction_id = hashlib.md5(id_string.encode()).hexdigest()

        # Calculate check date
        check_date = (datetime.now() + timedelta(days=time_horizon_days)).strftime("%Y-%m-%d")

        # Link prediction to source chains via variable overlap
        related_chain_ids = _link_prediction_to_chains(causal_mechanism, all_chains)

        prediction = {
            "prediction_id": prediction_id,
            "created_at": created_date,
            "query": query,
            "asset_class": asset_class,
            "track_title": title,
            "direction": direction,
            "magnitude_min": magnitude_min,
            "magnitude_max": magnitude_max,
            "time_horizon_days": time_horizon_days,
            "check_date": check_date,
            "confidence": confidence,
            "causal_mechanism": causal_mechanism,
            "related_chain_ids": related_chain_ids,
            "monitoring_variables": monitoring_variables,
            "status": "pending",
            "outcome": None,
        }

        predictions.append(prediction)

    return predictions


def log_predictions(predictions: List[Dict[str, Any]]) -> None:
    """
    Append predictions to the prediction ledger.

    Args:
        predictions: List of prediction dicts to log
    """
    ledger_path = config.PREDICTION_LEDGER_PATH

    # Load or create ledger
    if ledger_path.exists():
        with open(ledger_path, "r") as f:
            ledger = json.load(f)
    else:
        # Ensure directory exists
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_checked": None,
                "total_predictions": 0,
            },
            "predictions": [],
        }

    # Append new predictions
    ledger["predictions"].extend(predictions)
    ledger["metadata"]["total_predictions"] = len(ledger["predictions"])

    # Save
    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False, default=str)


def check_outcomes(asset_class: str) -> List[Dict[str, Any]]:
    """
    Evaluate pending predictions where check_date <= today.

    Fetches actual asset performance via Yahoo Finance and compares
    against predicted direction and magnitude.

    Args:
        asset_class: Asset class to check outcomes for

    Returns:
        List of evaluated prediction dicts
    """
    ledger_path = config.PREDICTION_LEDGER_PATH
    if not ledger_path.exists():
        return []

    with open(ledger_path, "r") as f:
        ledger = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    evaluated = []

    for prediction in ledger.get("predictions", []):
        if prediction.get("status") != "pending":
            continue
        if prediction.get("check_date", "9999-99-99") > today:
            continue

        # Fetch actual performance
        try:
            actual_change_pct = _fetch_actual_performance(
                asset_class=prediction.get("asset_class", asset_class),
                start_date=prediction.get("created_at"),
                end_date=prediction.get("check_date"),
            )
        except Exception as e:
            print(f"[Prediction Tracker] Failed to fetch data for {prediction.get('prediction_id')}: {e}")
            continue

        if actual_change_pct is None:
            continue

        # Compare direction
        predicted_direction = prediction.get("direction", "").lower()
        direction_correct = _check_direction(predicted_direction, actual_change_pct)

        # Compare magnitude
        magnitude_min = prediction.get("magnitude_min")
        magnitude_max = prediction.get("magnitude_max")
        magnitude_in_range = _check_magnitude(actual_change_pct, magnitude_min, magnitude_max)

        # Score the prediction
        score = _score_prediction(direction_correct, magnitude_in_range, actual_change_pct)

        # Update prediction
        prediction["status"] = "evaluated"
        prediction["outcome"] = {
            "actual_change_pct": round(actual_change_pct, 2),
            "direction_correct": direction_correct,
            "magnitude_in_range": magnitude_in_range,
            "evaluation_date": today,
            "score": score,
        }

        evaluated.append(prediction)

    # Save updated ledger
    ledger["metadata"]["last_checked"] = today

    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False, default=str)

    return evaluated


def get_chain_hit_rates(chain_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Compute hit rate per chain from the prediction ledger.

    Args:
        chain_ids: List of chain IDs to compute hit rates for

    Returns:
        Dict mapping chain_id -> {hit_rate, total, confirmed, partial, refuted}
    """
    ledger_path = config.PREDICTION_LEDGER_PATH
    if not ledger_path.exists():
        return {}

    with open(ledger_path, "r") as f:
        ledger = json.load(f)

    # Group predictions by chain_id
    chain_predictions: Dict[str, List[Dict]] = {}
    for prediction in ledger.get("predictions", []):
        if prediction.get("status") != "evaluated":
            continue
        for chain_id in prediction.get("related_chain_ids", []):
            if chain_id in chain_ids:
                if chain_id not in chain_predictions:
                    chain_predictions[chain_id] = []
                chain_predictions[chain_id].append(prediction)

    # Compute hit rates
    hit_rates = {}
    for chain_id, preds in chain_predictions.items():
        total = len(preds)
        confirmed = sum(1 for p in preds if p.get("outcome", {}).get("score") == "confirmed")
        partial = sum(1 for p in preds if p.get("outcome", {}).get("score") == "partial")
        refuted = sum(1 for p in preds if p.get("outcome", {}).get("score") == "refuted")

        hit_rate = confirmed / total if total > 0 else 0.0

        hit_rates[chain_id] = {
            "hit_rate": hit_rate,
            "total": total,
            "confirmed": confirmed,
            "partial": partial,
            "refuted": refuted,
        }

    return hit_rates


def format_hit_rates_for_prompt(hit_rates: Dict[str, Dict[str, Any]]) -> str:
    """
    Format hit rates as a text section for inclusion in prompts.

    Args:
        hit_rates: Dict from get_chain_hit_rates()

    Returns:
        Formatted string
    """
    if not hit_rates:
        return ""

    lines = ["## CHAIN PREDICTION SCORECARD"]
    for chain_id, stats in hit_rates.items():
        confirmed = stats.get("confirmed", 0)
        total = stats.get("total", 0)
        hit_rate = stats.get("hit_rate", 0)
        lines.append(f"- {chain_id}: {confirmed}/{total} confirmed ({hit_rate:.0%} hit rate)")

    return "\n".join(lines)


# ============================================================================
# Internal helpers
# ============================================================================


def _link_prediction_to_chains(causal_mechanism: str, chains: List[Dict]) -> List[str]:
    """
    Link a prediction to source chains by matching variables in the causal mechanism
    against variables in each chain's steps.

    Args:
        causal_mechanism: Arrow notation string (e.g., "boj_hike -> carry_unwind -> btc_selloff")
        chains: List of chain dicts with steps or chain_text

    Returns:
        List of chain IDs (relationship_id or chain_id) that overlap
    """
    if not causal_mechanism or not chains:
        return []

    # Extract variable tokens from the mechanism string
    # Split on arrows, underscores become part of the token
    mechanism_tokens = set()
    for part in re.split(r'\s*->\s*', causal_mechanism):
        token = part.strip().lower().replace(" ", "_")
        if token:
            mechanism_tokens.add(token)

    if not mechanism_tokens:
        return []

    linked_ids = []
    for chain in chains:
        chain_id = chain.get("relationship_id") or chain.get("chain_id") or chain.get("id", "")
        if not chain_id:
            continue

        # Extract variables from chain steps
        chain_vars = set()
        for step in chain.get("steps", []):
            cause_norm = step.get("cause_normalized", "")
            effect_norm = step.get("effect_normalized", "")
            if cause_norm:
                chain_vars.add(cause_norm.lower())
            if effect_norm:
                chain_vars.add(effect_norm.lower())

        # Also check chain_text for arrow-notation chains
        chain_text = chain.get("chain_text", "")
        if chain_text and not chain_vars:
            for part in re.split(r'\s*->\s*', chain_text):
                token = part.strip().lower().replace(" ", "_")
                if token:
                    chain_vars.add(token)

        # Check overlap — at least 2 tokens must match
        overlap = mechanism_tokens & chain_vars
        if len(overlap) >= 2:
            linked_ids.append(chain_id)

    return linked_ids


def _parse_magnitude_range(magnitude_str: str) -> tuple:
    """
    Parse magnitude range string into (min, max) floats.

    Examples:
        "-20% to -30%" -> (-30.0, -20.0)
        "5% to 10%" -> (5.0, 10.0)
        "+3% to +8%" -> (3.0, 8.0)

    Returns:
        (magnitude_min, magnitude_max) or (None, None) if parsing fails
    """
    if not magnitude_str:
        return None, None

    # Match patterns like "-20% to -30%", "5% to 10%", "+3% to +8%"
    pattern = r'([+-]?\d+(?:\.\d+)?)\s*%\s*to\s*([+-]?\d+(?:\.\d+)?)\s*%'
    match = re.search(pattern, magnitude_str)

    if match:
        val1 = float(match.group(1))
        val2 = float(match.group(2))
        return min(val1, val2), max(val1, val2)

    return None, None


def _parse_time_horizon(time_horizon_str: str) -> int:
    """
    Parse time horizon string to number of days.

    Examples:
        "1-3 months" -> 60
        "2-4 weeks" -> 21
        "1 week" -> 7
        "6 months" -> 180

    Returns:
        Number of days (default: 30)
    """
    if not time_horizon_str:
        return 30

    text = time_horizon_str.lower()

    # Match range patterns: "1-3 months", "2-4 weeks"
    range_pattern = r'(\d+)\s*[-–to]+\s*(\d+)\s*(day|week|month|year)'
    range_match = re.search(range_pattern, text)

    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        unit = range_match.group(3)
        mid = (low + high) / 2.0
        return int(mid * _unit_to_days(unit))

    # Match single patterns: "3 months", "1 week"
    single_pattern = r'(\d+)\s*(day|week|month|year)'
    single_match = re.search(single_pattern, text)

    if single_match:
        val = int(single_match.group(1))
        unit = single_match.group(2)
        return int(val * _unit_to_days(unit))

    return 30  # Default fallback


def _unit_to_days(unit: str) -> float:
    """Convert time unit to days."""
    unit = unit.lower().rstrip("s")
    if unit == "day":
        return 1
    elif unit == "week":
        return 7
    elif unit == "month":
        return 30
    elif unit == "year":
        return 365
    return 30


def _fetch_actual_performance(asset_class: str, start_date: str, end_date: str) -> Optional[float]:
    """
    Fetch actual asset performance between two dates via Yahoo Finance.

    Args:
        asset_class: Asset class to look up ticker for
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        Percentage change, or None if data unavailable
    """
    import yfinance as yf

    try:
        asset_cfg = get_asset_config(asset_class)
    except ValueError:
        # Unknown asset class, use SPY as fallback
        ticker_symbol = "SPY"
    else:
        ticker_symbol = asset_cfg.get("ticker", "SPY")

    ticker = yf.Ticker(ticker_symbol)

    # Fetch with small buffer for weekends/holidays (find closest trading day at/after dates)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=5)

    hist = ticker.history(start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"))

    if hist.empty or len(hist) < 2:
        return None

    # Get price at/after start_date (first trading day on or after prediction date)
    start_price = hist.iloc[0]["Close"]
    # Get price closest to end_date (last row before end buffer)
    target_end = datetime.strptime(end_date, "%Y-%m-%d")
    end_candidates = hist[hist.index <= target_end.strftime("%Y-%m-%d")]
    end_price = end_candidates.iloc[-1]["Close"] if not end_candidates.empty else hist.iloc[-1]["Close"]

    if start_price == 0:
        return None

    return ((end_price - start_price) / start_price) * 100


def _check_direction(predicted_direction: str, actual_change_pct: float) -> bool:
    """Check if predicted direction matches actual change."""
    predicted = predicted_direction.lower()

    if "bullish" in predicted or "up" in predicted or "positive" in predicted:
        return actual_change_pct > 0
    elif "bearish" in predicted or "down" in predicted or "negative" in predicted:
        return actual_change_pct < 0
    else:
        # Neutral or unclear prediction
        return abs(actual_change_pct) < 2.0


def _check_magnitude(actual_change_pct: float, magnitude_min: Optional[float], magnitude_max: Optional[float]) -> bool:
    """Check if actual change falls within predicted magnitude range."""
    if magnitude_min is None or magnitude_max is None:
        return False

    return magnitude_min <= actual_change_pct <= magnitude_max


def _score_prediction(direction_correct: bool, magnitude_in_range: bool, actual_change_pct: float) -> str:
    """
    Score a prediction based on direction and magnitude accuracy.

    Returns:
        "confirmed" - direction correct AND magnitude within range
        "partial" - direction correct, magnitude off
        "refuted" - direction wrong
        "expired" - actual change < 2% either way (no meaningful move)
    """
    if abs(actual_change_pct) < 2.0:
        return "expired"

    if not direction_correct:
        return "refuted"

    if magnitude_in_range:
        return "confirmed"

    return "partial"
