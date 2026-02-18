"""
Pattern Validator Module

Extracts patterns/conditions from retrieved research and validates
them against current market data.

Example:
  Research: "TGA increased 200% over 3 months → BTC crashed"
  Current: TGA +11% over 3 months
  Result: "Pattern NOT triggered - increase (11%) below threshold (200%)"
"""

import sys
import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import anthropic

# Add parent for models
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_haiku

from .states import RiskImpactState
from .current_data_fetcher import (
    fetch_fred_with_history,
    fetch_yahoo_with_history,
    resolve_variable,
)

# Tool schema for structured pattern extraction via tool_use
PATTERN_EXTRACTION_TOOL = {
    "name": "output_patterns",
    "description": "Output extracted quantitative patterns from research text that can be validated against current market data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "patterns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "variable": {
                            "type": "string",
                            "description": "Trigger variable normalized: tga, btc, sofr, fed_balance_sheet, dxy, vix, etc."
                        },
                        "condition_type": {
                            "type": "string",
                            "enum": ["percentage_change", "absolute_threshold", "new_high", "new_low", "range_breakout"],
                            "description": "Type of condition to evaluate"
                        },
                        "condition_value": {
                            "type": ["number", "null"],
                            "description": "Threshold value (e.g., 200 for 200%, 900000 for $900B). Null for new_high/new_low."
                        },
                        "condition_direction": {
                            "type": "string",
                            "enum": ["increase", "decrease", "above", "below", "equals"],
                            "description": "Direction of the condition"
                        },
                        "timeframe_days": {
                            "type": ["integer", "null"],
                            "description": "Number of days for the condition (e.g., 90 for 3 months, 30 for 1 month). Null if not time-bound."
                        },
                        "expected_effect": {
                            "type": "string",
                            "description": "Brief description of what happens when triggered"
                        },
                        "original_text": {
                            "type": "string",
                            "description": "Original text snippet this pattern was extracted from"
                        }
                    },
                    "required": ["variable", "condition_type", "condition_direction"]
                }
            }
        },
        "required": ["patterns"]
    }
}


PATTERN_EXTRACTION_PROMPT = """Extract quantitative patterns/conditions from this research text that can be validated against current market data.

Focus on patterns that have:
1. A TRIGGER VARIABLE (e.g., TGA, BTC, SOFR)
2. A CONDITION (e.g., "increases 200%", "hits new ATH", "above $900B", "drops below $50K")
3. A TIMEFRAME (e.g., "over 3 months", "within 2 weeks", "in January")
4. An EXPECTED EFFECT (e.g., "BTC drops", "risk assets rally")

TEXT:
{text}

Return JSON array of patterns. Each pattern should have:
- variable: the trigger variable (normalized: tga, btc, sofr, fed_balance_sheet, dxy, vix, etc.)
- condition_type: one of "percentage_change", "absolute_threshold", "new_high", "new_low", "range_breakout"
- condition_value: the threshold value (e.g., 200 for 200%, 900000 for $900B)
- condition_direction: "increase", "decrease", or "above", "below", "equals"
- timeframe_days: number of days for the condition (e.g., 90 for 3 months, 30 for 1 month)
- expected_effect: brief description of what happens when triggered
- original_text: the original text snippet this was extracted from

Return ONLY valid JSON array. If no patterns found, return [].

Example output:
[
  {{
    "variable": "tga",
    "condition_type": "percentage_change",
    "condition_value": 200,
    "condition_direction": "increase",
    "timeframe_days": 90,
    "expected_effect": "BTC crashes",
    "original_text": "TGA increased 200% over 3 months, BTC crashed"
  }},
  {{
    "variable": "tga",
    "condition_type": "absolute_threshold",
    "condition_value": 940000,
    "condition_direction": "above",
    "timeframe_days": null,
    "expected_effect": "risk assets decline within 2 months",
    "original_text": "TGA above $940B peak leads to risk asset decline"
  }}
]"""


def _extract_patterns_tool_use(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Extract patterns using Anthropic tool_use for structured output.

    Returns list of pattern dicts, or raises on failure.
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        temperature=0.0,
        messages=messages,
        tools=[PATTERN_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "output_patterns"}
    )

    # Log token usage
    try:
        from shared.run_logger import log_llm_call
        log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
    except Exception:
        pass

    for block in response.content:
        if block.type == "tool_use":
            patterns = block.input.get("patterns", [])
            print(f"[Pattern Validator] Extracted {len(patterns)} patterns via tool_use")
            return patterns

    raise ValueError("No tool_use block found in response")


