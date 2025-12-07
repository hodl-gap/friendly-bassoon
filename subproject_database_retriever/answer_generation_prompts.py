"""
Prompts for Answer Generation Module
"""

LOGIC_CHAIN_PROMPT = """You are analyzing financial research to extract logic chains relevant to a query.

Query: {query}

Research Context:
{context}

Instructions:
1. Identify logic chains (cause → effect relationships) relevant to the query
2. Connect chains where one chain's effect matches another's cause to form longer sequences
3. Use the interpretation/what_happened context to supplement chain understanding
4. Output as structured list only - no narrative summary

Output Format:
CHAIN: cause → effect → [next effect if connected]
MECHANISM: mechanism for each step
SOURCE: which source(s) support this chain

Example:
CHAIN: Fed rate cuts → real rates down → risk asset valuations up
MECHANISM: rate cuts reduce yields → lower real yields increase present value of future cash flows
SOURCE: Goldman Sachs, UBS"""
