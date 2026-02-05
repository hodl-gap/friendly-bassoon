"""
Prompts for Query Processing Module
"""

QUERY_TYPE_PROMPT = """Classify this query as either "research_question" or "data_lookup".

- research_question: Questions about concepts, interpretations, relationships, causes/effects
- data_lookup: Requests for specific metrics, thresholds, numbers, or exact data points

Query: {query}

Respond with only: research_question or data_lookup"""


# Prompt for SIMPLE queries (short, single-concept) - generates 2-3 variations
QUERY_EXPANSION_PROMPT_SIMPLE = """You are a query expansion engine for a financial/economic research database.

Your task: Generate 2-3 search queries that approach this question from different angles.

## Guidelines
- Stay VERY CLOSE to the original query - minor variations only
- Use concrete market terms: "equities", "stocks", "rate cuts", "Fed balance sheet"
- Keep queries simple and searchable
- Don't over-expand - this is a straightforward query

Generate exactly 2-3 query variations.

Original query: {query}

## Output Format
DIMENSION: [short name for this angle]
REASONING: [one sentence - why this angle matters]
QUERY: [the search query]

(repeat for each, 2-3 total)"""


# Prompt for COMPLEX queries (multi-concept, relationships) - generates 4-6 variations
QUERY_EXPANSION_PROMPT_COMPLEX = """You are a query expansion engine for a financial/economic research database.

Your task: Generate search queries that approach the question from different angles.

## Guidelines
- Stay CLOSE to the original query - small variations, not big tangents
- Use concrete market terms: "equities", "stocks", "rate cuts", "Fed balance sheet" - not academic jargon
- Each query should be recognizable as related to the original question
- Keep queries simple and searchable

## CRITICAL: Mechanical Operations
For any abstract event (intervention, QE, rate hike, etc.), FIRST identify the concrete mechanical operation:
- What is BOUGHT and what is SOLD?
- What asset/currency INCREASES vs DECREASES?

Then ensure at least ONE query uses these concrete action terms, not just the abstract event name.

Examples:
- "yen intervention to strengthen yen" → Japan SELLS USD, BUYS JPY → include query with "selling dollars" or "USD reserve drawdown"
- "Fed QE" → Fed BUYS bonds → include query with "Fed buying treasuries" or "balance sheet expansion"
- "rate hike" → raising interest rates → include query with "higher policy rate" or "tightening"

## Think About
- What is the MECHANICAL/DIRECT effect? (first-order)
- What are the MARKET/BEHAVIORAL consequences? (second-order)
- What causes this vs what results from it?

Generate 4-6 query variations. At least one MUST use concrete mechanical action terms.

Original query: {query}

## Output Format
DIMENSION: [short name for this angle]
REASONING: [one sentence - why this angle matters]
QUERY: [the search query]

(repeat for each, 4-6 total)"""


# Legacy prompt for backward compatibility
QUERY_EXPANSION_PROMPT = QUERY_EXPANSION_PROMPT_COMPLEX
