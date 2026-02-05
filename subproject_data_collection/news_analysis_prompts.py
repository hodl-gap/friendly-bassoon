"""
Prompts for News Analysis

Contains prompts for analyzing news actionability and generating retriever queries.
"""


NEWS_ACTIONABILITY_PROMPT = """You are a financial analyst extracting actionable insights from institutional investor news.

ARTICLE:
Title: {title}
Source: {source}
Published: {published}
Summary: {summary}
Content: {content}

Extract any actionable insights about institutional investor behavior, specifically:
1. Which institution or type of institution (pension fund, insurer, sovereign wealth, etc.)
2. What action they are taking (buying, selling, rebalancing, hedging)
3. Which asset class or market
4. Direction of the flow (risk-on, risk-off, duration, credit, etc.)
5. Why this matters for markets

OUTPUT FORMAT (JSON only):
{{
  "institution": "Name or type of institution",
  "institution_type": "pension_fund|insurer|sovereign_wealth|central_bank|asset_manager|other",
  "action": "buying|selling|rebalancing|hedging|allocating",
  "asset_class": "equities|bonds|fx|commodities|crypto|alternatives",
  "specific_assets": ["JGBs", "USD/JPY"],
  "direction": "risk_on|risk_off|duration_extension|credit_tightening|other",
  "size_indicator": "large|medium|small|unknown",
  "confidence": 0.0-1.0,
  "actionable_insight": "One sentence summary of what this means for markets",
  "market_implications": ["Implication 1", "Implication 2"]
}}

If no clear institutional action is described, set confidence to 0.

Return ONLY the JSON, nothing else."""


RETRIEVER_QUERY_GENERATION_PROMPT = """Based on these institutional investor news insights, generate queries to send to the research database retriever.

The retriever contains:
- Telegram messages from financial research communities
- Analysis of macro, liquidity, and institutional flows
- Historical patterns and correlations

INSIGHTS:
{insights}

Generate 2-4 specific queries that would help understand:
1. Historical precedents for similar institutional actions
2. Related macro/liquidity dynamics
3. Implications for other asset classes
4. Expected market impact timeline

OUTPUT FORMAT (JSON only):
{{
  "queries": [
    "What happens to risk assets when Japanese insurers rebalance into JGBs?",
    "Historical correlation between yen weakness and institutional JPY hedging",
    "How does Japanese insurer rebalancing affect Treasury demand?"
  ],
  "query_rationale": [
    "Understand precedent for this institutional behavior",
    "Connect yen dynamics to institutional flows",
    "Assess cross-market implications"
  ]
}}

Return ONLY the JSON, nothing else."""


NEWS_SUMMARY_PROMPT = """Summarize the key institutional investor insights from these analyzed news items.

ANALYZED NEWS:
{analyzed_news}

Create a brief summary highlighting:
1. Most significant institutional moves
2. Overall market direction implied
3. Key assets or markets affected
4. Confidence level in the signals

OUTPUT FORMAT (JSON only):
{{
  "summary": "2-3 sentence summary of key institutional activity",
  "dominant_theme": "risk_off|risk_on|rotation|hedging|mixed",
  "key_institutions": ["Institution 1", "Institution 2"],
  "affected_markets": ["Market 1", "Market 2"],
  "overall_confidence": 0.0-1.0,
  "recommended_actions": ["Action 1", "Action 2"]
}}

Return ONLY the JSON, nothing else."""


INSTITUTION_EXTRACTION_PROMPT = """Extract institutional investor entities mentioned in this text.

TEXT:
{text}

Look for:
- Named institutions (GPIF, CalPERS, Norges Bank, etc.)
- Types of institutions (pension funds, insurers, sovereign wealth funds)
- Central banks
- Large asset managers

OUTPUT FORMAT (JSON only):
{{
  "institutions": [
    {{
      "name": "Institution name or type",
      "type": "pension_fund|insurer|sovereign_wealth|central_bank|asset_manager",
      "country": "Country if mentioned",
      "mentioned_action": "What they are doing"
    }}
  ]
}}

Return ONLY the JSON, nothing else."""
