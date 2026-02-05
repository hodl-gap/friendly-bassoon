"""
Prompts for Validation Result Interpretation

Contains prompts for interpreting statistical validation results.
"""


VALIDATION_INTERPRETATION_PROMPT = """You are a quantitative analyst interpreting statistical validation results.

ORIGINAL CLAIM:
{claim_text}

VALIDATION RESULTS:
- Relationship type tested: {relationship_type}
- Actual correlation: {correlation}
- P-value: {p_value}
- Optimal lag (days): {optimal_lag}
- Expected lag range: {expected_lag_min} to {expected_lag_max} days
- Data points analyzed: {data_points}
- Date range: {date_range}

Provide a concise interpretation that:
1. States whether the claim is CONFIRMED, PARTIALLY_CONFIRMED, REFUTED, or INCONCLUSIVE
2. Explains the key findings in plain language
3. Notes any caveats or limitations
4. Suggests follow-up analysis if needed

OUTPUT FORMAT (JSON only):
{{
  "status": "confirmed|partially_confirmed|refuted|inconclusive",
  "interpretation": "2-3 sentence summary of findings",
  "key_findings": [
    "Finding 1",
    "Finding 2"
  ],
  "caveats": [
    "Caveat 1"
  ],
  "follow_up_suggestions": [
    "Suggested follow-up"
  ],
  "confidence_in_result": 0.85
}}

STATUS GUIDELINES:
- CONFIRMED: Statistical evidence strongly supports the claim (p < 0.05, effect in expected direction)
- PARTIALLY_CONFIRMED: Some evidence supports claim, but with caveats (weaker than claimed, different parameters)
- REFUTED: Statistical evidence contradicts the claim
- INCONCLUSIVE: Insufficient data or ambiguous results

Return ONLY the JSON, nothing else."""


THRESHOLD_INTERPRETATION_PROMPT = """Analyze whether a threshold-based claim is validated by historical data.

CLAIM: {claim_text}

THRESHOLD DETAILS:
- Variable: {variable}
- Threshold value: {threshold_value}
- Condition: {threshold_condition} (e.g., "falls below", "exceeds")
- Expected effect: {expected_effect}

HISTORICAL ANALYSIS:
- Times threshold was breached: {breach_count}
- Breach dates: {breach_dates}
- Effect observed after breaches: {observed_effects}
- Average time to effect: {avg_time_to_effect} days

OUTPUT FORMAT (JSON only):
{{
  "status": "confirmed|partially_confirmed|refuted|inconclusive",
  "interpretation": "Summary of threshold analysis",
  "breach_analysis": {{
    "total_breaches": 0,
    "effect_observed_rate": 0.0,
    "average_effect_lag_days": 0
  }},
  "caveats": [],
  "confidence_in_result": 0.0
}}

Return ONLY the JSON, nothing else."""


TREND_INTERPRETATION_PROMPT = """Analyze whether a trend claim is validated by data.

CLAIM: {claim_text}

TREND ANALYSIS:
- Variable: {variable}
- Claimed direction: {claimed_direction}
- Time period: {time_period}
- Actual trend slope: {trend_slope}
- Trend significance (p-value): {trend_p_value}
- R-squared: {r_squared}
- Percent change over period: {pct_change}

OUTPUT FORMAT (JSON only):
{{
  "status": "confirmed|partially_confirmed|refuted|inconclusive",
  "interpretation": "Summary of trend analysis",
  "trend_details": {{
    "direction": "up|down|flat",
    "strength": "strong|moderate|weak",
    "pct_change": 0.0
  }},
  "caveats": [],
  "confidence_in_result": 0.0
}}

Return ONLY the JSON, nothing else."""
