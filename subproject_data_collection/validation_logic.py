"""
Validation Logic Module

Statistical validation of claims using fetched data.
Supports correlation, lag, threshold, and trend analysis.
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from models import call_claude_haiku

from states import DataCollectionState
from config import (
    MIN_DATA_POINTS,
    CORRELATION_SIGNIFICANCE_THRESHOLD,
    LAG_SEARCH_RANGE_DAYS,
    CONFIRMED_THRESHOLD,
    PARTIAL_THRESHOLD,
    VALIDATION_INTERPRETATION_MODEL
)
from validation_prompts import VALIDATION_INTERPRETATION_PROMPT
from data_fetching import align_time_series

# Try to import scipy for statistical functions
try:
    from scipy import stats
    from scipy.signal import correlate
    import numpy as np
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("[validation] Warning: scipy not installed. Statistical validation limited.")


def validate_claims(state: DataCollectionState) -> DataCollectionState:
    """
    Validate claims using fetched data.

    LangGraph node function.

    Args:
        state: Current workflow state with parsed_claims and fetched_data

    Returns:
        Updated state with validation_results
    """
    claims = state.get("parsed_claims", [])
    fetched_data = state.get("fetched_data", {})

    if not claims:
        print("[validation] No claims to validate")
        state["validation_results"] = []
        return state

    if not fetched_data:
        print("[validation] No data available for validation")
        state["validation_results"] = []
        state["errors"] = state.get("errors", []) + ["No data available for validation"]
        return state

    print(f"[validation] Validating {len(claims)} claims")

    results = []
    for claim in claims:
        result = validate_single_claim(claim, fetched_data)
        results.append(result)
        print(f"[validation] {claim['claim_text'][:40]}... -> {result['status']}")

    state["validation_results"] = results
    return state


def validate_single_claim(
    claim: Dict[str, Any],
    fetched_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a single claim against fetched data.

    Args:
        claim: Parsed claim dictionary
        fetched_data: Dict of variable -> data

    Returns:
        Validation result dictionary
    """
    relationship_type = claim.get("relationship_type", "correlation")
    var_a = claim.get("variable_a", "")
    var_b = claim.get("variable_b")

    # Get data for variables
    data_a = fetched_data.get(var_a)
    data_b = fetched_data.get(var_b) if var_b else None

    # Check if we have required data
    if not data_a:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": f"No data available for {var_a}",
            "interpretation": f"Cannot validate: missing data for {var_a}"
        }

    if var_b and not data_b:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": f"No data available for {var_b}",
            "interpretation": f"Cannot validate: missing data for {var_b}"
        }

    # Route to appropriate validation function
    if relationship_type == "correlation":
        return validate_correlation(claim, data_a, data_b)
    elif relationship_type == "lag":
        return validate_lag(claim, data_a, data_b)
    elif relationship_type == "threshold":
        return validate_threshold(claim, data_a)
    elif relationship_type == "trend":
        return validate_trend(claim, data_a)
    else:
        # Default to correlation
        return validate_correlation(claim, data_a, data_b)


