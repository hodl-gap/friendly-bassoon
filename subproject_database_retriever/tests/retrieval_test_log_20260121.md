# Retrieval Test Log - 2026-01-21

## Test Environment

- **Date**: 2026-01-21
- **Index**: research-papers (Pinecone)
- **Vectors**: 301 (from 3 channels: Fomo CTRINE, Plan G Research, Macro Trend Hyott)
- **Embedding Model**: text-embedding-3-large (3072 dim)
- **Re-ranking**: Claude Haiku (ENABLE_LLM_RERANK=True)

---

## Query 1: Liquidity Expansion Predictors

### Input
```
what features predict liquidity expansion in 2026?
```

### Query Processing
- **Classification**: research_question
- **Expansion**: 6 dimension queries generated

| Dimension | Expanded Query |
|-----------|---------------|
| Leading Economic Indicators | economic growth forecasts 2026 inflation expectations Fed policy |
| Central Bank Balance Sheet | Fed balance sheet expansion 2026 quantitative easing asset purchases |
| Interest Rate Environment | interest rate cuts 2026 Fed funds rate forecast monetary easing |
| Credit Market Stress | credit spreads 2026 financial stability risks liquidity conditions |
| Historical Policy Precedents | liquidity expansion cycles Fed policy history recession indicators |
| Money Supply and Reserve Demand | M2 money supply growth 2026 bank reserves monetary aggregates |

### Retrieval Results

**Stage 1**: 64 candidates above 0.40 threshold

**Final Retrieved Chunks (10)**:

| # | Chunk ID | Score | Channel | Content Summary |
|---|----------|-------|---------|-----------------|
| 1 | `42ae63883a10996e_63` | 0.678 | Fomo CTRINE | CME FedWatch: 60.7% prob rates 325-350 bps through Apr 2026 |
| 2 | `bf0d33f059ca7b94_133` | 0.675 | Fomo CTRINE | Fed vs Market divergence: market expects 1-2 additional cuts |
| 3 | `2e3908524b6cea7d_165` | 0.632 | Fomo CTRINE | 83.4% prob Fed holds at 350-375 bps in Jan 2026 |
| 4 | `2799bf974e4a06f1_123` | 0.618 | Fomo CTRINE | Unemployment 3.2% Nov 2025 |
| 5 | `2fa948af8e99299d_36` | 0.602 | Fomo CTRINE | Productivity + Fed cuts + fiscal stimulus → GDP rebound |
| 6 | `95958f942da07473_132` | 0.597 | Fomo CTRINE | Fed views 2026 cuts nearly complete |
| 7 | `4acec76b9da5d0e9_79` | 0.621 | Fomo CTRINE | Goldman: unemployment 4.5%, GDP 2.8% |
| 8 | `05304d9ce7505ba0_13` | 0.608 | Fomo CTRINE | Fed $55.36B Treasury purchases over 3 weeks |
| 9 | `026ca73779873fff_61` | 0.578 | Plan G Research | "Expects ~150bp cuts in 2026" |
| 10 | `1030057603c430a9_78` | 0.576 | Fomo CTRINE | Goldman unemployment forecast |

### Synthesis Results

**Consensus Conclusions**:
1. Significant liquidity expansion in 2026 (~$1.26-2T) - Confidence: 0.85 (High)
2. Accommodative financial conditions maintained - Confidence: 0.80 (High)
3. Equities rally supported - Confidence: 0.70 (Medium)
4. Gradual rate reduction H2 2026 - Confidence: 0.65 (Medium)

**Contradictions Identified**: 7

| # | Contradiction | Impact |
|---|---------------|--------|
| 1 | Market vs Fed on rate cuts | High |
| 2 | Balance sheet expanding vs "constrained liquidity" | High |
| 3 | 2019 precedent may not apply | Medium |
| 4 | VIX positioning self-defeating | Medium |
| 5 | Seasonal volatility lacks recent validation | Medium |
| 6 | $2T money supply target lacks Fed commitment | Medium |
| 7 | Internal inconsistency in conclusions | High |

---

## Query 2: BTC Price Up Signals

*(Analysis deferred - focusing on Query 1 fix first)*

### Input
```
what data suggest BTC price up
```

### Query Processing
- **Classification**: data_lookup
- **Expansion**: 6 dimension queries generated
- **Stage 1 Candidates**: 66 chunks above 0.40 threshold
- **Final Retrieved**: 10 chunks

### Quick Notes
- Re-ranking worked (unlike Q1) but made questionable filtering decisions
- Critical miss: `96735a924bf6eb2e_130` (120% institutional buying) - Stage 1 rank #8
- 5 of top 10 Stage 1 candidates were NOT retrieved
- Full analysis pending after Q1 fix

---

## Critical Issue Discovered: Missing Highly Relevant Chunk (Query 1)

### The Missing Chunk

**Chunk ID**: `89ce3018db941935_32`

**Raw Text** (Korean):
```
모든 징후는 2026년에 유동성 공급 물결이 일어날 것임을 시사합니다.
머니펀드 규모 확대, 은행 신용 견고, 그리고 연준의 월 400억 달러 규모의 국채 매입이 그 원인입니다.
```

**Translation**:
> All signs suggest a liquidity supply wave in 2026. Money fund expansion, robust bank credit, and the Fed's $40 billion monthly Treasury purchases are the causes.

**This is THE most directly relevant chunk for Query 1.**

### Score Analysis

