"""
Prompts for Vector Search Module

Contains prompts for:
- LLM re-ranking (causal relevance scoring)
"""

# System prompt for structured re-ranking (used with tool_use)
RE_RANK_SYSTEM_PROMPT = """You are evaluating financial research context for CAUSAL RELEVANCE.
Your job is to score how well each chunk helps answer the query with actual causal reasoning (A → B relationships).
Be STRICT: high scores ONLY for chunks with explicit causal logic relevant to the query.
"Mentions the same topic" is NOT enough for a high score."""

# Re-ranking prompt for two-stage retrieval (legacy free-form JSON)
# Stage 2: Score retrieved chunks for CAUSAL relevance to the query
RE_RANK_PROMPT = """You are evaluating retrieved financial research context for CAUSAL RELEVANCE to a query.

Your job is to score how well each chunk helps answer the query with actual causal reasoning (A → B relationships), not just surface-level keyword matches.

**Query:** {query}

**Scoring Guidelines (0.0-1.0):**
- **0.9-1.0**: Directly answers the query with explicit causal logic (cause → effect → mechanism)
- **0.7-0.8**: Contains relevant causal mechanisms or specific thresholds related to query
- **0.5-0.6**: Conceptually related topic but no direct causal link to query
- **0.3-0.4**: Tangentially related, only surface-level word overlap
- **0.0-0.2**: Off-topic or irrelevant despite keyword match

**Be STRICT:**
- High scores ONLY for chunks with actual causal reasoning relevant to the query
- "Mentions the same topic" is NOT enough for a high score
- Chunks that just use similar words but discuss unrelated mechanisms should score LOW

**Chunks to evaluate:**
{chunks}

**Output JSON array with scores:**
```json
[
  {{"chunk_id": "chunk_1", "relevance_score": 0.85, "reasoning": "Contains direct causal chain: TGA down → reserves up → funding eases"}},
  {{"chunk_id": "chunk_2", "relevance_score": 0.45, "reasoning": "Mentions liquidity but no causal link to query topic"}},
  ...
]
```

Return ONLY the JSON array, nothing else."""
