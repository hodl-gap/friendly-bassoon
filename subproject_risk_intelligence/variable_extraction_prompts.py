"""Prompts for LLM-based variable extraction."""

VARIABLE_INFERENCE_PROMPT = """You are extracting financial variables relevant to a macro research query.

QUERY:
{query}

RESEARCH SYNTHESIS:
{synthesis}

LOGIC CHAINS:
{chains}

KNOWN VARIABLE VOCABULARY:
{known_variables}

Your task: Identify ALL variables relevant to this analysis.

1. **Explicitly named**: Variables directly mentioned in the query, synthesis, or chains
2. **Logically implied**: Variables that are causally connected to the mentioned variables
   - Example: "Fed tightening" implies fed_balance_sheet, bank_reserves, sofr
   - Example: "carry trade unwind" implies usdjpy, vix, emerging market currencies
   - Example: "risk-off move" implies vix, gold, dxy, us10y

Return variables from the known vocabulary when possible. For variables NOT in the vocabulary, add them to suggested_new in snake_case format.

IMPORTANT:
- Use exact names from the known vocabulary (lowercase)
- Only suggest truly new variables that aren't covered by existing names
- Include logically implied variables even if not explicitly mentioned
- Be thorough but relevant — only include variables connected to the analysis"""
