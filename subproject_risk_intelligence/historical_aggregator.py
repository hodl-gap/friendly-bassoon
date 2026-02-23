"""
Historical Analog Aggregator

Fetches data for N historical analogs in parallel,
aggregates statistics (direction, magnitude, timing).
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List
from statistics import median, mean

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_with_tools

from .historical_event_detector import identify_instruments, get_date_range
from .historical_data_fetcher import fetch_historical_event_data, compare_to_current, fetch_conditions_at_date
from .asset_configs import get_asset_config
from . import config
from .historical_event_prompts import MECHANISM_VALIDATION_PROMPT


def validate_analog_mechanism(analog: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate whether the claimed causal mechanism played out in the market data.

    One Haiku call per analog (~$0.01).

    Args:
        analog: Analog dict with key_mechanism, event_description
        market_data: Instrument data from historical fetch

    Returns:
        Dict with mechanism_match (0.0-1.0) and validation_note
    """
    mechanism = analog.get("key_mechanism", "")
    event = analog.get("event_description", "")

    if not mechanism:
        return {"mechanism_match": 0.5, "validation_note": "No mechanism to validate"}

    # Format market data summary
    data_summary = []
    instruments = market_data.get("instruments", {})
    for name, data in instruments.items():
        metrics = data.get("metrics", {})
        change = metrics.get("peak_to_trough_pct")
        if change is not None:
            data_summary.append(f"{name}: {change:+.1f}%")

    if not data_summary:
        return {"mechanism_match": 0.5, "validation_note": "Insufficient market data for validation"}

    prompt = MECHANISM_VALIDATION_PROMPT.format(
        event=event,
        mechanism=mechanism,
        market_data=", ".join(data_summary)
    )

    validation_tool = {
        "name": "validate_mechanism",
        "description": "Score whether the claimed causal mechanism is confirmed by actual market data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mechanism_match": {
                    "type": "number",
                    "description": "Score 0.0-1.0: how well the market data confirms the claimed mechanism"
                },
                "validation_note": {
                    "type": "string",
                    "description": "Brief note explaining the score"
                }
            },
            "required": ["mechanism_match", "validation_note"]
        }
    }

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[validation_tool],
            tool_choice={"type": "tool", "name": "validate_mechanism"},
            model="haiku",
            max_tokens=300,
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "validate_mechanism":
                result = block.input
                return {
                    "mechanism_match": result.get("mechanism_match", 0.5),
                    "validation_note": result.get("validation_note", "")
                }

        return {"mechanism_match": 0.5, "validation_note": "No tool response"}

    except Exception as e:
        print(f"[Historical Analogs] Mechanism validation error for {event}: {e}")
        return {"mechanism_match": 0.5, "validation_note": f"Validation error: {e}"}