def validate_correlation(
    claim: Dict[str, Any],
    data_a: Dict[str, Any],
    data_b: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a correlation claim.

    Args:
        claim: Parsed claim
        data_a: First variable's data
        data_b: Second variable's data

    Returns:
        Validation result
    """
    if not SCIPY_AVAILABLE:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": "scipy not available for statistical analysis",
            "interpretation": "Cannot perform correlation analysis without scipy"
        }

    # Align time series
    dates, values_a, values_b = align_time_series(data_a, data_b)

    if len(dates) < MIN_DATA_POINTS:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": f"Insufficient data points: {len(dates)} < {MIN_DATA_POINTS}",
            "interpretation": f"Only {len(dates)} overlapping data points available"
        }

    # Calculate Pearson correlation
    correlation, p_value = stats.pearsonr(values_a, values_b)

    # Determine status
    expected_direction = claim.get("direction", "positive")
    if expected_direction == "positive":
        direction_match = correlation > 0
    elif expected_direction == "negative":
        direction_match = correlation < 0
    else:
        direction_match = True

    if p_value < CORRELATION_SIGNIFICANCE_THRESHOLD and direction_match:
        if abs(correlation) >= CONFIRMED_THRESHOLD:
            status = "confirmed"
        elif abs(correlation) >= PARTIAL_THRESHOLD:
            status = "partially_confirmed"
        else:
            status = "partially_confirmed"
    elif p_value >= CORRELATION_SIGNIFICANCE_THRESHOLD:
        status = "inconclusive"
    else:
        status = "refuted"

    return {
        "claim": claim.get("claim_text", ""),
        "status": status,
        "actual_correlation": round(correlation, 4),
        "p_value": round(p_value, 6),
        "data_points": len(dates),
        "date_range": f"{dates[0]} to {dates[-1]}",
        "interpretation": generate_correlation_interpretation(
            claim, correlation, p_value, len(dates), direction_match
        )
    }


def validate_lag(
    claim: Dict[str, Any],
    data_a: Dict[str, Any],
    data_b: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a lag relationship claim using cross-correlation.

    Args:
        claim: Parsed claim with expected lag range
        data_a: First variable's data (leader)
        data_b: Second variable's data (follower)

    Returns:
        Validation result with optimal lag
    """
    if not SCIPY_AVAILABLE:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": "scipy not available for lag analysis",
            "interpretation": "Cannot perform lag analysis without scipy"
        }

    # Align time series
    dates, values_a, values_b = align_time_series(data_a, data_b)

    if len(dates) < MIN_DATA_POINTS:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": f"Insufficient data points: {len(dates)}",
            "interpretation": f"Only {len(dates)} overlapping data points available"
        }

    # Convert to numpy arrays
    arr_a = np.array(values_a)
    arr_b = np.array(values_b)

    # Normalize
    arr_a = (arr_a - np.mean(arr_a)) / (np.std(arr_a) + 1e-10)
    arr_b = (arr_b - np.mean(arr_b)) / (np.std(arr_b) + 1e-10)

    # Cross-correlation
    max_lag = min(LAG_SEARCH_RANGE_DAYS, len(dates) // 2)
    correlations = []

    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            corr = np.corrcoef(arr_a[:lag], arr_b[-lag:])[0, 1]
        elif lag > 0:
            corr = np.corrcoef(arr_a[lag:], arr_b[:-lag])[0, 1]
        else:
            corr = np.corrcoef(arr_a, arr_b)[0, 1]
        correlations.append((lag, corr))

    # Find optimal lag
    optimal_lag, max_corr = max(correlations, key=lambda x: abs(x[1]))

    # Get expected lag range from claim
    params = claim.get("parameters", {})
    lag_range = params.get("lag_range", {})
    expected_min = lag_range.get("min", 0)
    expected_max = lag_range.get("max", 500)

    # Determine status
    lag_in_range = expected_min <= abs(optimal_lag) <= expected_max
    corr_significant = abs(max_corr) >= PARTIAL_THRESHOLD

    if lag_in_range and corr_significant:
        status = "confirmed" if abs(max_corr) >= CONFIRMED_THRESHOLD else "partially_confirmed"
    elif corr_significant and not lag_in_range:
        status = "partially_confirmed"
    else:
        status = "refuted" if not corr_significant else "inconclusive"

    return {
        "claim": claim.get("claim_text", ""),
        "status": status,
        "optimal_lag_days": optimal_lag,
        "correlation_at_optimal_lag": round(max_corr, 4),
        "expected_lag_range": f"{expected_min}-{expected_max} days",
        "lag_in_expected_range": lag_in_range,
        "data_points": len(dates),
        "date_range": f"{dates[0]} to {dates[-1]}",
        "interpretation": generate_lag_interpretation(
            claim, optimal_lag, max_corr, expected_min, expected_max
        )
    }


def validate_threshold(
    claim: Dict[str, Any],
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a threshold-based claim.

    Args:
        claim: Parsed claim with threshold parameters
        data: Variable's data

    Returns:
        Validation result
    """
    params = claim.get("parameters", {})
    threshold_info = params.get("threshold", {})
    threshold_value = threshold_info.get("value")
    condition = threshold_info.get("condition", "less_than")

    if threshold_value is None:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": "No threshold value specified in claim",
            "interpretation": "Cannot validate without a specific threshold value"
        }

    # Get data points
    data_points = data.get("data", [])
    if not data_points:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": "No data points available",
            "interpretation": "No historical data to analyze"
        }

    # Find threshold breaches
    breaches = []
    for date, value in data_points:
        if condition == "less_than" and value < threshold_value:
            breaches.append((date, value))
        elif condition == "greater_than" and value > threshold_value:
            breaches.append((date, value))
        elif condition == "equals" and value == threshold_value:
            breaches.append((date, value))

    # Generate result
    breach_rate = len(breaches) / len(data_points) if data_points else 0

    return {
        "claim": claim.get("claim_text", ""),
        "status": "confirmed" if breaches else "refuted",
        "threshold_value": threshold_value,
        "threshold_condition": condition,
        "breach_count": len(breaches),
        "breach_rate": round(breach_rate, 4),
        "breach_dates": [b[0] for b in breaches[:10]],  # First 10 breaches
        "data_points": len(data_points),
        "interpretation": f"Threshold {'has' if breaches else 'has not'} been breached {len(breaches)} times ({breach_rate:.1%} of observations)"
    }


def validate_trend(
    claim: Dict[str, Any],
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a trend claim using linear regression.

    Args:
        claim: Parsed claim with expected trend direction
        data: Variable's data

    Returns:
        Validation result
    """
    if not SCIPY_AVAILABLE:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": "scipy not available for trend analysis",
            "interpretation": "Cannot perform trend analysis without scipy"
        }

    data_points = data.get("data", [])
    if len(data_points) < MIN_DATA_POINTS:
        return {
            "claim": claim.get("claim_text", ""),
            "status": "inconclusive",
            "reason": f"Insufficient data points: {len(data_points)}",
            "interpretation": f"Only {len(data_points)} data points available"
        }

    # Extract values
    values = [v for _, v in data_points]
    x = np.arange(len(values))

    # Linear regression
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, values)

    # Calculate percent change
    pct_change = (values[-1] - values[0]) / values[0] * 100 if values[0] != 0 else 0

    # Determine actual direction
    if slope > 0 and p_value < CORRELATION_SIGNIFICANCE_THRESHOLD:
        actual_direction = "up"
    elif slope < 0 and p_value < CORRELATION_SIGNIFICANCE_THRESHOLD:
        actual_direction = "down"
    else:
        actual_direction = "flat"

    # Compare with expected
    expected_direction = claim.get("direction", "positive")
    if expected_direction == "positive":
        expected = "up"
    elif expected_direction == "negative":
        expected = "down"
    else:
        expected = "flat"

    direction_match = actual_direction == expected

    return {
        "claim": claim.get("claim_text", ""),
        "status": "confirmed" if direction_match else "refuted",
        "trend_slope": round(slope, 6),
        "trend_direction": actual_direction,
        "expected_direction": expected,
        "r_squared": round(r_value ** 2, 4),
        "p_value": round(p_value, 6),
        "pct_change": round(pct_change, 2),
        "data_points": len(data_points),
        "interpretation": f"Trend is {actual_direction} ({pct_change:+.1f}%), {'matching' if direction_match else 'not matching'} expected {expected} direction"
    }


