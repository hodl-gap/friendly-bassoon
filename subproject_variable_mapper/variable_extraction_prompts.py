"""
Prompts for Variable Extraction Module
"""

# Main prompt for extracting variables from synthesis text
VARIABLE_EXTRACTION_PROMPT = """You are a financial data analyst. Your task is to extract all measurable financial variables from the given text.

A "measurable variable" is any financial metric, indicator, or data point that:
- Can be expressed as a number
- Can be fetched from a data source (FRED, Bloomberg, etc.)
- Is used in financial analysis or economic reasoning

INPUT TEXT:
{synthesis_text}

INSTRUCTIONS:
1. Scan the entire text for mentions of financial variables
2. Extract EVERY variable mentioned, even if mentioned multiple times
3. For each variable, capture:
   - The variable name as mentioned in the text
   - Any threshold or value mentioned with it
   - The context where it appears (brief quote)

**CRITICAL - TEMPORAL CONTEXT FOR THRESHOLDS:**
- Thresholds are TIME-BOUND examples, not absolute targets
- A threshold like "$1.26T" or "105 billion" is specific to the data's time period
- Extract the year/period the threshold applies to (look for years like 2025, 2026, Q1, etc.)
- If no specific year mentioned, infer from context or mark as "unknown"
- These thresholds are ILLUSTRATIVE - users will need to update with current data

OUTPUT FORMAT (JSON):
{{
  "variables": [
    {{
      "name": "TGA",
      "role": "trigger",
      "role_reasoning": "mentioned as condition that initiates policy response",
      "threshold": "500",
      "threshold_unit": "billion_usd",
      "threshold_condition": "less_than",
      "threshold_data_year": "2026",
      "threshold_is_example": true,
      "context": "TGA drawdown schedule"
    }},
    {{
      "name": "Fed funds rate",
      "role": "indicator",
      "role_reasoning": "monitored as early warning signal for policy direction",
      "threshold": null,
      "threshold_unit": null,
      "threshold_condition": null,
      "threshold_data_year": null,
      "threshold_is_example": false,
      "context": "Fed rate cuts → short rates down"
    }},
    {{
      "name": "QE annual volume",
      "role": "indicator",
      "role_reasoning": "scale of asset purchase program for liquidity impact",
      "threshold": "1.26",
      "threshold_unit": "trillion_usd",
      "threshold_condition": "equals",
      "threshold_data_year": "2026",
      "threshold_is_example": true,
      "context": "2026 QE expected $1.26T"
    }}
  ]
}}

IMPORTANT:
- Extract ALL variables, not just the main ones
- Include rate variables (Fed funds, SOFR, Treasury yields)
- Include liquidity metrics (TGA, RRP, reserves, QT)
- Include market indicators (VIX, DXY, FCI)
- Include positioning metrics (CTA flows, fund flows)
- Include economic indicators (CPI, unemployment, GDP)
- Do NOT include qualitative concepts (e.g., "risk sentiment", "market stress") unless they have a measurable proxy

THRESHOLD TEMPORAL RULES:
- If threshold has a specific year (e.g., "2026 QE $1.26T"), set threshold_data_year to that year
- If threshold is from a projection/forecast, set threshold_is_example to true
- Absolute values like "$105B", "$7.6T", "83.4%" are ALWAYS examples (threshold_is_example: true)
- The variable itself is timeless; only the threshold value is time-bound
- Example: "Fed balance sheet" is always valid, but "+$105B" is a 2026-specific value

ROLE CLASSIFICATION:
- "indicator": Early warning signal, something to WATCH continuously (e.g., RDE trending up, Fed funds rate, yield curve)
- "trigger": Hard constraint or condition that CAUSES action when breached (e.g., reserve floor, TGA < $500B, unemployment spike)
- "confirmation": After-the-fact validation signal that confirms an outcome has occurred (e.g., ON RRP collapse confirms stress, VIX spike confirms risk-off)
- null: If role is unclear from context

Role hints from text patterns:
- "watch for...", "monitor...", "track..." → likely "indicator"
- "if X falls below...", "when X reaches...", "threshold of..." → likely "trigger"
- "confirms...", "validates...", "signals that..." → likely "confirmation"

Return ONLY the JSON, no additional text."""


# Prompt for extracting variables specifically from logic chains
CHAIN_VARIABLE_EXTRACTION_PROMPT = """Extract variables from this logic chain.

CHAIN: {chain}

For each step in the chain (A → B → C), identify what variables are involved and classify their role.

ROLE CLASSIFICATION based on position in chain:
- Variables at the START of a chain (causal position) → "indicator" (something we monitor)
- Variables in CONDITIONAL position ("if X then...") → "trigger" (causes action when breached)
- Variables at the END of a chain (outcome position) → "confirmation" (validates the outcome)

OUTPUT FORMAT (JSON):
{{
  "chain": "{chain}",
  "variables": [
    {{"name": "variable1", "role": "indicator"}},
    {{"name": "variable2", "role": "trigger"}},
    {{"name": "variable3", "role": "confirmation"}}
  ],
  "steps": [
    {{"from": "variable1", "to": "variable2", "relationship": "causes"}},
    {{"from": "variable2", "to": "variable3", "relationship": "leads_to"}}
  ]
}}

Return ONLY the JSON."""
