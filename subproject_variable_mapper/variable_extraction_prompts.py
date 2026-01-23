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


# =============================================================================
# COMBINED EXTRACTION PROMPT (Optimization: merge Steps 1 & 3)
# =============================================================================
# This prompt extracts BOTH:
# 1. Explicit variables mentioned with thresholds/values
# 2. Implicit variables found in logic chains (A → B → C)
# Eliminates the need for separate Step 3 (missing_variable_detection)
# =============================================================================

COMBINED_EXTRACTION_PROMPT = """You are a financial data analyst. Extract ALL measurable financial variables from the given text.

You must identify TWO types of variables:

**TYPE 1: EXPLICIT VARIABLES** - Directly mentioned with values/thresholds
- Variables with specific numbers, thresholds, or conditions
- Example: "TGA drawdown to $500B", "Fed funds rate at 5.25%", "VIX above 20"

**TYPE 2: IMPLICIT VARIABLES** - Found within logic chains (A → B → C)
- Variables that appear in causal relationships but may not have explicit values
- Example: In "Fed rate cuts → short rates down → curve steepening", extract:
  - Fed funds rate (implicit - no value given)
  - Short-term rates (implicit)
  - Yield curve (implicit)

INPUT TEXT:
{synthesis_text}

OUTPUT FORMAT (JSON):
{{
  "explicit_variables": [
    {{
      "name": "TGA",
      "role": "trigger",
      "role_reasoning": "mentioned as condition that initiates policy response",
      "threshold": "500",
      "threshold_unit": "billion_usd",
      "threshold_condition": "less_than",
      "threshold_data_year": "2026",
      "threshold_is_example": true,
      "context": "TGA drawdown schedule",
      "source_type": "explicit"
    }}
  ],
  "implicit_variables": [
    {{
      "name": "short-term rates",
      "role": "indicator",
      "role_reasoning": "appears in causal chain as intermediate variable",
      "context": "Fed rate cuts → short rates down",
      "source_chain": "Fed rate cuts → short rates down → curve steepening",
      "source_type": "implicit"
    }}
  ],
  "chain_dependencies": [
    {{
      "chain": "Fed rate cuts → short rates down → curve steepening",
      "steps": [
        {{"from": "fed_funds_rate", "to": "short_rates", "relationship": "causes"}},
        {{"from": "short_rates", "to": "yield_curve", "relationship": "leads_to"}}
      ]
    }}
  ]
}}

ROLE CLASSIFICATION:
- "indicator": Early warning signal to WATCH continuously
- "trigger": Hard constraint that CAUSES action when breached
- "confirmation": After-the-fact validation signal
- null: If role is unclear

IMPORTANT:
- Extract ALL variables - both explicit (with values) and implicit (in chains)
- Deduplicate: if a variable appears both explicitly and in chains, put it in explicit_variables with enriched context
- For implicit variables, include the source_chain where it was found
- Extract chain_dependencies to capture the causal relationships
- Use standardized names: TGA, RRP, QT, Fed funds rate, VIX, FCI, SOFR, etc.

Return ONLY the JSON, no additional text."""


# Prompt for batch chain parsing (multiple chains in single call)
BATCH_CHAIN_PARSING_PROMPT = """Parse these financial logic chains into component variables and causal relationships.

CHAINS:
{chains}

For EACH chain, identify:
1. Variables involved
2. Causal relationships between them
3. Role of each variable (indicator/trigger/confirmation)

OUTPUT FORMAT (JSON):
{{
  "parsed_chains": [
    {{
      "chain": "original chain text",
      "variables": [
        {{"name": "var1", "role": "indicator"}},
        {{"name": "var2", "role": "trigger"}}
      ],
      "steps": [
        {{"from": "var1", "to": "var2", "relationship": "causes"}}
      ]
    }}
  ],
  "all_variables": ["var1", "var2", "var3"]
}}

RELATIONSHIP TYPES: causes, leads_to, influences, triggers, correlates_with

ROLE CLASSIFICATION:
- "indicator": Variables at START of chain (we monitor these)
- "trigger": Variables in CONDITIONAL position (cause action when breached)
- "confirmation": Variables at END of chain (validate outcome)

Return ONLY the JSON."""
