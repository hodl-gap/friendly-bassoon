# Database Retriever - Status

**IMPORTANT**: Read `CLAUDE.md` first for project guidelines and patterns.

**Last Updated**: 2026-01-23

## Current State: Hybrid Retrieval + Temporal Awareness + Cross-Chunk Chain Linkage + Optimizations

### Completed
- [x] Project structure set up
- [x] `states.py` - LangGraph state definitions
- [x] `config.py` - Configuration management (loads .env from parent)
- [x] `retrieval_orchestrator.py` - Main orchestrator with LangGraph workflow
- [x] `vector_search.py` - Pinecone semantic search module
- [x] `query_processing.py` - Query classification and expansion
- [x] `answer_generation.py` - Context synthesis and answer generation
- [x] Prompt files (`*_prompts.py`) for each module
- [x] `utils/` and `tests/` directories

### Query Processing Features
- **Query classification**: Classifies as `research_question` or `data_lookup`
- **Flexible dimension-based expansion**: LLM generates 4-6 query variations from different angles
- **Concrete terminology**: Prompts tuned to use market terms (equities, stocks, rate cuts) not academic jargon
- **Debugging output**: Each query includes dimension name and reasoning

### Workflow
```
query → process_query → search → [refine loop if needed] → generate → answer
```

### Files
```
subproject_database_retriever/
├── retrieval_orchestrator.py    # Main LangGraph workflow
├── query_processing.py          # Query classification + expansion
├── query_processing_prompts.py  # Prompts for query processing
├── vector_search.py             # Pinecone semantic search
├── vector_search_prompts.py     # (placeholder)
├── answer_generation.py         # Context synthesis + answer gen
├── answer_generation_prompts.py # Prompts for answer generation
├── states.py                    # LangGraph state definitions
├── config.py                    # Configuration
├── utils/
├── tests/
├── CLAUDE.md                    # Project documentation
└── STATUS.md                    # This file
```

### Not Yet Implemented
- [ ] Query refinement logic (currently just returns original)
- [ ] Query type distinction handling (research_question vs data_lookup classified but not used differently)

### Recently Completed
- [x] Multi-query retrieval - searches with original + all dimension queries, deduplicates by chunk ID
- [x] Logic chain extraction - answer generation now extracts `logic_chains` and connects chains
- [x] Full context synthesis - includes what_happened, interpretation, used_data, and logic chains
- [x] End-to-end workflow tested and working
- [x] **Confidence metadata** - Numeric scoring with path_count, source_diversity (2026-01-16)
- [x] **Contradiction detection** - Stage 3 identifies evidence that weakens consensus (2026-01-16)
- [x] **Hybrid retrieval** - Guarantees original query's top-5 chunks preserved (2026-01-22)
- [x] **Temporal awareness** - LLM distinguishes logic chains from time-bound values (2026-01-22)
- [x] **Structured re-ranking** - Uses tool_use for guaranteed JSON parsing (2026-01-23)
- [x] **Conditional contradiction** - Skips Stage 3 for data_lookup or high-confidence (2026-01-23)
- [x] **Adaptive query expansion** - 2-3 dims for simple queries, 4-6 for complex (2026-01-23)

---

## Session Summary: 2026-01-23

### Optimization: LLM Efficiency Improvements

Based on evaluation report, implemented 3 high-impact optimizations.

**1. Structured Output for Re-Ranking (tool_use)**

Replaced fragile JSON regex parsing with Claude's `tool_use` for guaranteed structure.

```python
# New: tool_use with forced tool choice
rerank_tool = {"name": "submit_rerank_scores", "input_schema": {...}}
tool_choice = {"type": "tool", "name": "submit_rerank_scores"}
```

**Files updated:**
- `vector_search.py` - Added `rerank_with_structured_output()`
- `vector_search_prompts.py` - Added `RE_RANK_SYSTEM_PROMPT`
- `config.py` - Added `USE_STRUCTURED_RERANK = True`

**2. Conditional Contradiction Detection**

Stage 3 now skips for:
- `data_lookup` queries (simple factual lookups)
- High confidence syntheses (>= 0.85)

**Files updated:**
- `answer_generation.py` - Added `should_skip_contradiction_detection()`
- `config.py` - Added `SKIP_CONTRADICTION_FOR_DATA_LOOKUP`, `SKIP_CONTRADICTION_CONFIDENCE_THRESHOLD`

**Savings:** 30-50% of queries skip Stage 3 (~$0.002/query)

**3. Adaptive Query Expansion**

