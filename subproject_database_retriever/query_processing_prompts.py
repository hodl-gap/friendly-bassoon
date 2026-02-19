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

(repeat for each, 2-3 total)

## Example (simple query → 3 focused dimensions)
<!-- [FEW-SHOT v1] Source: run_20260211_075133. Review & improve with more diverse examples. -->

Original query: What does rising RDE indicate about liquidity conditions?

DIMENSION: Direct RDE-Liquidity Link
REASONING: Targets the core relationship between RDE movements and liquidity assessment in financial markets.
QUERY: RDE rising liquidity conditions market

DIMENSION: RDE as Liquidity Indicator
REASONING: Frames RDE explicitly as a diagnostic tool for understanding systemic liquidity tightness or ease.
QUERY: RDE liquidity indicator financial stress

DIMENSION: RDE and Money Market Conditions
REASONING: Connects RDE signals to the operational liquidity environment where short-term funding occurs.
QUERY: RDE money market liquidity tightening"""


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

(repeat for each, 4-6 total)

## Example (complex multi-factor → 6 orthogonal dimensions)
<!-- [FEW-SHOT v1] Source: run_20260211_081106. Review & improve with more diverse examples. -->

Original query: What is the impact on global liquidity and fiat currency from: (1) global stockpiling demand, (2) AI investment cycle, (3) global fiscal spending expansion, (4) defense and public investment increase, (5) China domestic demand policy pivot, and (6) China demand recovery from deeply negative to neutral levels?

DIMENSION: Monetary Base Expansion & Reserve Accumulation
REASONING: These demand shocks will mechanically increase central bank balance sheets and fiat money supply as central banks intervene to manage currency pressures and liquidity.
QUERY: Central bank balance sheet expansion, reserve accumulation, and monetary base growth from increased global demand and fiscal spending

DIMENSION: Commodity & FX Pressure from Demand Surge
REASONING: Stockpiling, AI capex, and China demand recovery will drive commodity prices and currency flows, forcing central banks to manage inflation and exchange rate volatility.
QUERY: Commodity price inflation, currency appreciation pressures, and foreign exchange intervention from global investment cycle and China demand recovery

DIMENSION: Real Rates & Liquidity Conditions
REASONING: Fiscal expansion and defense spending increase nominal demand and inflation expectations, which compresses real rates and affects global liquidity availability.
QUERY: Real interest rates, liquidity conditions, and inflation expectations from fiscal expansion, defense spending, and China policy pivot

DIMENSION: Capital Flows & Cross-Border Liquidity
REASONING: AI investment and stockpiling create uneven capital allocation across regions, generating liquidity mismatches and currency carry dynamics.
QUERY: Cross-border capital flows, emerging market liquidity, and currency carry trades from AI investment concentration and global demand shifts

DIMENSION: Fiat Currency Debasement & Purchasing Power
REASONING: Sustained fiscal spending and monetary accommodation to support these demand shocks will erode fiat currency value and purchasing power globally.
QUERY: Fiat currency debasement, purchasing power erosion, and inflation from sustained fiscal spending and monetary accommodation

DIMENSION: Debt Issuance & Credit Expansion
REASONING: Funding defense, infrastructure, and AI investment requires massive government and corporate debt issuance, expanding credit and money supply.
QUERY: Government debt issuance, credit expansion, and money supply growth from defense spending, public investment, and AI capex cycle"""


QUERY_REFINEMENT_PROMPT = """You are refining a financial research query because the initial
search returned insufficient results.

ORIGINAL QUERY: {query}

WHAT WAS FOUND (brief summaries of {chunk_count} chunks):
{chunk_summaries}

Your task: Generate a SINGLE refined query that:
1. Broadens the search if results were too narrow
2. Uses alternative terminology for the same concepts
3. Removes overly specific qualifiers that may have limited recall
4. Keeps the core research intent intact

Return ONLY the refined query text, nothing else."""


# Legacy prompt for backward compatibility
QUERY_EXPANSION_PROMPT = QUERY_EXPANSION_PROMPT_COMPLEX
