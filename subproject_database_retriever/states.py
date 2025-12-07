"""
LangGraph State Definitions for Database Retriever

Defines the state schema used to pass data between function modules.
Keep states minimal - add fields as needed during development.
"""

from typing import TypedDict, List, Optional, Dict, Any


class RetrieverState(TypedDict, total=False):
    """Main state for the retrieval workflow."""

    # Input
    query: str  # User's original query

    # Query Processing
    processed_query: str  # Cleaned/expanded query
    query_variations: List[str]  # Alternative phrasings for better recall
    query_dimensions: List[Dict[str, Any]]  # Dimension-based query breakdown with reasoning (debug)
    query_type: str  # "research_question" or "data_lookup"

    # Retrieval
    retrieved_chunks: List[Dict[str, Any]]  # Retrieved documents from Pinecone
    retrieval_scores: List[float]  # Similarity scores

    # Synthesis & Answer
    synthesized_context: str  # Combined relevant context
    answer: str  # Final generated answer

    # Agentic Control
    iteration_count: int  # Number of retrieval iterations
    needs_refinement: bool  # Whether to iterate again
    confidence_score: float  # Self-assessed answer confidence
