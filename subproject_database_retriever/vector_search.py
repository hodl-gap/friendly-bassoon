"""
Vector Search Module

Performs semantic search in Pinecone vector database.
Supports multi-query retrieval using query variations.
Implements two-stage retrieval: broad recall + LLM re-ranking for causal relevance.
"""

import sys
import re
import json
import os
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from pinecone import Pinecone
from anthropic import Anthropic
from models import call_openai_embedding, call_openai_embedding_batch, call_claude_haiku
from states import RetrieverState
from config import (
    PINECONE_API_KEY, PINECONE_INDEX_NAME, DEFAULT_TOP_K, SIMILARITY_THRESHOLD,
    ENABLE_LLM_RERANK, BROAD_RETRIEVAL_TOP_K, BROAD_SIMILARITY_THRESHOLD, RERANK_TOP_K,
    ORIGINAL_QUERY_TOP_N, USE_STRUCTURED_RERANK,
    FOLLOWUP_TOP_K, FOLLOWUP_THRESHOLD
)
from vector_search_prompts import RE_RANK_PROMPT, RE_RANK_SYSTEM_PROMPT

# Initialize Anthropic client for structured output
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)
_anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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
    Hybrid two-stage retrieval: preserves original query's top results + adds expanded query breadth.

    Stage 1A: Get top-N from ORIGINAL query (protected - always included)
    Stage 1B: Add expanded query results for breadth (max-score merge, skip protected)
    Stage 2: LLM re-ranking to score causal relevance (if ENABLE_LLM_RERANK)

    Input: query_variations (or processed_query/query as fallback)
    Output: retrieved_chunks, retrieval_scores
    """
    # Get all queries to search with
    query_variations = state.get("query_variations", [])
    original_query = state.get("processed_query") or state.get("query", "")

    # Always include original query first
    all_queries = [original_query] + query_variations if query_variations else [original_query]

    print(f"[vector_search] Hybrid retrieval with {len(all_queries)} queries:")
    for i, q in enumerate(all_queries):
        print(f"  {i+1}. {q[:80]}{'...' if len(q) > 80 else ''}")

    # Generate embeddings for all queries in batch
    print(f"[vector_search] Generating {len(all_queries)} embeddings...")
    query_embeddings = call_openai_embedding_batch(all_queries)

    index = get_pinecone_index()
    all_matches = {}  # id -> chunk_data (deduplication)
    protected_ids = set()  # IDs protected from being overwritten

    # Use broader threshold and higher top_k for Stage 1
    stage1_threshold = BROAD_SIMILARITY_THRESHOLD if ENABLE_LLM_RERANK else SIMILARITY_THRESHOLD
    stage1_top_k = BROAD_RETRIEVAL_TOP_K if ENABLE_LLM_RERANK else DEFAULT_TOP_K

    # Stage 1A: Get top-N from ORIGINAL query first (protected)
    original_embedding = query_embeddings[0]
    original_results = index.query(
        vector=original_embedding,
        top_k=stage1_top_k,
        include_metadata=True
    )

    protected_count = 0
    for match in original_results.matches:
        if match.score >= stage1_threshold and protected_count < ORIGINAL_QUERY_TOP_N:
            chunk_id = match.id
            protected_ids.add(chunk_id)
            all_matches[chunk_id] = {
                "id": chunk_id,
                "score": match.score,
                "metadata": match.metadata,
                "matched_query_idx": 0,
                "is_original_top": True  # Flag for debugging
            }
            protected_count += 1

    print(f"[vector_search] Stage 1A: Protected {len(protected_ids)} chunks from original query")

    # Stage 1B: Add expanded query results (skip protected chunks)
    for i, embedding in enumerate(query_embeddings):
        results = index.query(
            vector=embedding,
            top_k=stage1_top_k,
            include_metadata=True
        )

        for match in results.matches:
            if match.score >= stage1_threshold:
                chunk_id = match.id

                # Protected chunks keep their original score - don't overwrite
                if chunk_id in protected_ids:
                    continue

                # Non-protected: max-score wins (existing behavior)
                if chunk_id not in all_matches or match.score > all_matches[chunk_id]["score"]:
                    all_matches[chunk_id] = {
                        "id": chunk_id,
                        "score": match.score,
                        "metadata": match.metadata,
                        "matched_query_idx": i,
                        "is_original_top": False
                    }

    # Sort by semantic score
    candidates = sorted(all_matches.values(), key=lambda x: x["score"], reverse=True)

    print(f"[vector_search] Stage 1B: {len(candidates)} total candidates above {stage1_threshold}")

    # Stage 2: LLM re-ranking (if enabled and enough candidates)
    if ENABLE_LLM_RERANK and len(candidates) > RERANK_TOP_K:
        print(f"[vector_search] Stage 2: LLM re-ranking {len(candidates)} candidates...")
        candidates = rerank_with_llm(original_query, candidates)
        retrieved_chunks = candidates[:RERANK_TOP_K]
    else:
        # No re-ranking - just take top results
        retrieved_chunks = candidates[:DEFAULT_TOP_K]

    retrieval_scores = [chunk.get("rerank_score", chunk["score"]) for chunk in retrieved_chunks]

    # Log how many protected chunks made it to final results
    final_protected = sum(1 for c in retrieved_chunks if c.get("is_original_top", False))
    print(f"[vector_search] Final: {len(retrieved_chunks)} chunks ({final_protected} from original query)")

    # Determine if refinement needed
    needs_refinement = len(retrieved_chunks) < 3

    return {
        **state,
        "retrieved_chunks": retrieved_chunks,
        "retrieval_scores": retrieval_scores,
        "needs_refinement": needs_refinement,
        "iteration_count": state.get("iteration_count", 0) + 1
    }


def rerank_with_llm(query: str, candidates: list) -> list:
    """
    Stage 2: Re-rank candidates using LLM causal relevance scoring.

    Uses Claude Haiku to score each chunk for causal relevance to the query.
    Uses structured output (tool_use) for reliable JSON parsing when enabled.
    Returns candidates sorted by rerank_score (highest first).
    """
    # Format chunks for the prompt
    chunks_text = format_chunks_for_rerank(candidates)
    chunk_ids = [c["id"] for c in candidates]

    if USE_STRUCTURED_RERANK:
        # Use structured output with tool_use for guaranteed valid JSON
        scores = rerank_with_structured_output(query, chunks_text, chunk_ids)
    else:
        # Legacy: free-form JSON parsing (less reliable)
        prompt = RE_RANK_PROMPT.format(query=query, chunks=chunks_text)
        messages = [{"role": "user", "content": prompt}]
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=5000)
        print(f"[vector_search] Re-rank LLM response:\n{response}")
        scores = parse_rerank_response(response)

    # Merge scores with candidates
    for candidate in candidates:
        chunk_id = candidate["id"]
        # Use rerank score if available, else default to 0.5
        candidate["rerank_score"] = scores.get(chunk_id, 0.5)

    # Sort by rerank_score descending
    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

    print(f"[vector_search] Stage 2 complete: re-ranked {len(candidates)} chunks")

    return candidates


def rerank_with_structured_output(query: str, chunks_text: str, chunk_ids: list) -> dict:
    """
    Re-rank using Claude's tool_use for guaranteed structured output.

    Returns dict of {chunk_id: score}
    """
    # Define the tool schema for structured output
    rerank_tool = {
        "name": "submit_rerank_scores",
        "description": "Submit relevance scores for each chunk. Score 0.0-1.0 based on causal relevance to the query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "array",
                    "description": "Array of chunk scores",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chunk_id": {
                                "type": "string",
                                "description": "The chunk ID being scored"
                            },
                            "relevance_score": {
                                "type": "number",
                                "description": "Causal relevance score 0.0-1.0"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Brief explanation for the score"
                            }
                        },
                        "required": ["chunk_id", "relevance_score"]
                    }
                }
            },
            "required": ["scores"]
        }
    }

    user_prompt = f"""Score each chunk for CAUSAL RELEVANCE to this query.

