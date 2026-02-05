"""
Prompts for News Collection

Contains prompts for filtering and categorizing collected news.
"""


NEWS_RELEVANCE_PROMPT = """You are a financial news analyst filtering articles for relevance to institutional investor activity.

SEARCH QUERY: {query}

ARTICLE TO EVALUATE:
Title: {title}
Source: {source}
Published: {published}
Summary: {summary}

Determine if this article is relevant to the search query, specifically looking for:
1. Institutional investor activity (pension funds, sovereign wealth, insurers)
2. Asset allocation changes or rebalancing decisions
3. Large-scale portfolio movements
4. Central bank policy impacts on institutional flows

OUTPUT FORMAT (JSON only):
{{
  "is_relevant": true|false,
  "relevance_score": 0.0-1.0,
  "relevance_reason": "Brief explanation",
  "mentioned_entities": ["Entity1", "Entity2"],
  "topic_category": "institutional_flow|policy|market_event|other"
}}

Return ONLY the JSON, nothing else."""


NEWS_CATEGORIZATION_PROMPT = """Categorize this financial news article by its primary focus.

ARTICLE:
Title: {title}
Summary: {summary}

CATEGORIES:
- institutional_rebalancing: Pension funds, insurers, asset managers changing allocations
- sovereign_wealth: Sovereign wealth fund activity or announcements
- central_bank: Central bank policy, reserves, or intervention
- currency_intervention: FX market intervention or currency policy
- risk_sentiment: Risk-on/risk-off shifts, market sentiment changes
- regulatory: New regulations affecting institutional investors
- economic_data: Economic releases affecting asset allocation
- other: None of the above

OUTPUT FORMAT (JSON only):
{{
  "primary_category": "category_name",
  "secondary_categories": ["category1", "category2"],
  "confidence": 0.0-1.0
}}

Return ONLY the JSON, nothing else."""


BATCH_RELEVANCE_PROMPT = """You are filtering a batch of news articles for relevance to institutional investor activity.

SEARCH CONTEXT: {query}

ARTICLES:
{articles_list}

For each article, determine relevance to institutional investor flows, rebalancing, and large-scale portfolio activity.

OUTPUT FORMAT (JSON array):
[
  {{
    "article_index": 0,
    "is_relevant": true|false,
    "relevance_score": 0.0-1.0,
    "key_entities": ["Entity1"]
  }},
  ...
]

Return ONLY the JSON array, nothing else."""