def fetch_multiple_analogs(
    analogs: List[Dict[str, Any]],
    query: str,
    synthesis: str,
    logic_chains: list,
    current_values: dict,
    asset_class: str = "btc",
    condition_variables: list = None
) -> List[Dict[str, Any]]:
    """Fetch data for N analogs in parallel.

    Reuses existing identify_instruments(), get_date_range(),
    fetch_historical_event_data(), compare_to_current().

    Args:
        analogs: List of analog dicts from detect_historical_analogs()
        query: User's original query
        synthesis: Retrieved synthesis text
        logic_chains: Logic chains from retrieval
        current_values: Current market values for comparison
        asset_class: Asset class for instrument identification
        condition_variables: List of variable dicts for macro condition comparison
            [{"normalized": str, "ticker": str, "source": str}]

    Returns:
        List of enriched analog dicts with market data
    """
    def _fetch_single(analog: dict) -> dict:
        event = analog.get("event_description", "Unknown")
        date_query = analog.get("date_search_query", event)

        try:
            # Get date range
            date_range = get_date_range(event, date_query)

            # Identify instruments
            instruments = identify_instruments(
                event_description=event,
                query=query,
                synthesis=synthesis,
                logic_chains=logic_chains,
                asset_class=asset_class
            )

            # Fetch historical data
            historical_data = fetch_historical_event_data(
                instruments=instruments,
                start_date=date_range.get("start_date"),
                end_date=date_range.get("end_date")
            )

            # Compare to current
            comparison = {}
            if current_values and historical_data.get("instruments"):
                comparison = compare_to_current(historical_data, current_values)

            # Fetch macro conditions at analog start date ("Then" side)
            conditions_then = {}
            if condition_variables:
                try:
                    conditions_then = fetch_conditions_at_date(
                        condition_variables,
                        date_range.get("start_date")
                    )
                except Exception as e:
                    print(f"[Historical Analogs] Condition fetch failed for {event}: {e}")

            result_dict = {
                **analog,
                "period": {
                    "start": date_range.get("start_date"),
                    "end": date_range.get("end_date"),
                    "peak_date": date_range.get("peak_date"),
                },
                "instruments": historical_data.get("instruments", {}),
                "correlations": historical_data.get("correlations", {}),
                "comparison_to_current": comparison,
                "conditions_then": conditions_then,
                "fetch_success": True,
            }

            # Mechanism validation (Gap 2)
            if config.ENABLE_MECHANISM_VALIDATION:
                validation = validate_analog_mechanism(analog, historical_data)
                result_dict["mechanism_match"] = validation["mechanism_match"]
                result_dict["validation_note"] = validation["validation_note"]

            return result_dict

        except Exception as e:
            print(f"[Historical Analogs] Failed to fetch {event}: {e}")
            return {
                **analog,
                "fetch_success": False,
                "error": str(e),
            }

    enriched = []
    with ThreadPoolExecutor(max_workers=min(len(analogs), 3)) as executor:
        futures = {
            executor.submit(_fetch_single, analog): analog
            for analog in analogs
        }
        for future in as_completed(futures):
            result = future.result()
            enriched.append(result)

    # Sort by relevance score (preserve original order)
    enriched.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)

    # Filter by mechanism match threshold (Gap 2)
    if config.ENABLE_MECHANISM_VALIDATION:
        before_filter = len(enriched)
        enriched = [
            a for a in enriched
            if not a.get("fetch_success") or a.get("mechanism_match", 1.0) >= config.MECHANISM_MATCH_THRESHOLD
        ]
        filtered_count = before_filter - len(enriched)
        if filtered_count > 0:
            print(f"[Historical Analogs] Filtered {filtered_count} analogs below mechanism_match threshold ({config.MECHANISM_MATCH_THRESHOLD})")

    successful = sum(1 for a in enriched if a.get("fetch_success"))
    print(f"[Historical Analogs] Fetched {successful}/{len(analogs)} analogs successfully")

    return enriched


def aggregate_analogs(
    enriched_analogs: List[Dict[str, Any]],
    target_asset_name: str = "BTC"
) -> Dict[str, Any]:
    """Compute aggregates across N analogs.

    Args:
        enriched_analogs: List of enriched analog dicts with market data
        target_asset_name: Asset name to look for in instrument data

    Returns:
        Aggregated statistics dict
    """
    per_analog = []
    directions = {"bearish": 0, "bullish": 0, "neutral": 0}
    changes = []
    recovery_days_list = []

    target_name_lower = target_asset_name.lower()

    for analog in enriched_analogs:
        if not analog.get("fetch_success"):
            continue

        instruments = analog.get("instruments", {})

        # Find the target asset in instruments
        target_change = None
        target_recovery = None
        for name, data in instruments.items():
            if target_name_lower in name.lower():
                metrics = data.get("metrics", {})
                target_change = metrics.get("peak_to_trough_pct", None)
                target_recovery = metrics.get("recovery_days", None)
                break

        # If target not found, use the first instrument with peak_to_trough data
        if target_change is None:
            for name, data in instruments.items():
                metrics = data.get("metrics", {})
                ptt = metrics.get("peak_to_trough_pct")
                if ptt is not None:
                    target_change = ptt
                    target_recovery = metrics.get("recovery_days")
                    break

        direction = "neutral"
        if target_change is not None:
            if target_change < -5:
                direction = "bearish"
            elif target_change > 5:
                direction = "bullish"
            changes.append(target_change)

        directions[direction] += 1

        if target_recovery is not None:
            recovery_days_list.append(target_recovery)

        per_analog.append({
            "event": analog.get("event_description", ""),
            "year": analog.get("year"),
            "relevance": analog.get("relevance_score", 0),
            "target_change_pct": target_change,
            "recovery_days": target_recovery,
            "direction": direction,
            "key_mechanism": analog.get("key_mechanism", ""),
        })

    # Build aggregates
    magnitude = {}
    if changes:
        magnitude = {
            "median_pct": round(median(changes), 1),
            "min_pct": round(min(changes), 1),
            "max_pct": round(max(changes), 1),
            "mean_pct": round(mean(changes), 1),
        }

    timing = {}
    if recovery_days_list:
        timing = {
            "median_recovery_days": round(median(recovery_days_list)),
            "min_recovery_days": min(recovery_days_list),
            "max_recovery_days": max(recovery_days_list),
        }

    # Build summary string
    total = sum(directions.values())
    dominant = max(directions, key=directions.get)
    dominant_count = directions[dominant]
    summary_parts = []
    if total > 0:
        summary_parts.append(f"{dominant_count}/{total} analogs {dominant}")
    if magnitude:
        summary_parts.append(f"median {magnitude['median_pct']:+.0f}%")
    if timing:
        summary_parts.append(f"recovery {timing['median_recovery_days']} days")
    summary = ", ".join(summary_parts) if summary_parts else "Insufficient data"

    result = {
        "direction_distribution": directions,
        "magnitude": magnitude,
        "timing": timing,
        "per_analog": per_analog,
        "summary": summary,
        "total_analogs": total,
    }

    print(f"[Historical Analogs] Aggregated: {summary}")
    return result