Detects query complexity and adjusts expansion dimensions:
- Simple (≤10 words, single concept): 2-3 dimensions
- Complex (multiple concepts, relationships): 4-6 dimensions

**Files updated:**
- `query_processing.py` - Added `is_simple_query()`, adaptive prompt selection
- `query_processing_prompts.py` - Added `QUERY_EXPANSION_PROMPT_SIMPLE`, `QUERY_EXPANSION_PROMPT_COMPLEX`
- `config.py` - Added `SIMPLE_QUERY_MAX_WORDS`, `SIMPLE_QUERY_DIMENSIONS`, `COMPLEX_QUERY_DIMENSIONS`

**Savings:** 30-50% reduction in expansion tokens for simple queries

---

## Session Summary: 2026-01-22

### Fix: Query Expansion Dilution & Retrieval Improvements

**Problem**: Query 1 (`"what features predict liquidity expansion in 2026?"`) missed the most relevant chunk despite it ranking #1 for the original query. After query expansion merge, it dropped to #10.

**Root Causes Fixed**:
1. **Merge strategy diluted results** - Max-score merge treated all queries equally
2. **JSON parsing fragile** - Failed on markdown code blocks
3. **Re-ranking non-deterministic** - temperature=0.1 allowed variation

**Fixes Implemented**:

