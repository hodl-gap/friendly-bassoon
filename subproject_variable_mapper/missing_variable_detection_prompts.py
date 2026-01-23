"""
Prompts for Missing Variable Detection Module
"""

# Prompt for parsing a logic chain into component variables
CHAIN_PARSING_PROMPT = """Parse this financial logic chain into its component variables, causal relationships, and roles.

CHAIN: {chain}

INSTRUCTIONS:
1. Identify each distinct variable/metric in the chain
2. Use standardized financial terms (e.g., "Fed funds rate" not "Fed policy")
3. Use common abbreviations where appropriate (TGA, QT, RRP, VIX, FCI, etc.)
4. Identify the causal relationship between consecutive variables
5. Classify each variable's ROLE based on its position/usage in the chain

RELATIONSHIP TYPES:
- "causes": Direct causal relationship (A causes B)
- "leads_to": Sequential outcome (A leads to B)
- "influences": Indirect effect (A influences B)
- "triggers": Event-driven (A triggers B)
- "correlates_with": Statistical relationship

ROLE CLASSIFICATION (based on position in chain):
- "indicator": Variables at the START of a chain (causal position) - something we monitor continuously
- "trigger": Variables in CONDITIONAL position ("if X then...", "when X reaches...") - causes action when breached
- "confirmation": Variables at the END of a chain (outcome position) - validates the final outcome

Return ONLY a JSON object:
{{
    "chain": "{chain}",
    "variables": [
        {{"name": "var1", "role": "indicator"}},
        {{"name": "var2", "role": "trigger"}},
        {{"name": "var3", "role": "confirmation"}}
    ],
    "steps": [
        {{"from": "var1", "to": "var2", "relationship": "causes"}},
        {{"from": "var2", "to": "var3", "relationship": "leads_to"}}
    ]
}}

IMPORTANT:
- Extract ONLY measurable financial variables
- Skip qualitative concepts like "risk sentiment" unless they have a measurable proxy
- Each step should connect consecutive variables in the chain
- First variable in chain → typically "indicator"
- Middle variables with threshold conditions → typically "trigger"
- Final outcome variable → typically "confirmation"

Return ONLY the JSON, no additional text."""