def format_analogs_for_prompt(
    aggregated: Dict[str, Any],
    enriched_analogs: List[Dict[str, Any]] = None,
    current_conditions: Dict[str, Any] = None
) -> str:
    """Format as '## HISTORICAL PRECEDENT ANALYSIS (Multi-Analog)' section for prompt.

    Args:
        aggregated: Output from aggregate_analogs()
        enriched_analogs: List of enriched analog dicts (for conditions_then)
        current_conditions: Current macro values {var_name: {"value": ..., "source": ...}}
            Used for the "NOW" side of the Then vs Now comparison
    """
    if not aggregated or not aggregated.get("per_analog"):
        return ""

    lines = ["## HISTORICAL PRECEDENT ANALYSIS (Multi-Analog)"]
    lines.append(f"**Summary**: {aggregated.get('summary', 'N/A')}\n")

    # Direction distribution
    dist = aggregated.get("direction_distribution", {})
    lines.append(f"Direction distribution: bearish={dist.get('bearish', 0)}, "
                 f"bullish={dist.get('bullish', 0)}, neutral={dist.get('neutral', 0)}")

    # Magnitude
    mag = aggregated.get("magnitude", {})
    if mag:
        lines.append(f"Magnitude: median {mag.get('median_pct', 0):+.1f}%, "
                     f"range [{mag.get('min_pct', 0):+.1f}% to {mag.get('max_pct', 0):+.1f}%]")

    # Timing
    timing = aggregated.get("timing", {})
    if timing:
        lines.append(f"Recovery timing: median {timing.get('median_recovery_days', '?')} days "
                     f"(range {timing.get('min_recovery_days', '?')}-{timing.get('max_recovery_days', '?')} days)")

    lines.append("")
    lines.append("**Per-analog breakdown:**")

    # Build a lookup from event description to enriched analog for conditions_then
    conditions_lookup = {}
    if enriched_analogs:
        for ea in enriched_analogs:
            event_key = ea.get("event_description", "")
            if ea.get("conditions_then"):
                conditions_lookup[event_key] = ea["conditions_then"]

    for a in aggregated.get("per_analog", []):
        event = a.get("event", "?")
        year = a.get("year", "?")
        change = a.get("target_change_pct")
        recovery = a.get("recovery_days")
        relevance = a.get("relevance", 0)
        mechanism = a.get("key_mechanism", "")

        change_str = f"{change:+.1f}%" if change is not None else "N/A"
        recovery_str = f"{recovery} days" if recovery is not None else "N/A"

        lines.append(f"- {event} ({year}): {change_str}, recovery {recovery_str} "
                     f"[relevance: {relevance:.1f}]")
        if mechanism:
            lines.append(f"  Mechanism: {mechanism}")

        # Add "Macro Backdrop (Then vs Now)" if conditions available
        conditions_then = conditions_lookup.get(event, {})
        if conditions_then and current_conditions:
            backdrop_lines = []
            for var_name, then_data in sorted(conditions_then.items()):
                then_val = then_data.get("value")
                if then_val is None:
                    continue
                now_data = current_conditions.get(var_name, {})
                now_val = now_data.get("value")
                if now_val is not None:
                    backdrop_lines.append(
                        f"    - {var_name.upper()}: THEN {then_val:.2f} vs NOW {now_val:.2f}"
                    )
                else:
                    backdrop_lines.append(
                        f"    - {var_name.upper()}: THEN {then_val:.2f} (no current data)"
                    )
            if backdrop_lines:
                lines.append("  **Macro Backdrop (Then vs Now)**:")
                lines.extend(backdrop_lines)

    return "\n".join(lines)
