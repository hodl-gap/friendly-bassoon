"""
Vector Search Module

Performs semantic search in Pinecone vector database.
Supports multi-query retrieval using query variations.
"""

import sys
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from pinecone import Pinecone
from models import call_openai_embedding, call_openai_embedding_batch
from states import RetrieverState
from config import PINECONE_API_KEY, PINECONE_INDEX_NAME, DEFAULT_TOP_K, SIMILARITY_THRESHOLD

# Pinecone index singleton
_pinecone_index = None


def get_pinecone_index():
    """Initialize Pinecone connection (singleton)."""
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def search_vectors(state: RetrieverState) -> RetrieverState:
    """
    Search Pinecone using multiple query variations.

    Input: query_variations (or processed_query/query as fallback)
    Output: retrieved_chunks, retrieval_scores
    """
    # Get all queries to search with
    query_variations = state.get("query_variations", [])
    original_query = state.get("processed_query") or state.get("query", "")

    # Always include original query
    all_queries = [original_query] + query_variations if query_variations else [original_query]

    print(f"[vector_search] Multi-query search with {len(all_queries)} queries:")
    for i, q in enumerate(all_queries):
        print(f"  {i+1}. {q[:80]}{'...' if len(q) > 80 else ''}")

    # Generate embeddings for all queries in batch
    print(f"[vector_search] Generating {len(all_queries)} embeddings...")
    query_embeddings = call_openai_embedding_batch(all_queries)

    # Search Pinecone with each embedding
    index = get_pinecone_index()
    all_matches = {}  # id -> chunk_data (deduplication)

    for i, embedding in enumerate(query_embeddings):
        results = index.query(
            vector=embedding,
            top_k=DEFAULT_TOP_K,
            include_metadata=True
        )

        for match in results.matches:
            if match.score >= SIMILARITY_THRESHOLD:
                chunk_id = match.id

                # Keep highest score if duplicate
                if chunk_id not in all_matches or match.score > all_matches[chunk_id]["score"]:
                    all_matches[chunk_id] = {
                        "id": chunk_id,
                        "score": match.score,
                        "metadata": match.metadata,
                        "matched_query_idx": i  # Track which query found this
                    }

    # Sort by score descending
    retrieved_chunks = sorted(all_matches.values(), key=lambda x: x["score"], reverse=True)
    retrieval_scores = [chunk["score"] for chunk in retrieved_chunks]

    print(f"[vector_search] Retrieved {len(retrieved_chunks)} unique chunks (from {len(all_queries)} queries)")

    # Determine if refinement needed
    needs_refinement = len(retrieved_chunks) < 3

    return {
        **state,
        "retrieved_chunks": retrieved_chunks,
        "retrieval_scores": retrieval_scores,
        "needs_refinement": needs_refinement,
        "iteration_count": state.get("iteration_count", 0) + 1
    }


def search_single_query(query_text: str) -> list:
    """
    Simple single-query search (utility function).

    Returns list of chunk dicts with id, score, metadata.
    """
    print(f"[vector_search] Single search: {query_text[:100]}...")

    embedding = call_openai_embedding(query_text)
    index = get_pinecone_index()

    results = index.query(
        vector=embedding,
        top_k=DEFAULT_TOP_K,
        include_metadata=True
    )

    chunks = []
    for match in results.matches:
        if match.score >= SIMILARITY_THRESHOLD:
            chunks.append({
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata
            })

    print(f"[vector_search] Retrieved {len(chunks)} chunks")
    return chunks
