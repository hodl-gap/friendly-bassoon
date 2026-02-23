"""
Prompts for Pattern Validator Module
"""

# Prompt for extracting quantitative patterns from research text
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