**Query:** {query}

**Scoring Guidelines (0.0-1.0):**
- 0.9-1.0: Directly answers query with explicit causal logic (cause → effect → mechanism)
- 0.7-0.8: Contains relevant causal mechanisms or specific thresholds
- 0.5-0.6: Conceptually related but no direct causal link
- 0.3-0.4: Tangentially related, surface-level overlap only
- 0.0-0.2: Off-topic despite keyword match

**Be STRICT:** High scores ONLY for chunks with actual causal reasoning.

**Chunks to evaluate:**
{chunks_text}

Use the submit_rerank_scores tool to submit your scores for ALL chunks."""

    try:
        response = _anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            temperature=0.0,
            system=RE_RANK_SYSTEM_PROMPT,
            tools=[rerank_tool],
            tool_choice={"type": "tool", "name": "submit_rerank_scores"},
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Extract tool use result
        scores = {}
        for content_block in response.content:
            if content_block.type == "tool_use" and content_block.name == "submit_rerank_scores":
                tool_input = content_block.input
                for item in tool_input.get("scores", []):
                    chunk_id = item.get("chunk_id", "")
                    score = item.get("relevance_score", 0.5)
                    scores[chunk_id] = float(score)

                print(f"[vector_search] Structured re-rank: parsed {len(scores)} scores")
                return scores

        print(f"[vector_search] WARNING: No tool_use found in response, using fallback")
        return {}

    except Exception as e:
        print(f"[vector_search] WARNING: Structured re-rank failed ({e}), using fallback")
        return {}


def format_chunks_for_rerank(candidates: list) -> str:
    """Format chunks for the re-ranking prompt."""
    chunks_text = ""
    for i, chunk in enumerate(candidates):
        chunk_id = chunk["id"]
        metadata = chunk.get("metadata", {})

        # Extract key information for re-ranking
        source = metadata.get("source", metadata.get("tg_channel", "unknown"))
        what_happened = metadata.get("what_happened", "")
        interpretation = metadata.get("interpretation", "")

        # Try to get extracted_data for logic chains
        extracted_data = metadata.get("extracted_data", "{}")
        if isinstance(extracted_data, str):
            try:
                extracted_data = json.loads(extracted_data)
            except json.JSONDecodeError:
                extracted_data = {}

        logic_chains = extracted_data.get("logic_chains", [])
        logic_summary = ""
        if logic_chains:
            for chain in logic_chains[:2]:  # Limit to first 2 chains
                steps = chain.get("steps", [])
                if steps:
                    chain_str = " → ".join([f"{s.get('cause', '')} → {s.get('effect', '')}" for s in steps[:3]])
                    logic_summary += f"Chain: {chain_str}; "

        chunks_text += f"""