def generate_correlation_interpretation(
    claim: Dict[str, Any],
    correlation: float,
    p_value: float,
    data_points: int,
    direction_match: bool
) -> str:
    """Generate human-readable interpretation of correlation result."""
    strength = "strong" if abs(correlation) >= 0.7 else "moderate" if abs(correlation) >= 0.4 else "weak"
    significant = "statistically significant" if p_value < 0.05 else "not statistically significant"

    return (
        f"Found {strength} {'positive' if correlation > 0 else 'negative'} correlation "
        f"(r={correlation:.3f}, p={p_value:.4f}), which is {significant}. "
        f"Based on {data_points} data points. "
        f"Direction {'matches' if direction_match else 'does not match'} expected."
    )


def generate_lag_interpretation(
    claim: Dict[str, Any],
    optimal_lag: int,
    correlation: float,
    expected_min: int,
    expected_max: int
) -> str:
    """Generate human-readable interpretation of lag analysis result."""
    in_range = expected_min <= abs(optimal_lag) <= expected_max

    return (
        f"Optimal lag found at {optimal_lag} days with correlation {correlation:.3f}. "
        f"Expected range was {expected_min}-{expected_max} days. "
        f"Actual lag {'is' if in_range else 'is not'} within expected range."
    )


# Testing entry point
if __name__ == "__main__":
    print("Validation logic module loaded.")
    print(f"scipy available: {SCIPY_AVAILABLE}")
