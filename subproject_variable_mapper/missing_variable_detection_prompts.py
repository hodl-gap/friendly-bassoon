"""
Prompts for Missing Variable Detection Module
"""

# Prompt for parsing a logic chain into component variables
CHAIN_PARSING_PROMPT = """Parse this financial logic chain into its component variables and causal relationships.

CHAIN: {chain}

INSTRUCTIONS:
1. Identify each distinct variable/metric in the chain
2. Use standardized financial terms (e.g., "Fed funds rate" not "Fed policy")
3. Use common abbreviations where appropriate (TGA, QT, RRP, VIX, FCI, etc.)
4. Identify the causal relationship between consecutive variables

RELATIONSHIP TYPES:
- "causes": Direct causal relationship (A causes B)
- "leads_to": Sequential outcome (A leads to B)
- "influences": Indirect effect (A influences B)
- "triggers": Event-driven (A triggers B)
- "correlates_with": Statistical relationship

Return ONLY a JSON object:
{{
    "chain": "{chain}",
    "variables": ["var1", "var2", "var3"],
    "steps": [
        {{"from": "var1", "to": "var2", "relationship": "causes"}},
        {{"from": "var2", "to": "var3", "relationship": "leads_to"}}
    ]
}}

IMPORTANT:
- Extract ONLY measurable financial variables
- Skip qualitative concepts like "risk sentiment" unless they have a measurable proxy
- Each step should connect consecutive variables in the chain

Return ONLY the JSON, no additional text."""