| Fix | Change |
|-----|--------|
| Hybrid retrieval | Top-5 from original query protected, then add expanded query results |
| Robust JSON parsing | Handles markdown code blocks (` ```json `) with fallback |
| Deterministic re-ranking | temperature 0.1 → 0.0 |
| Increased max_tokens | 3000 → 5000 for re-ranking (70 chunks was truncating) |

**Configuration Added**:
- `ORIGINAL_QUERY_TOP_N = 5` - Guaranteed slots for original query's top results

**Files Updated**:
- `vector_search.py` - Hybrid retrieval logic, robust JSON parsing, temperature fix
- `config.py` - Added ORIGINAL_QUERY_TOP_N constant

### Feature: Temporal Awareness for Logic Chain Focus

**Problem**: System returns 2026-specific data ($1.26T QE, 83.4% prob) for any query, even if asking about 2035. Absolute values become stale but structural relationships remain valid.

**Solution**: LLM-aware temporal context - passes temporal information to LLM so it can reason about what's timeless vs time-bound.

**How It Works**:
1. `query_processing.py` extracts temporal reference from query (e.g., "2035" → reference_year=2035)
2. `answer_generation.py` extracts `temporal_context` from each chunk's metadata
3. Builds temporal summary: data_years, forward_looking_count, structural_count
4. Adds `## TEMPORAL GUIDANCE` section to context sent to LLM
5. If temporal mismatch detected, instructs LLM to focus on logic chains over absolute values

**LLM Now Outputs**:
- `**TEMPORAL NOTE:** Mechanism valid across periods; $1.26T scale specific to 2026 forecast context`
- `**TEMPORAL CAVEAT:** Specific magnitudes are 2025-2026 forecast context. The causal mechanisms are structural and predict liquidity expansion features across periods.`

**Files Updated**:
- `query_processing.py` - Added `extract_temporal_reference()`
- `states.py` - Added `query_temporal_reference`, `data_temporal_summary` fields
- `answer_generation.py` - Added `extract_chunk_temporal_context()`, `summarize_data_temporal_context()`, updated `synthesize_context()`
- `answer_generation_prompts.py` - Added TEMPORAL AWARENESS section to prompts

**Use Case**: Query for future year → LLM extracts timeless logic chains → User can plug in current numbers and re-run the logic.

---

## Session Summary: 2026-01-20

### Cross-Chunk Chain Linkage Fix

Fixed bug and enhanced chain connection during answer generation.

**Bug Fixed**: `answer_generation.py` was accessing wrong structure (looking for cause/effect at chain level instead of steps array).

**Enhancement**: Added explicit chain linkage using normalized variable names.

**New functions:**
- `find_chain_connections()` - Builds effect→chunk map for cross-chunk connections
- Adds "## CHAIN CONNECTIONS" section to context for LLM

**How it works:**
1. Extract `effect_normalized` from each chunk's logic chains
2. For each chunk's `cause_normalized`, check if it matches another chunk's effect
3. Generate hints: "carry_unwind connects to chunks: [chunk_1, chunk_2]"
4. LLM uses these to build multi-hop chains across sources

**Files updated:**
- `answer_generation.py` - Fixed bug + added `find_chain_connections()` + updated `synthesize_context()`
- `answer_generation_prompts.py` - Updated LOGIC_CHAIN_PROMPT with chain connection rules

---

## Session Summary: 2026-01-17

### Logic Flaw Issue 2: Two-Stage Retrieval with LLM Re-Ranking

**Problem**: Pure semantic similarity retrieval may miss causally relevant chunks (surface-level keyword matches rank high).

**Solution**: Two-stage retrieval:
- Stage 1: Broad semantic recall (top_k × 2, lower threshold 0.40)
- Stage 2: LLM re-ranks for CAUSAL relevance (not just semantic similarity)

**Re-Ranking Scoring Guidelines:**
| Score | Meaning |
|-------|---------|
| 0.9-1.0 | Directly answers query with explicit causal logic |
| 0.7-0.8 | Contains relevant causal mechanisms |
| 0.5-0.6 | Conceptually related but no direct causal link |
| 0.3-0.4 | Tangentially related, surface-level overlap |
| 0.0-0.2 | Off-topic despite keyword match |

**Configuration:**
- `ENABLE_LLM_RERANK = True` (toggle for cost control)
- `BROAD_RETRIEVAL_TOP_K = 20`
- `BROAD_SIMILARITY_THRESHOLD = 0.40`
- `RERANK_TOP_K = 10`

**Files created/updated:**
- `vector_search.py` - Added `rerank_chunks()` function
- `vector_search_prompts.py` - NEW: RERANK_PROMPT
- `config.py` - Added re-ranking configuration

---

## Session Summary: 2026-01-16

### Evaluation Response Implementation - Issues 3 & 4

Implemented enhancements from external architecture evaluation.

**Issue 3: Confidence & Consensus Scoring**

Extended existing basic confidence (High/Medium) to include numeric scores:

```json
{
  "overall_score": 0.75,
  "path_count": 3,
  "source_diversity": 2,
  "confidence_level": "High"
}
```

**Confidence guidelines:**
- High (0.8+): 3+ paths from 2+ independent sources
- Medium (0.5-0.8): 2 paths OR single source with strong logic
- Low (<0.5): Single path, weak support, or contradictory evidence

**Issue 4: Negative Evidence Handling**

Added Stage 3 contradiction detection that runs on every query:
- Sources that explicitly disagree with consensus
- Conditions where logic chain breaks down
- Historical examples where similar logic failed
- Missing considerations that could invalidate conclusions

**Files updated:**
- `answer_generation_prompts.py` - Extended SYNTHESIS_PROMPT, added CONTRADICTION_PROMPT
- `answer_generation.py` - Added `extract_confidence_metadata()`, `identify_contradictions()`, updated `synthesize_chains()` and `generate_answer()`
- `states.py` - Added `confidence_metadata` and `contradictions` fields

---

### Dependencies
- Parent `models.py` for AI calls (call_claude_haiku, call_claude_sonnet, call_openai_embedding)
- Parent `.env` for API keys (PINECONE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY)
- Pinecone "research-papers" index (built by database_manager subproject)

### Recent Changes
- Fixed Claude Haiku model ID (`claude-haiku-4-5-20251001`)
- Implemented flexible two-stage query expansion prompt
- Tuned prompt to produce concrete market terminology instead of academic jargon

### Design Decisions

**Query Expansion Approach:**
- Two-stage thinking: LLM first identifies relevant dimensions, then generates queries
- No predefined categories - LLM invents dimension names relevant to each specific query
- Prompt tuned to avoid academic jargon and stay close to original query

**Example output for "liquidity and risk asset price relationship":**
```
[Direct Mechanism] liquidity conditions impact on equity valuations
[Monetary Policy Transmission] Fed liquidity injections and stock market performance
[Market Stress Episodes] liquidity crises and equity price declines
[Reverse Causality] stock market volatility and financial system liquidity
```

### Key Patterns (from CLAUDE.md)
- Main file (`retrieval_orchestrator.py`) = orchestration only, no business logic
- Each module has corresponding `*_prompts.py` file
- All AI calls go through parent's `models.py`
- `.env` loaded from parent directory

### Configuration Notes
- `SIMILARITY_THRESHOLD = 0.45` - Lowered from 0.7; current index returns scores ~0.45-0.52 for relevant queries
- `DEFAULT_TOP_K = 10` - Per query, before deduplication across multi-query results
- `MAX_CHUNKS_FOR_ANSWER = 15` - Limits chunks sent to answer generation to preserve LLM reasoning quality

---

**TODO**: Check the initial logic extraction logic in `subproject_database_manager` - verify `logic_chains` are being extracted correctly at ingestion time.
