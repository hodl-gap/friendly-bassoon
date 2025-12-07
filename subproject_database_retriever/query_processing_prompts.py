"""
Prompts for Query Processing Module
"""

QUERY_TYPE_PROMPT = """Classify this query as either "research_question" or "data_lookup".

- research_question: Questions about concepts, interpretations, relationships, causes/effects
- data_lookup: Requests for specific metrics, thresholds, numbers, or exact data points

Query: {query}

Respond with only: research_question or data_lookup"""


QUERY_EXPANSION_PROMPT = """You are a query expansion engine for a financial/economic research database.

Your task: Generate search queries that approach the question from different angles.

## Guidelines
- Stay CLOSE to the original query - small variations, not big tangents
- Use concrete market terms: "equities", "stocks", "rate cuts", "Fed balance sheet" - not academic jargon
- Each query should be recognizable as related to the original question
- Keep queries simple and searchable

## Think About
- What directly vs indirectly relates to this?
- What precedes, coincides with, or follows from this?
- What causes this vs what results from it?

Generate 4-6 query variations.

Original query: {query}

## Output Format
DIMENSION: [short name for this angle]
REASONING: [one sentence - why this angle matters]
QUERY: [the search query]

(repeat for each)"""