| Query | Target Chunk Rank | Score |
|-------|-------------------|-------|
| Original query alone | **#1** | 0.5648 |
| "Fed balance sheet expansion 2026..." | #5 | 0.5344 |
| "liquidity expansion cycles..." | **#1** | 0.5573 |
| "M2 money supply growth 2026..." | #3 | 0.4851 |
| **After merging all 7 queries** | **#10** | 0.5648 |

### Root Cause Analysis

#### Issue 1: Query Expansion Diluted Results

When the original query was expanded into 7 queries and results merged:

| Stage 1 Rank | Chunk ID | Score | In Final Results? |
|--------------|----------|-------|-------------------|
| #1 | `8192094ddce93f69_177` | 0.6847 | ❌ NO |
| #2 | `2c291ad4832d8498_176` | 0.6601 | ❌ NO |
| #8 | `6ee573ba75d4d074_33` | 0.5942 | ❌ NO |
| #10 | `89ce3018db941935_32` (TARGET) | 0.5648 | ❌ NO |

The expanded queries surfaced different chunks that scored higher on specific dimensions, pushing the most holistically relevant chunk from #1 → #10.

#### Issue 2: LLM Re-Ranking JSON Parsing Failed

```
[vector_search] WARNING: Could not find JSON array in re-rank response
```

When JSON parsing fails:
- All chunks get default score 0.5
- Original Stage 1 order is preserved
- But Stage 1 order was already diluted by query expansion

#### Issue 3: Re-Ranking Non-Determinism

Multiple runs produce different orderings because:
- LLM re-ranking is stochastic (temperature > 0)
- JSON parsing success/failure varies
- Different chunks surface in different runs

---

## Recommendations for Investigation

### 1. Query Expansion Strategy
- Consider weighting original query higher than expanded queries
- Or: Run original query separately and ensure top-k from original are always included
- Or: Use reciprocal rank fusion instead of max-score deduplication

### 2. Re-Ranking Robustness
- Fix JSON parsing to be more resilient (handle partial JSON, markdown code blocks, etc.)
- Add fallback: if parsing fails, use semantic scores directly
- Consider structured output (tool use) instead of free-form JSON

### 3. Retrieval Threshold
- Current: BROAD_SIMILARITY_THRESHOLD = 0.40
- The target chunk scored 0.5648 - well above threshold
- Issue is not threshold but result merging strategy

### 4. Hybrid Approach
- Always include top-N from original query regardless of expanded query scores
- Then add top-M from expanded queries for breadth
- Re-rank the combined set

---

## Test Artifacts

### Files Referenced
- Processed CSVs: `data/processed/processed_*_2026-01-20.csv`
- Vector DB: Pinecone `research-papers` index (301 vectors)

### Config Used
```python
ENABLE_LLM_RERANK = True
BROAD_RETRIEVAL_TOP_K = 20
BROAD_SIMILARITY_THRESHOLD = 0.40
RERANK_TOP_K = 10
```

---

## Design Gap: Temporal Validity of Extracted Data

### Problem

The current extraction system stores `what_happened` and `logic_chains` but does **NOT** distinguish between:

| Data Type | Example | Temporal Validity | Current Handling |
|-----------|---------|-------------------|------------------|
| Absolute values | "$1.26T QE in 2026" | Stale after 2026 | ❌ No distinction |
| Point-in-time expectations | "83.4% prob no Jan cut" | Expired after Jan 2026 | ❌ No distinction |
| Relative deltas | "Fed BS +$105B" | Context-dependent | ❌ No distinction |
| Structural relationships | "QE → risk asset support" | Timeless pattern | ❌ No distinction |

### Consequence

If a user queries "what features predict liquidity expansion in 2035?":
- System returns 2026-specific data ($1.26T, 83.4%, etc.)
- These absolute values are obsolete
- But the underlying **relationships** (Fed BS expansion → liquidity) may still be valid

### Current State

The extraction schema has:
```python
"temporal_context": {
    "valid_from": "2026-01",
    "valid_until": null,
    "is_forward_looking": true
}
```

But this is **not used** in:
1. Retrieval filtering (no date-aware search)
2. Answer generation (no staleness warning)
3. Logic chain extraction (absolute vs relative not separated)

### Potential Solutions

1. **Separate relationship from values**: Extract "Fed BS expansion → liquidity up" as a pattern, with specific values as time-stamped instances

2. **Date-aware retrieval**: Filter chunks by `valid_from`/`valid_until` based on query timeframe

3. **Staleness warning**: If query timeframe differs from data timeframe, flag in response

4. **Relative metric extraction**: Store "Fed BS +20%" alongside "$105B" to preserve relative meaning

---

## Clarification: Output Sources

All synthesis outputs are **model outputs** from the retrieval system, not Claude Code assessments:

| Output | Source | Stage |
|--------|--------|-------|
| Logic Chains | `answer_generation.py` Stage 1 | LLM extracts from chunks |
| Synthesis/Consensus | `answer_generation.py` Stage 2 | LLM synthesizes paths |
| Contradictions | `answer_generation.py` Stage 3 | LLM identifies conflicts |

Claude Code only formatted/displayed these outputs.

---

## Next Steps (Query 1 Focus)

1. Review query expansion logic in `query_processing.py`
2. Fix JSON parsing in `vector_search.py:parse_rerank_response()`
3. Consider hybrid retrieval strategy (guarantee original query's top-N)
4. Re-test with fixes applied
5. Evaluate if synthesis quality improves with correct chunks
6. Design temporal validity handling for extracted data

---

*Log created: 2026-01-21*