def _extract_patterns_regex_fallback(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Fallback: extract patterns using call_claude_haiku + regex JSON parsing.

    Returns list of pattern dicts, or empty list.
    """
    print("[Pattern Validator] Falling back to regex-based extraction")
    response = call_claude_haiku(
        messages,
        temperature=0.1,
        max_tokens=2000
    )

    json_match = re.search(r'\[[\s\S]*\]', response)
    if json_match:
        patterns = json.loads(json_match.group())
        print(f"[Pattern Validator] Extracted {len(patterns)} patterns via regex fallback")
        return patterns
    else:
        print("[Pattern Validator] No patterns found in regex fallback response")
        return []


def extract_patterns(state: RiskImpactState) -> List[Dict[str, Any]]:
    """
    Extract quantitative patterns from retrieved research.

    Uses Anthropic tool_use for structured output. Falls back to
    regex-based JSON parsing if tool_use fails.
    """
    # Combine relevant text
    text_parts = []

    synthesis = state.get("synthesis", "")
    if synthesis:
        # Focus on the KEY VARIABLES section which has historical context
        text_parts.append(synthesis)

    answer = state.get("retrieval_answer", "")
    if answer:
        # Take a reasonable chunk
        text_parts.append(answer[:4000])

    if not text_parts:
        return []

    combined_text = "\n\n".join(text_parts)

    # Build prompt and messages
    prompt = PATTERN_EXTRACTION_PROMPT.format(text=combined_text)
    messages = [{"role": "user", "content": prompt}]

    # Try tool_use first, fall back to regex parsing
    try:
        return _extract_patterns_tool_use(messages)
    except Exception as e:
        print(f"[Pattern Validator] tool_use extraction failed: {e}")

    try:
        return _extract_patterns_regex_fallback(messages)
    except Exception as e:
        print(f"[Pattern Validator] Regex fallback also failed: {e}")
        return []


def fetch_historical_for_pattern(variable: str, timeframe_days: int) -> Optional[Dict[str, Any]]:
    """
    Fetch historical data for a specific variable and timeframe.

    Returns dict with current value, historical value, and calculated change.
    """
    lookback = max(timeframe_days + 14, 45)  # Extra buffer for data gaps

    # Resolve variable to source and series_id
    var_lower = variable.lower()
    resolution = resolve_variable(var_lower)

    if not resolution:
        return None

    source = resolution["source"]
    series_id = resolution["series_id"]

    result = None
    if source == "FRED":
        result = fetch_fred_with_history(series_id, lookback)
    elif source == "Yahoo":
        result = fetch_yahoo_with_history(series_id, lookback)

    if not result or not result.get("history"):
        return None

    history = result["history"]
    current_value = result["value"]
    current_date = datetime.strptime(result["date"], "%Y-%m-%d")

    # Find value from timeframe_days ago
    target_date = current_date - timedelta(days=timeframe_days)
    historical_value = None
    historical_date = None

    for date_str, value in history:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        # Find closest value within a window
        if abs((date - target_date).days) <= 7:
            historical_value = value
            historical_date = date_str
            break

    if historical_value is None:
        # Fallback: use earliest available
        if history:
            historical_value = history[0][1]
            historical_date = history[0][0]

    if historical_value is None:
        return None

    # Calculate changes
    abs_change = current_value - historical_value
    pct_change = ((current_value - historical_value) / historical_value * 100) if historical_value != 0 else 0

    # Find max/min in period for ATH/ATL detection
    values = [v for _, v in history]
    max_value = max(values) if values else current_value
    min_value = min(values) if values else current_value

    return {
        "current_value": current_value,
        "current_date": result["date"],
        "historical_value": historical_value,
        "historical_date": historical_date,
        "absolute_change": abs_change,
        "percentage_change": pct_change,
        "period_max": max_value,
        "period_min": min_value,
        "is_at_high": current_value >= max_value * 0.98,  # Within 2% of high
        "is_at_low": current_value <= min_value * 1.02,   # Within 2% of low
    }


def normalize_threshold(variable: str, condition_value: float) -> float:
    """
    Normalize threshold values to match FRED data units.

    FRED uses different units for different series:
    - TGA (WTREGEN), Fed BS (WALCL): Millions of dollars
    - Reserves (TOTRESNS), RRP (RRPONTSYD): Billions of dollars

    LLM extracts thresholds in dollars (e.g., 940000000000 = $940B).
    This converts dollar thresholds to the appropriate FRED units.
    """
    if not condition_value:
        return condition_value

    var_lower = variable.lower()

    # FRED series reported in millions
    if var_lower in {"tga", "fed_balance_sheet"}:
        # Convert dollars to millions (e.g., 940B = 940e9 -> 940000 in millions)
        if condition_value > 1e9:
            return condition_value / 1e6
        return condition_value

    # FRED series reported in billions
    if var_lower in {"bank_reserves", "reserves", "rrp"}:
        # Convert dollars to billions (e.g., 3T = 3e12 -> 3000 in billions)
        if condition_value > 1e9:
            return condition_value / 1e9
        return condition_value

    return condition_value


def evaluate_pattern(pattern: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a single pattern against fetched data.

    Returns evaluation result with triggered status and explanation.
    """
    condition_type = pattern.get("condition_type", "")
    variable = pattern.get("variable", "")
    raw_condition_value = pattern.get("condition_value")
    condition_value = normalize_threshold(variable, raw_condition_value)
    condition_direction = pattern.get("condition_direction", "")

    # Guard against None condition values
    if condition_value is None and condition_type not in ["new_high", "new_low"]:
        return {
            "pattern": pattern,
            "triggered": False,
            "current_metric": None,
            "threshold": None,
            "explanation": "No threshold value provided",
            "data": data
        }

    triggered = False
    current_metric = None
    threshold = condition_value
    explanation = ""

    if condition_type == "percentage_change":
        current_metric = data["percentage_change"]

        if condition_direction == "increase":
            triggered = current_metric >= condition_value
            explanation = f"Change: {current_metric:+.1f}% vs threshold: +{condition_value}%"
        elif condition_direction == "decrease":
            triggered = current_metric <= -condition_value
            explanation = f"Change: {current_metric:+.1f}% vs threshold: -{condition_value}%"

    elif condition_type == "absolute_threshold":
        current_metric = data["current_value"]

        if condition_direction in ["above", "increase"]:
            triggered = current_metric >= condition_value
            explanation = f"Current: {current_metric:,.0f} vs threshold: {condition_value:,.0f}"
        elif condition_direction in ["below", "decrease"]:
            triggered = current_metric <= condition_value
            explanation = f"Current: {current_metric:,.0f} vs threshold: {condition_value:,.0f}"

    elif condition_type == "new_high":
        triggered = data["is_at_high"]
        current_metric = data["current_value"]
        threshold = data["period_max"]
        explanation = f"Current: {current_metric:,.0f}, Period high: {threshold:,.0f}"

    elif condition_type == "new_low":
        triggered = data["is_at_low"]
        current_metric = data["current_value"]
        threshold = data["period_min"]
        explanation = f"Current: {current_metric:,.0f}, Period low: {threshold:,.0f}"

    elif condition_type == "range_breakout":
        current_metric = data["current_value"]
        if condition_direction == "above":
            triggered = current_metric > condition_value
        else:
            triggered = current_metric < condition_value
        explanation = f"Current: {current_metric:,.0f} vs level: {condition_value:,.0f}"

    return {
        "pattern": pattern,
        "triggered": triggered,
        "current_metric": current_metric,
        "threshold": threshold,
        "explanation": explanation,
        "data": data
    }


def validate_patterns(state: RiskImpactState) -> RiskImpactState:
    """
    Main function to extract and validate patterns from research.

    Updates state with:
    - validated_patterns: List of patterns with their trigger status
    """
    print("[Pattern Validator] Extracting patterns from research...")

    # Step 1: Extract patterns from research
    patterns = extract_patterns(state)

    if not patterns:
        print("[Pattern Validator] No patterns to validate")
        state["validated_patterns"] = []
        return state

    # Step 2: Validate each pattern
    # Guard: skip non-dict entries and cap at reasonable limit
    patterns = [p for p in patterns if isinstance(p, dict)]
    if len(patterns) > 50:
        print(f"[Pattern Validator] WARNING: {len(patterns)} patterns extracted, capping at 50")
        patterns = patterns[:50]

    validated = []

    for pattern in patterns:
        variable = pattern.get("variable", "")
        timeframe = pattern.get("timeframe_days") or 30  # Default 30 days

        # Fetch historical data
        data = fetch_historical_for_pattern(variable, timeframe)

        if data:
            result = evaluate_pattern(pattern, data)
            validated.append(result)

            status = "✓ TRIGGERED" if result["triggered"] else "✗ Not triggered"
            print(f"[Pattern Validator] {variable}: {status} - {result['explanation']}")
        else:
            print(f"[Pattern Validator] Could not fetch data for {variable}")

    state["validated_patterns"] = validated

    triggered_count = sum(1 for v in validated if v["triggered"])
    print(f"[Pattern Validator] {triggered_count}/{len(validated)} patterns triggered")

    return state


def format_validated_patterns_for_prompt(validated_patterns: List[Dict]) -> str:
    """
    Format validated patterns for inclusion in LLM prompt.
    """
    if not validated_patterns:
        return ""

    lines = ["## PATTERN VALIDATION (Research conditions vs current data)"]

    triggered = [v for v in validated_patterns if v["triggered"]]
    not_triggered = [v for v in validated_patterns if not v["triggered"]]

    if triggered:
        lines.append("\n**TRIGGERED PATTERNS (conditions currently met):**")
        for v in triggered:
            p = v["pattern"]
            lines.append(f"- ✓ {p['variable'].upper()}: {p.get('original_text', 'N/A')}")
            lines.append(f"    → {v['explanation']}")
            lines.append(f"    → Expected effect: {p.get('expected_effect', 'N/A')}")

    if not_triggered:
        lines.append("\n**NOT TRIGGERED (conditions not met):**")
        for v in not_triggered:
            p = v["pattern"]
            lines.append(f"- ✗ {p['variable'].upper()}: {p.get('original_text', 'N/A')}")
            lines.append(f"    → {v['explanation']}")

    return "\n".join(lines)
