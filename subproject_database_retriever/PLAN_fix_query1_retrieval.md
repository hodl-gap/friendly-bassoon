# Plan: Fix Query 1 Retrieval Issues

## Problem Summary

Query 1 (`"what features predict liquidity expansion in 2026?"`) missed the most relevant chunk (`89ce3018db941935_32` - "2026 liquidity supply wave") despite it ranking **#1** for the original query with score 0.5648.

## Root Cause Analysis

### Issue 1: Merge Strategy Dilutes Original Query's Best Matches

**Important clarification:** The query expansion itself is working correctly. It captures nuances:
- "liquidity expansion" → "rate cuts", "Fed balance sheet", "M2 money supply"
- These are semantically related but use different vocabulary

**The problem is the MERGE strategy, not expansion quality.**

**Location:** `vector_search.py` lines 71-89

**Current behavior:**
```python
for i, embedding in enumerate(query_embeddings):
    # All 7 queries (1 original + 6 expanded) treated equally
    for match in results.matches:
        if chunk_id not in all_matches or match.score > all_matches[chunk_id]["score"]:
            all_matches[chunk_id] = {...}  # Max-score wins
```

**Problem:**
- Original query: target chunk = #1 (0.5648) - PERFECT holistic match
- Expanded queries surface dimension-specific chunks (GDP, unemployment) that score higher on narrow terms
- Max-score merge treats all queries equally, so narrow-topic chunks overtake holistic match
- After merging 7 queries: target chunk drops to #10

**Evidence from test log:**
| Query | Target Chunk Rank | Score |
|-------|-------------------|-------|
| Original query alone | **#1** | 0.5648 |
| After merging all 7 | **#10** | 0.5648 |

**Key insight:** Expansion adds valuable breadth. The fix should preserve original query's holistic relevance while ADDING expanded query breadth, not REPLACING it.

### Issue 2: LLM Re-Ranking JSON Parsing Fragile

**Location:** `vector_search.py` lines 197-225 (`parse_rerank_response`)

**Current behavior:**
```python
start_idx = response.find('[')
end_idx = response.rfind(']') + 1
json_str = response[start_idx:end_idx]
results = json.loads(json_str)
```

**Problem:**
- Fails when LLM adds markdown code blocks: ` ```json [...] ``` `
- Fails when JSON is truncated (max_tokens=3000 may cut it off)
- On failure: all chunks get default score 0.5, order becomes random

**Evidence:** `[vector_search] WARNING: Could not find JSON array in re-rank response`

### Issue 3: Re-Ranking Non-Determinism

**Location:** `vector_search.py` line 134

**Current:** `temperature=0.1` - allows stochastic variation
**Impact:** Different runs produce different results

---

## Proposed Fixes

### Fix 1: Hybrid Retrieval - Guarantee Original Query's Top-N

**Strategy:** Always preserve top-5 chunks from the original query, then ADD expanded query results for breadth.

**Key principle:** Expansion is valuable (captures nuances), but original query captures holistic relevance. Both should contribute.

**Changes to `vector_search.py` (lines 63-92):**

```python
def search_vectors(state: RetrieverState) -> RetrieverState:
    # ... existing setup ...

    ORIGINAL_QUERY_TOP_N = 5  # Guaranteed slots for original query

    # Stage 1A: Get top-N from ORIGINAL query first (protected)
    original_embedding = query_embeddings[0]
    original_results = index.query(vector=original_embedding, top_k=stage1_top_k, include_metadata=True)

    protected_ids = set()
    for match in original_results.matches[:ORIGINAL_QUERY_TOP_N]:
        if match.score >= stage1_threshold:
            protected_ids.add(match.id)
            all_matches[match.id] = {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata,
                "matched_query_idx": 0,
                "is_original_top": True  # Flag for debugging
            }

    # Stage 1B: Add expanded query results (existing merge logic)
    for i, embedding in enumerate(query_embeddings):
        results = index.query(vector=embedding, top_k=stage1_top_k, include_metadata=True)
        for match in results.matches:
            if match.score >= stage1_threshold:
                chunk_id = match.id
                # Protected chunks keep their original score
                if chunk_id in protected_ids:
                    continue
                # Non-protected: max-score wins (existing behavior)
                if chunk_id not in all_matches or match.score > all_matches[chunk_id]["score"]:
                    all_matches[chunk_id] = {...}

    # Stage 1 output: protected chunks + best from expanded queries
```

**Result:**
- Top 5 from original query: ALWAYS included (holistic relevance)
- Remaining 5 slots: Best from expanded queries (nuance breadth)
- Re-ranking then scores all 10+ for causal relevance

### Fix 2: Robust JSON Parsing

**Strategy:** Multiple parsing attempts with fallbacks.

**Changes to `parse_rerank_response`:**

```python
def parse_rerank_response(response: str) -> dict:
    scores = {}

    # Attempt 1: Extract from markdown code block
    import re
    code_block = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, re.DOTALL)
    if code_block:
        json_str = code_block.group(1)
    else:
        # Attempt 2: Find raw [ ... ]
        start_idx = response.find('[')
        end_idx = response.rfind(']') + 1
        if start_idx >= 0 and end_idx > start_idx:
            json_str = response[start_idx:end_idx]
        else:
            # Attempt 3: Parse line-by-line for chunk_id: score patterns
            # ... fallback regex parsing ...
            return scores  # Empty = use semantic scores

    try:
        results = json.loads(json_str)
        # ... existing score extraction ...
    except json.JSONDecodeError:
        # Fallback: return empty, will use semantic scores
        print("[vector_search] WARNING: JSON parse failed, using semantic scores")

    return scores
```

### Fix 3: Deterministic Re-Ranking

**Change:** `temperature=0.1` → `temperature=0.0`

**Location:** `vector_search.py` line 134

---

## Files to Modify

| File | Changes |
|------|---------|
| `vector_search.py` | Hybrid retrieval logic, robust JSON parsing, temperature fix |
| `config.py` | Add `ORIGINAL_QUERY_TOP_N = 5` constant |

## Implementation Order

1. **Fix 3** (trivial): Change temperature to 0.0
2. **Fix 2** (moderate): Improve JSON parsing robustness
3. **Fix 1** (core fix): Implement hybrid retrieval

## Testing

After implementation:
1. Re-run Query 1: `"what features predict liquidity expansion in 2026?"`
2. Verify target chunk `89ce3018db941935_32` is in final results
3. Check synthesis quality improvement

---

## User Decisions

- **ORIGINAL_QUERY_TOP_N**: 5 slots guaranteed for original query
- **JSON parse fallback**: Use semantic scores (no retry)

---

## Out of Scope (Future Fix)

**Temporal Validity Handling** - Deferred to separate fix:
- System doesn't distinguish absolute values ($1.26T QE) from structural relationships (QE → liquidity)
- `temporal_context` fields exist in extraction schema but unused in retrieval/generation
- Requires changes to both database_manager and database_retriever
- Will address after retrieval merge strategy is fixed
