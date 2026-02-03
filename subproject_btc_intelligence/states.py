"""State definitions for BTC Impact Module."""

from typing import TypedDict, List, Optional, Dict, Any


class BTCImpactState(TypedDict, total=False):
    # Input
    query: str  # User's original query

    # Retrieval Results (from database_retriever)
    retrieved_chunks: List[Dict[str, Any]]  # Raw chunks from retriever
    logic_chains: List[Dict[str, Any]]  # Parsed logic chains
    confidence_metadata: Dict[str, Any]  # {overall_score, path_count, source_diversity}

    # Variable Extraction (Phase 2)
    extracted_variables: List[Dict[str, Any]]
    # Each: {normalized: str, role: "cause"|"effect", chain_path: str, source: str}

    # Data Fetching (Phase 2)
    current_values: Dict[str, Any]  # {variable_name: {value, timestamp, source}}
    btc_price: float  # Current BTC price
    fetch_errors: List[str]  # Variables that failed to fetch

    # Pattern Validation (Phase 2)
    validated_patterns: List[Dict[str, Any]]  # Patterns extracted from research, validated against current data
    # Each: {pattern: {...}, triggered: bool, current_metric: float, threshold: float, explanation: str}

    # Relationship Store (Phase 3)
    historical_chains: List[Dict]  # Loaded from btc_relationships.json
    discovered_chains: List[Dict]  # New logic chains found this run

    # Output
    direction: str  # BULLISH / BEARISH / NEUTRAL
    confidence: Dict[str, Any]
    # {
    #     "score": 0.72,
    #     "chain_count": 3,
    #     "source_diversity": 2,
    #     "strongest_chain": "tga -> liquidity -> btc"
    # }
    time_horizon: str  # "intraday" | "days" | "weeks" | "months" | "regime_shift"
    decay_profile: str  # "fast" | "medium" | "slow"
    rationale: str  # Explanation text
    risk_factors: List[str]  # What could invalidate the thesis

    # Debug
    retrieval_answer: str  # Raw answer from retriever
    retrieval_synthesis: str  # Raw synthesis from retriever

    # Topic Coverage (extrapolation warning)
    topic_coverage: Dict[str, Any]  # {query_entities, found_entities, direct_match, extrapolation_note}

    # Regime State (Phase 3)
    regime_state: Dict[str, Any]  # Current liquidity regime from relationship_store
