"""
LangGraph State Definitions for Data Collection

Defines the state schema used to pass data between function modules.
Keep states minimal - add fields as needed during development.
"""

from typing import TypedDict, List, Optional, Dict, Any


class DataCollectionState(TypedDict, total=False):
    """Main state for the data collection workflow."""

    # =========================================================================
    # INPUT
    # =========================================================================
    mode: str  # "news_collection" | "claim_validation"

    # For claim_validation mode
    claims_input: List[Dict[str, Any]]  # Pre-parsed claims (optional)
    retriever_synthesis: str  # Full synthesis text from database_retriever
    variable_mappings: Dict[str, Any]  # Data ID mappings from variable_mapper

    # For news_collection mode
    news_query: str  # Topic to search (e.g., "Japanese insurers rebalancing")
    news_sources: List[str]  # Sources to query (e.g., ["reuters", "bloomberg"])
    time_window_days: int  # How far back to search (default: 7)

    # =========================================================================
    # CLAIM VALIDATION PATH
    # =========================================================================
    parsed_claims: List[Dict[str, Any]]
    # Example: [{
    #     "claim_text": "BTC follows gold with 63-428 day lag",
    #     "variable_a": "btc",
    #     "variable_b": "gold",
    #     "relationship_type": "correlation",  # correlation|lag|threshold|trend
    #     "expected_lag": {"min": 63, "max": 428, "unit": "days"},
    #     "testability_score": 0.9
    # }]

    resolved_data_ids: Dict[str, Dict[str, Any]]
    # Example: {
    #     "btc": {"data_id": "CoinGecko:bitcoin", "source": "CoinGecko"},
    #     "gold": {"data_id": "FRED:GOLDAMGBD228NLBM", "source": "FRED"}
    # }

    fetched_data: Dict[str, Any]
    # Example: {
    #     "btc": {"data": [(date, value), ...], "source": "CoinGecko", "start": "2020-01-01"},
    #     "gold": {"data": [(date, value), ...], "source": "FRED", "start": "2020-01-01"}
    # }

    validation_results: List[Dict[str, Any]]
    # Example: [{
    #     "claim": "BTC follows gold with 63-428 day lag",
    #     "status": "partially_confirmed",  # confirmed|refuted|partially_confirmed|inconclusive
    #     "actual_correlation": 0.45,
    #     "optimal_lag_days": 127,
    #     "p_value": 0.001,
    #     "confidence_interval": [0.32, 0.58],
    #     "interpretation": "Correlation exists but weaker than implied"
    # }]

    # =========================================================================
    # NEWS COLLECTION PATH
    # =========================================================================
    collected_articles: List[Dict[str, Any]]
    # Example: [{
    #     "title": "Japanese insurers shift to JGBs",
    #     "source": "Reuters",
    #     "date": "2026-01-27",
    #     "content": "...",
    #     "url": "https://..."
    # }]

    filtered_articles: List[Dict[str, Any]]  # Relevant articles after LLM filtering

    analyzed_news: List[Dict[str, Any]]
    # Example: [{
    #     "article": {...},
    #     "institution": "GPIF",
    #     "institution_type": "pension_fund",
    #     "action": "rebalancing",
    #     "asset_class": "fixed_income",
    #     "direction": "buy",
    #     "confidence": 0.85,
    #     "actionable_insight": "Japanese pension fund buying JGBs signals risk-off"
    # }]

    retriever_queries: List[str]
    # Example: ["What does Japanese insurer rebalancing into JGBs mean for risk assets?"]

    # =========================================================================
    # OUTPUT
    # =========================================================================
    final_output: Dict[str, Any]
    # Structured output for downstream consumers

    # =========================================================================
    # CONTROL FLOW
    # =========================================================================
    errors: List[str]  # Errors encountered during processing
    warnings: List[str]  # Non-fatal warnings
    skip_news_analysis: bool  # Skip analysis if no relevant articles found
