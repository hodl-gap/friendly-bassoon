"""State definitions for BTC Impact Module."""

from typing import TypedDict, List, Optional, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.schemas import LogicChain, ConfidenceMetadata


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
    historical_chains: List[Dict]  # Loaded from btc_relationships.json
    discovered_chains: List[Dict]  # New logic chains found this run

    # Output - Belief Space (Multi-Scenario)
    scenarios: List[Dict[str, Any]]
    # Each scenario:
    # {
    #     "name": "Liquidity Crunch",
    #     "direction": "BEARISH",
    #     "likelihood": 0.65,
    #     "chain": "tga_increase -> reserve_drain -> funding_stress -> btc_pressure",
    #     "chain_steps": [{"cause": "...", "effect": "...", "mechanism": "..."}],
    #     "rationale": "TGA increased 10%, draining reserves...",
    #     "key_data_points": ["TGA: $923B (+10%)", "Reserves: -$50B"],
    #     "polarity": "BEARISH"  # Explicit outcome polarity
    # }

    # Primary direction (highest likelihood scenario) - for backward compatibility
    direction: str  # BULLISH / BEARISH / NEUTRAL
    confidence: ConfidenceMetadata
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

    # Belief Space Metadata
    belief_space: Dict[str, Any]
    # {
    #     "contradictions": [
    #         {
    #             "thesis_a": "CAPEX increase implies value destruction",
    #             "thesis_b": "CAPEX increase confirms AI leadership",
    #             "source_a": "BofA",
    #             "source_b": "Morgan Stanley",
    #             "implication": "Market pricing both scenarios simultaneously"
    #         }
    #     ],
    #     "regime_uncertainty": "high" | "medium" | "low",
    #     "narrative_count": 3,
    #     "dominant_narrative": "Scenario A: Liquidity Crunch"
    # }

    # Debug
    retrieval_answer: str  # Raw answer from retriever
    synthesis: str  # Raw synthesis from retriever (renamed from retrieval_synthesis)

    # Topic Coverage (extrapolation warning)
    topic_coverage: Dict[str, Any]  # {query_entities, found_entities, direct_match, extrapolation_note}

    # Regime State (Phase 3)
    regime_state: Dict[str, Any]  # Current liquidity regime from relationship_store

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
