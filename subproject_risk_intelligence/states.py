"""State definitions for BTC Impact Module."""

from typing import TypedDict, List, Optional, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.schemas import LogicChain, ConfidenceMetadata


class InsightTrack(TypedDict, total=False):
    """A single reasoning track in an insight report."""
    track_id: str
    title: str                          # "Historical Pattern Track"
    causal_mechanism: str               # Arrow notation
    causal_steps: List[Dict[str, Any]]
    historical_evidence: Dict[str, Any] # {precedent_count, success_rate, precedent_summary, precedents: [...]}
    asset_implications: List[Dict]      # [{asset, direction, magnitude_range, timing}]
    monitoring_variables: List[Dict]    # [{variable, condition, meaning}]
    confidence: float
    time_horizon: str
    sequence_position: int              # 1, 2, 3... for temporal ordering (Gap 3)


class RiskImpactState(TypedDict, total=False):
    # Input
    query: str  # User's original query

    # Retrieval Results (from database_retriever)
    retrieved_chunks: List[Dict[str, Any]]  # Raw chunks from retriever
    logic_chains: List[LogicChain]  # Parsed logic chains
    confidence_metadata: ConfidenceMetadata  # {score, chain_count, source_diversity}

    # Variable Extraction (Phase 2)
    extracted_variables: List[Dict[str, Any]]
    # Each: {normalized: str, role: "cause"|"effect", chain_path: str, source: str}

    # Asset class (multi-asset support)
    asset_class: str  # "btc", "equity"
    asset_price: float  # Current price of target asset

    # Data Fetching (Phase 2)
    current_values: Dict[str, Any]  # {variable_name: {value, timestamp, source}}
    btc_price: float  # Current BTC price (kept for backwards compat)
    fetch_errors: List[str]  # Variables that failed to fetch

    # Pattern Validation (Phase 2)
    validated_patterns: List[Dict[str, Any]]  # Patterns extracted from research, validated against current data
    # Each: {pattern: {...}, triggered: bool, current_metric: float, threshold: float, explanation: str}

    # Relationship Store (Phase 3)
    historical_chains: List[Dict]  # Loaded from relationships.json
    discovered_chains: List[Dict]  # New logic chains found this run

    # Primary direction (highest confidence track) - for backward compatibility
    direction: str  # BULLISH / BEARISH / NEUTRAL
    confidence: ConfidenceMetadata
    time_horizon: str  # "intraday" | "days" | "weeks" | "months" | "regime_shift"
    rationale: str  # Explanation text
    risk_factors: List[str]  # What could invalidate the thesis

    # Debug
    retrieval_answer: str  # Raw answer from retriever
    synthesis: str  # Raw synthesis from retriever (renamed from retrieval_synthesis)

    # Topic Coverage (extrapolation warning)
    topic_coverage: Dict[str, Any]  # {query_entities, found_entities, direct_match, extrapolation_note}

    # Regime State (Phase 3)
    regime_state: Dict[str, Any]  # Current liquidity regime from relationship_store

    # Theme States (Phase 6 - proactive research)
    theme_states: Dict[str, Any]  # Per-theme assessments from theme_index.json

    # Historical Event Data (Phase 4)
    historical_event_data: Dict[str, Any]
    # {
    #     "event_detected": True,
    #     "event_name": "August 2024 Yen Carry Trade Crash",
    #     "period": {"start": "2024-07-25", "end": "2024-08-15"},
    #     "instruments": {
    #         "USDJPY": {"ticker": "...", "role": "...", "data": [...], "metrics": {...}},
    #         ...
    #     },
    #     "correlations": {"BTC_vs_VIX": 0.82, ...},
    #     "comparison_to_current": {...}
    # }

    # Knowledge Gap Detection (from retrieval layer)
    knowledge_gaps: Dict[str, Any]  # Gap detection results
    gap_enrichment_text: str  # Additional context from filled gaps
    filled_gaps: List[Dict[str, Any]]  # Gaps successfully filled
    partially_filled_gaps: List[Dict[str, Any]]  # Gaps with partial info
    unfillable_gaps: List[Dict[str, Any]]  # Gaps that could not be filled

    # Claim validation results (from data_collection claim validation)
    claim_validation_results: List[Dict[str, Any]]

    # Multi-hop chain graph (Phase 2 - chain traversal)
    chain_tracks: List[Dict[str, Any]]  # Multi-hop tracks from chain graph
    chain_graph_text: str  # Formatted graph for prompt

    # Historical N-analog aggregation (Phase 3)
    historical_analogs: Dict[str, Any]  # {"enriched": [...], "aggregated": {...}}
    historical_analogs_text: str  # Formatted for prompt

    # Regime characterization (Gap 1)
    regime_characterization_text: str  # Formatted "Then vs Now" regime comparison

    # EDF knowledge tree from Phase 0 (optional, passed through for routing directives)
    _edf_knowledge_tree: Dict[str, Any]

    # Insight output
    insight_output: Dict[str, Any]  # InsightOutput (tracks, synthesis, key_uncertainties)
