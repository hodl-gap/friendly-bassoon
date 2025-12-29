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

OUTPUT FORMAT (JSON):
{{
  "variables": [
    {{
      "name": "TGA",
      "threshold": "500",
      "threshold_unit": "billion_usd",
      "threshold_condition": "less_than",
      "context": "TGA drawdown schedule"
    }},
    {{
      "name": "Fed funds rate",
      "threshold": null,
      "threshold_unit": null,
      "threshold_condition": null,
      "context": "Fed rate cuts → short rates down"
    }},
    {{
      "name": "VIX",
      "threshold": null,
      "threshold_unit": null,
      "threshold_condition": null,
      "context": "elevated vol expected"
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

Return ONLY the JSON, no additional text."""


# Prompt for extracting variables specifically from logic chains
CHAIN_VARIABLE_EXTRACTION_PROMPT = """Extract variables from this logic chain.

CHAIN: {chain}

For each step in the chain (A → B → C), identify what variables are involved.

OUTPUT FORMAT (JSON):
{{
  "chain": "{chain}",
  "variables": ["variable1", "variable2", "variable3"],
  "steps": [
    {{"from": "variable1", "to": "variable2", "relationship": "causes"}},
    {{"from": "variable2", "to": "variable3", "relationship": "leads_to"}}
  ]
}}

Return ONLY the JSON."""
