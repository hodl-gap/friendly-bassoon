"""
Prompts for Claim Parsing

Contains prompts for extracting testable quantitative claims from synthesis text.
"""


CLAIM_EXTRACTION_PROMPT = """You are a financial analyst extracting testable quantitative claims from research synthesis.

A testable claim must:
1. Reference specific variables that can be fetched from data sources (FRED, Yahoo Finance, CoinGecko)
2. State a measurable relationship (correlation, lag, threshold, trend)
3. Include enough detail to validate programmatically

SYNTHESIS TEXT:
{synthesis_text}

Extract ALL testable quantitative claims. For each claim:
- Identify the exact claim text
- Extract both variables involved
- Determine the relationship type
- Extract any specific parameters (lag values, thresholds, etc.)
- Rate testability (0.0-1.0)

OUTPUT FORMAT (JSON only):
{{
  "claims": [
    {{
      "claim_text": "Exact quote from synthesis",
      "variable_a": "first variable (normalized name, lowercase)",
      "variable_b": "second variable (normalized name, lowercase, or null if single-variable claim)",
      "relationship_type": "correlation|lag|threshold|trend|ratio",
      "direction": "positive|negative|neutral",
      "parameters": {{
        "lag_range": {{"min": 0, "max": 0, "unit": "days"}},
        "threshold": {{"value": null, "condition": "greater_than|less_than|equals"}},
        "expected_value": null,
        "time_period": null
      }},
      "testability_score": 0.9,
      "testability_reason": "Why this can/cannot be tested programmatically"
    }}
  ],
  "non_testable_statements": [
    {{
      "statement": "Statement that cannot be tested",
      "reason": "Why it cannot be tested (qualitative, no data available, etc.)"
    }}
  ]
}}

RELATIONSHIP TYPES:
- correlation: Two variables move together (e.g., "BTC correlates with gold")
- lag: One variable follows another with delay (e.g., "BTC follows gold with 63-428 day lag")
- threshold: Specific level triggers effect (e.g., "When TGA falls below $500B")
- trend: Direction of movement (e.g., "DXY is trending down")
- ratio: Proportional relationship (e.g., "VIX/SPY ratio above 0.5")

VARIABLE NORMALIZATION:
- Use lowercase snake_case
- Map common names: "Treasury General Account" → "tga", "Bitcoin" → "btc"
- Be specific: "gold" not "precious metals"

Return ONLY the JSON, nothing else."""


CLAIM_REFINEMENT_PROMPT = """Refine these extracted claims for data fetching.

EXTRACTED CLAIMS:
{claims_json}

AVAILABLE DATA SOURCES:
- FRED: US economic data (TGA, reserves, rates, VIX, gold)
- Yahoo Finance: Stocks, ETFs, indices, forex, crypto
- CoinGecko: Cryptocurrency prices

For each claim:
1. Map variables to the best data source
2. Suggest specific series IDs if known
3. Flag if data is unavailable

OUTPUT FORMAT (JSON only):
{{
  "refined_claims": [
    {{
      "claim_text": "Original claim",
      "variable_a": {{
        "name": "btc",
        "suggested_source": "CoinGecko",
        "suggested_series_id": "bitcoin",
        "data_available": true
      }},
      "variable_b": {{
        "name": "gold",
        "suggested_source": "FRED",
        "suggested_series_id": "GOLDAMGBD228NLBM",
        "data_available": true
      }},
      "relationship_type": "lag",
      "parameters": {{}},
      "testability_score": 0.9
    }}
  ],
  "untestable_claims": [
    {{
      "claim": "Claim text",
      "reason": "Why data is not available"
    }}
  ]
}}

Return ONLY the JSON, nothing else."""