---
**Chunk ID:** {chunk_id}
**Source:** {source}
**What happened:** {what_happened}
**Interpretation:** {interpretation}
**Logic chains:** {logic_summary if logic_summary else 'None extracted'}
**Semantic score:** {chunk['score']:.3f}
"""

    return chunks_text


def parse_rerank_response(response: str) -> dict:
    """
    Parse LLM re-ranking response to extract scores.

    Multiple parsing attempts with fallbacks:
    1. Extract from markdown code block (```json [...] ```)
    2. Find raw [ ... ]
    3. Return empty dict (will use semantic scores as fallback)
    """
    scores = {}
    json_str = None

    # Attempt 1: Extract from markdown code block
    code_block = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, re.DOTALL)
    if code_block:
        json_str = code_block.group(1)
        print(f"[vector_search] Found JSON in markdown code block")
    else:
        # Attempt 2: Find raw [ ... ]
        start_idx = response.find('[')
        end_idx = response.rfind(']') + 1
        if start_idx >= 0 and end_idx > start_idx:
            json_str = response[start_idx:end_idx]
            print(f"[vector_search] Found raw JSON array")

    if json_str is None:
        print(f"[vector_search] WARNING: No JSON array found, using semantic scores")
        return scores

    try:
        results = json.loads(json_str)

        for item in results:
            chunk_id = item.get("chunk_id", "")
            score = item.get("relevance_score", 0.5)
            scores[chunk_id] = float(score)

        print(f"[vector_search] Parsed {len(scores)} re-rank scores")

    except json.JSONDecodeError as e:
        print(f"[vector_search] WARNING: JSON parse failed ({e}), using semantic scores")
    except Exception as e:
        print(f"[vector_search] WARNING: Re-rank parsing error ({e}), using semantic scores")

    return scores


def search_single_query(
    query_text: str,
    top_k: int = None,
    threshold: float = None
) -> list:
    """
    Simple single-query search for follow-up retrievals.
    No re-ranking, no query expansion - just semantic search.

    Args:
        query_text: The search query
        top_k: Number of results (default: FOLLOWUP_TOP_K)
        threshold: Similarity threshold (default: FOLLOWUP_THRESHOLD)

    Returns: List of chunks with id, score, metadata
    """
    top_k = top_k or FOLLOWUP_TOP_K
    threshold = threshold or FOLLOWUP_THRESHOLD

    print(f"[vector_search] Single query: '{query_text[:80]}...' (top_k={top_k}, threshold={threshold})")

    embedding = call_openai_embedding(query_text)
    index = get_pinecone_index()

    results = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True
    )

    chunks = []
    for match in results.matches:
        if match.score >= threshold:
            chunks.append({
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata
            })

    print(f"[vector_search] Single query retrieved {len(chunks)} chunks")
    return chunks


def search_by_cause_normalized(
    cause_norm: str,
    top_k: int = 5
) -> list:
    """
    Search for chunks where a specific cause_normalized appears.

    Uses Pinecone metadata filtering for deterministic (symbolic) match
    instead of semantic search. This is more reliable for chain expansion
    when we know the exact normalized variable name.

    Args:
        cause_norm: Normalized cause variable name (e.g., "carry_unwind", "bank_reserves")
        top_k: Maximum results to return

    Returns:
        List of chunks with id, score, metadata, and match_type="metadata"

    Note:
        Requires cause_normalized to be indexed in Pinecone metadata.
        If not indexed, returns empty list and falls back to semantic search.
    """
    print(f"[vector_search] Metadata search for cause_normalized='{cause_norm}'")

    try:
        index = get_pinecone_index()

        # Query with metadata filter
        # Note: This requires cause_normalized to be indexed in Pinecone
        # Pinecone filter syntax: {"field": {"$eq": "value"}}
        results = index.query(
            vector=[0.0] * 3072,  # Dummy vector (metadata-only query)
            top_k=top_k,
            include_metadata=True,
            filter={"cause_normalized": {"$eq": cause_norm}}
        )

        chunks = []
        for match in results.matches:
            chunks.append({
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata,
                "match_type": "metadata"  # Tag for downstream processing
            })

        print(f"[vector_search] Metadata search found {len(chunks)} chunks for '{cause_norm}'")
        return chunks

    except Exception as e:
        # Filter may fail if cause_normalized is not indexed
        print(f"[vector_search] Metadata filter failed ({e}), returning empty")
        return []


def search_for_chain_continuation(
    effect_norm: str,
    top_k: int = 5
) -> list:
    """
    Search for chunks where a given effect appears as a cause (chain continuation).

    First tries metadata filter (deterministic), then falls back to semantic search.
    This is the main function for chain expansion in answer_generation.py.

    Args:
        effect_norm: The effect to find as a cause in other chunks
        top_k: Maximum results to return

    Returns:
        List of chunks with match_type ("metadata" or "semantic")
    """
    # Step 1: Try deterministic metadata match first
    metadata_chunks = search_by_cause_normalized(effect_norm, top_k=top_k)

    if len(metadata_chunks) >= 2:
        # Good coverage from metadata - return these
        print(f"[vector_search] Chain continuation: {len(metadata_chunks)} metadata matches for '{effect_norm}'")
        return metadata_chunks

    # Step 2: Fall back to semantic search if insufficient metadata matches
    print(f"[vector_search] Insufficient metadata matches ({len(metadata_chunks)}), adding semantic search")

    # Build semantic query
    query = f"What is the impact of {effect_norm.replace('_', ' ')}?"
    semantic_chunks = search_single_query(query, top_k=top_k)

    # Tag semantic chunks
    for chunk in semantic_chunks:
        chunk["match_type"] = "semantic"

    # Merge: metadata first, then semantic (deduplicated)
    seen_ids = {c["id"] for c in metadata_chunks}
    merged = list(metadata_chunks)

    for chunk in semantic_chunks:
        if chunk["id"] not in seen_ids:
            merged.append(chunk)
            seen_ids.add(chunk["id"])

    print(f"[vector_search] Chain continuation total: {len(merged)} chunks ({len(metadata_chunks)} metadata + {len(merged) - len(metadata_chunks)} semantic)")
    return merged[:top_k]
