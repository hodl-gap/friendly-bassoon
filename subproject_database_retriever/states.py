"""
LangGraph State Definitions for Database Retriever

Defines the state schema used to pass data between function modules.
Keep states minimal - add fields as needed during development.
"""

from typing import TypedDict, List, Optional, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.schemas import LogicChain, ConfidenceMetadata


class RetrieverState(TypedDict, total=False):
    """Main state for the retrieval workflow."""

    # Input
    query: str  # User's original query
    image_path: str  # Optional path to indicator chart image

    # Query Processing
    processed_query: str  # Cleaned/expanded query
    query_variations: List[str]  # Alternative phrasings for better recall
    query_dimensions: List[Dict[str, Any]]  # Dimension-based query breakdown with reasoning (debug)
    query_type: str  # "research_question" or "data_lookup"
    query_temporal_reference: Dict[str, Any]  # {reference_year, reference_period, is_future, is_current}

    # Retrieval
    retrieved_chunks: List[Dict[str, Any]]  # Retrieved documents from Pinecone
    retrieval_scores: List[float]  # Similarity scores
    data_temporal_summary: Dict[str, Any]  # Summary of temporal context from retrieved chunks

    # Chain Expansion (follows dangling effects)
    dangling_effects_followed: List[str]  # Effects that were followed up with additional queries

    # Synthesis & Answer
    answer: str  # Final generated answer (logic chains)
    synthesis: str  # Consensus chains + variables to monitor
    contradictions: str  # Contradicting evidence analysis

    # Confidence Metadata
    confidence_metadata: ConfidenceMetadata  # {score, chain_count, source_diversity, confidence_level}

    # Topic Coverage (detects when query topic not found in retrieved chunks)
    topic_coverage: Dict[str, Any]  # {query_entities, found_entities, direct_match, extrapolation_note}

    # Knowledge Gap Detection & Filling
    knowledge_gaps: Dict[str, Any]  # Gap detection results from detect_knowledge_gaps()
    gap_enrichment_text: str  # Additional context from filled gaps
    filled_gaps: List[Dict[str, Any]]  # Gaps successfully filled
    partially_filled_gaps: List[Dict[str, Any]]  # Gaps with partial information
    unfillable_gaps: List[Dict[str, Any]]  # Gaps that could not be filled
    extracted_web_chains: List[LogicChain]  # Logic chains from web extraction
    logic_chains: List[LogicChain]  # Merged DB + web chains

    # Agentic Control
    iteration_count: int  # Number of retrieval iterations
    needs_refinement: bool  # Whether to iterate again
    skip_gap_filling: bool  # If True, skip gap detection and filling
