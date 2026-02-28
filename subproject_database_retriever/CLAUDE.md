# Database Retriever Subproject - Claude Context

## Project Overview
This subproject implements an agentic RAG (Retrieval-Augmented Generation) pipeline for querying the vector database of financial research data. It handles semantic search, iterative query refinement, and generating answers to research questions using retrieved context.

## Parent Project Goal
The entire project aims to produce an agentic research workflow. This subproject is specifically for **retrieval and question-answering**.

## Technology Stack
- **Vector Database**: Pinecone (queries the "research-papers" index built by database_manager)
- **Embeddings**: OpenAI embeddings (text-embedding-3-large, 3072 dimensions)
- **Framework**: Agentic ReAct loops via `shared/agent_loop.py`
- **AI Model Calls**: Via `models.py` in parent directory
- **Environment**: `.env` file in project root folder (use `python-dotenv` to load)

## Architecture Principles

### Code Organization
```
subproject_database_retriever/
├── retrieval_orchestrator.py    # MAIN FILE - orchestrator only
├── query_processing.py          # Function: process and expand queries
├── vector_search.py             # Function: semantic search in Pinecone
├── context_synthesis.py         # Function: synthesize retrieved chunks
├── answer_generation.py         # Function: generate final answers
├── knowledge_gap_detector.py    # Function: detect and fill knowledge gaps
├── knowledge_gap_prompts.py     # Prompts for gap detection
├── web_chain_persistence.py     # Function: persist verified web chains to Pinecone (L1 learning)
├── query_routing.py             # Function: route queries to appropriate handlers
├── {other}_prompts.py           # Prompts for each workflow
├── states.py                    # LangGraph state definitions
├── config.py                    # Configuration management
├── utils/                       # Utility functions
│
│   # EDF (Epistemic Decomposition Framework) — Phase 0:
├── edf_decomposer.py            # Phase 0: Opus call → knowledge tree JSON (7 knowledge types)
├── edf_decomposer_prompts.py    # Phase 0: Decomposition + coverage scoring prompts
│
│   # Hybrid agentic pipeline files (tested 2026-02-24):
├── retrieval_agent.py           # Phase 0+1: EDF decomposition → agentic retrieval (ReAct loop)
├── retrieval_agent_tools.py     # Phase 1: Tool schemas + handlers (6 tools, EDF-aware coverage)
└── retrieval_agent_prompts.py   # Phase 1: System prompt (EDF + generic) + coverage prompts
```

### Main File Structure (`retrieval_orchestrator.py`)
The main file should **ONLY** contain:
1. Loading of States
2. Calling other .py files (function modules)
3. Central router logic
4. NO business logic or implementation details

### Function Module Pattern
Each separate `.py` file (except main) works as a **function module**:
- Receives certain parameters as input
- Performs a simple workflow
- Returns output to be passed via States
- Each function should consist of a simple, focused workflow

### AI Calls Pattern
- **All AI calls** must go through `models.py` in parent directory
- `models.py` sets up AI models as callable functions (for easier updates)
- Import and use those functions, never call AI APIs directly

### Prompts Pattern
- **All prompts** must be in `{filename}_prompts.py` files
- Each module has its corresponding prompts file
- Call prompts from these files, never hardcode prompts in logic files
- Example: `query_processing.py` uses prompts from `query_processing_prompts.py`

### Debug Print Guidelines
- **LLM responses**: Print FULL raw texts
- **Other outputs**: Print raw texts, but NOT full (summary/truncated is fine)
- Always print raw texts (not processed/formatted versions)

## State Management (LangGraph)
- States defined in `states.py`
- States pass data between function modules
- Keep states simple and minimal for now
- Add states as needed during development
- **Don't be overly complicated** - start minimal, extend as needed

## Environment Configuration
- `.env` file location: Project root folder (parent directory)
- Use `python-dotenv` to load environment variables
- All API keys and secrets stored in `.env`
- Example variables:
  ```
  OPENAI_API_KEY=...
  PINECONE_API_KEY=...
  PINECONE_ENVIRONMENT=...
  PINECONE_INDEX_NAME=...
  ANTHROPIC_API_KEY=...
  ```

## Current Scope
**This subproject handles retrieval and RAG ONLY:**
- Processing user queries
- Semantic search in vector database
- Iterative query refinement (agentic capability)
- Synthesizing retrieved context
- Generating answers to research questions
- Finding specific metrics, thresholds, or data points

**NOT in scope (handled by database_manager):**
- Building/updating the vector database
- Processing Telegram messages
- Embedding generation for new data
- QA validation of extractions

## Query Types Supported

### 1. Research Questions
Questions about financial data, market interpretations, Fed policy, etc.
- "What does rising RDE indicate about liquidity conditions?"
- "How does USDKRW affect global liquidity?"
- "What are the precursors to Fed rate cuts?"

### 2. Data Lookup
Finding specific metrics, thresholds, or data points.
- "What level of RDE indicates market stress?"
- "What threshold triggers Fed intervention?"
- "Find all mentions of Reserve Demand Elasticity"

## Agentic RAG Capabilities

The retriever can:
1. **Iterate on queries** - Refine search terms based on initial results
2. **Expand queries** - Generate alternative phrasings for better recall
3. **Combine retrievals** - Merge results from multiple search passes
4. **Self-assess** - Determine if retrieved context is sufficient
5. **Route queries** - Direct different query types to appropriate handlers
6. **Score confidence** - Compute confidence based on path count and source diversity
7. **Detect contradictions** - Identify evidence that weakens consensus conclusions
8. **LLM re-ranking** - Score retrieved chunks for causal relevance
9. **Chain-of-retrievals** - Auto-follow dangling effects with follow-up queries (NEW)

### Answer Generation Pipeline (3 Stages)

| Stage | Purpose | Output |
|-------|---------|--------|
| Stage 1 | Extract and organize logic chains | Grouped chains by theme |
| Stage 2 | Synthesize consensus and variables | Confidence-scored conclusions |
| Stage 3 | Identify contradicting evidence | Contradiction analysis |

### Cross-Chunk Chain Linkage (NEW)

The answer generation system now supports **explicit chain connection across chunks** using normalized variable names.

**How it works:**
1. Extraction adds `cause_normalized` and `effect_normalized` to each logic chain step
2. `answer_generation.py` builds an effect map: `{effect_normalized: [chunk_ids]}`
3. For each chunk's cause, check if it matches another chunk's effect
4. Generate "## CHAIN CONNECTIONS" section listing linkable variables
5. LLM uses these hints to build multi-hop chains

**Example context sent to LLM:**
```
[Source 1: Goldman Sachs]
Logic chains:
  - JPY weakness [jpy_weakness] → carry trade unwind [carry_unwind]: funding currency appreciation...

[Source 2: UBS]
Logic chains:
  - carry trade unwind [carry_unwind] → EM equity selling [em_selling]: deleveraging pressure...

## CHAIN CONNECTIONS (use these for multi-hop reasoning):
- carry_unwind: appears as effect in [chunk_1]
```

**Result:** LLM connects: `jpy_weakness → carry_unwind → em_selling` across sources.

### Confidence Metadata (NEW)

Each synthesis includes structured confidence metadata:
```json
{
  "overall_score": 0.75,      // 0.0-1.0 numeric score
  "path_count": 3,            // Number of supporting paths
  "source_diversity": 2,      // Unique institutions supporting conclusion
  "confidence_level": "High"  // High/Medium/Low
}
```

**Confidence Guidelines:**
- **High (0.8+)**: 3+ paths from 2+ independent sources
- **Medium (0.5-0.8)**: 2 paths OR single source with strong logic
- **Low (<0.5)**: Single path, weak support, or contradictory evidence

### Contradiction Detection (Conditional)

Stage 3 identifies evidence that contradicts or weakens consensus:
- Sources that explicitly disagree
- Conditions where logic chain breaks down
- Historical examples where similar logic failed
- Missing considerations that could invalidate conclusions

Output includes impact assessment (High/Medium/Low) and recommendation.

**Skip Conditions (for efficiency):**
- `data_lookup` queries (simple factual lookups don't need contradiction analysis)
- High confidence syntheses (>= 0.85 score)

**Configuration (`config.py`):**
```python
SKIP_CONTRADICTION_FOR_DATA_LOOKUP = True  # Skip for data_lookup queries
SKIP_CONTRADICTION_CONFIDENCE_THRESHOLD = 0.85  # Skip if confidence >= this
```

### Two-Stage Retrieval with LLM Re-Ranking (NEW)

Addresses the risk of retrieving conceptually adjacent but causally unrelated content with a fixed similarity threshold.

**Stage 1: Broad Semantic Recall**
- Lower similarity threshold (0.40) for higher recall
- Retrieves more candidates (top 20) to ensure coverage
- Pure embedding-based semantic search

**Stage 2: LLM Re-Ranking for Causal Relevance**
- Claude Haiku scores each chunk for CAUSAL relevance (0.0-1.0)
- Only high scores for chunks with actual causal reasoning relevant to query
- Filters out surface-level keyword matches that lack causal logic
- Returns top 10 after re-ranking
- **Uses structured output (tool_use)** for guaranteed JSON parsing (no more regex failures)

**Configuration (`config.py`):**
```python
ENABLE_LLM_RERANK = True           # Toggle for cost control
BROAD_RETRIEVAL_TOP_K = 20         # Stage 1: candidates to retrieve
BROAD_SIMILARITY_THRESHOLD = 0.40  # Stage 1: lower threshold for recall
RERANK_TOP_K = 10                  # Stage 2: keep top N after re-ranking
USE_STRUCTURED_RERANK = True       # Use tool_use for reliable JSON (recommended)
```

**Re-Ranking Scoring Guidelines:**
| Score | Meaning |
|-------|---------|
| 0.9-1.0 | Directly answers query with explicit causal logic (cause → effect → mechanism) |
| 0.7-0.8 | Contains relevant causal mechanisms or specific thresholds |
| 0.5-0.6 | Conceptually related but no direct causal link |
| 0.3-0.4 | Tangentially related, surface-level word overlap only |
| 0.0-0.2 | Off-topic despite keyword match |

**Cost:** ~$0.001-0.002 per query (Claude Haiku)

### Hybrid Retrieval - Original Query Protection (NEW)

Addresses query expansion dilution where expanded queries surface dimension-specific chunks that overtake the original query's holistic matches.

**Problem**: Original query might rank the most relevant chunk #1, but after merging 7 queries (1 original + 6 expanded), that chunk drops to #10 because narrow-topic chunks score higher on specific dimensions.

**Solution**: Guarantee original query's top-N chunks are preserved.

**How it works**:
1. **Stage 1A**: Get top-5 from original query (protected - always included)
2. **Stage 1B**: Add expanded query results for breadth (max-score merge, skip protected)
3. **Stage 2**: LLM re-ranking scores all candidates for causal relevance

**Configuration (`config.py`):**
```python
ORIGINAL_QUERY_TOP_N = 5  # Guaranteed slots for original query's top results
```

**Result**: Holistic relevance from original query + nuance breadth from expanded queries.

### Temporal Awareness for Logic Chain Focus (NEW)

Addresses temporal validity of extracted data - system now distinguishes time-bound values from timeless structural relationships.

**Problem**: If user queries about 2035 liquidity, system returns 2026-specific data ($1.26T QE, 83.4% prob). Absolute values become stale but structural relationships (QE → liquidity) remain valid.

**Solution**: LLM-aware temporal context - LLM receives temporal information and reasons about what's timeless vs time-bound.

**How it works**:
1. `query_processing.py` extracts temporal reference from query (e.g., "2035" → reference_year=2035)
2. `answer_generation.py` extracts `temporal_context` from each chunk's metadata
3. Builds temporal summary across chunks (data_years, forward_looking_count, structural_count)
4. Adds `## TEMPORAL GUIDANCE` section to context sent to LLM
5. If temporal mismatch (query year ≠ data years), instructs LLM to focus on logic chains

**LLM Behavior with Temporal Awareness**:
- Prioritizes LOGIC CHAINS (cause → effect) - these are timeless and transferable
- De-emphasizes ABSOLUTE VALUES ($1.26T, 83.4%) - these are time-bound
- Adds `**TEMPORAL NOTE:**` annotations distinguishing mechanisms from specific values
- Example: "The mechanism (QE → liquidity expansion) was projected at $1.26T scale in 2026 context"

**State Fields Added**:
- `query_temporal_reference`: {reference_year, reference_period, is_future, is_current}
- `data_temporal_summary`: {data_years, forward_looking_count, time_bound_count, structural_count}

**Use Case**: Query for future year → LLM extracts timeless logic chains → User can plug in current numbers and re-run the logic.

### Adaptive Query Expansion (NEW)

Adjusts the number of expansion dimensions based on query complexity.

**Problem**: Simple queries like "what is RDE?" don't need 6 expansion dimensions - wastes tokens and may dilute results.

**Solution**: Detect query complexity and adapt:
- **Simple queries** (≤10 words, single concept): 2-3 dimensions
- **Complex queries** (multiple concepts, relationships): 4-6 dimensions

**Complexity Detection:**
```python
complexity_indicators = [" and ", " or ", " relationship ", " between ", " causes ", " affects "]
is_simple = words <= 10 and not any(indicator in query for indicator in complexity_indicators)
```

**Configuration (`config.py`):**
```python
SIMPLE_QUERY_MAX_WORDS = 10        # Queries with <= this many words are "simple"
SIMPLE_QUERY_DIMENSIONS = 3       # Expansion dimensions for simple queries
COMPLEX_QUERY_DIMENSIONS = 6      # Expansion dimensions for complex queries
```

**Savings:** 30-50% reduction in expansion tokens for simple queries

### Chain-of-Retrievals (NEW)

Addresses incomplete chain traversal - when retrieved chunks mention an intermediate effect but don't explain what it leads to.

**Problem**: Current retrieval is single-hop. If chunks mention "carry_unwind" as an effect but nothing explains what carry_unwind leads to, the answer is incomplete.

**Solution**: Post-retrieval chain expansion - detect dangling effects and run follow-up queries.

**How it works**:
1. After initial retrieval, `detect_dangling_chains()` finds effects that aren't causes anywhere
2. Effects are sorted by frequency (most common first)
3. `expand_dangling_chains()` runs follow-up queries for top N effects
4. New chunks are merged with original chunks (deduplicated)
5. Synthesis proceeds with the expanded context

**Example flow**:
```
Query: "JPY intervention impact on USD"
    ↓
Initial retrieval finds:
  - JPY intervention → JPY strength [jpy_strength]
  - JPY strength [jpy_strength] → carry unwind [carry_unwind]
    ↓
Dangling detection: "carry_unwind" is effect but not cause
    ↓
Follow-up query: "What is the impact of carry trade unwind?"
    ↓
Retrieves additional chunks:
  - carry unwind [carry_unwind] → forced liquidation [liquidation]
    ↓
Complete chain available for synthesis
```

**Configuration (`config.py`):**
```python
ENABLE_CHAIN_EXPANSION = True       # Toggle feature
MAX_DANGLING_TO_FOLLOW = 3          # Limit follow-up queries per run
MIN_CHUNKS_BEFORE_EXPANSION = 3     # Only expand if enough initial context
FOLLOWUP_TOP_K = 5                  # Chunks per follow-up query
FOLLOWUP_THRESHOLD = 0.40           # Similarity threshold for follow-ups
```

**Cost:** ~$0.0006 per query with 3 follow-ups (no LLM re-ranking on follow-ups)

**State Fields Added**:
- `dangling_effects_followed`: List of effects that were followed up with additional queries

### Knowledge Gap Detection & Filling (NEW)

The retrieval layer now handles gap detection and filling, providing enriched context to consumers (e.g., BTC Intelligence).

**Architecture Change**: Gap detection was moved FROM `subproject_risk_intelligence` TO here to make it topic-agnostic. The retrieval layer returns enriched results with merged DB + web chains.

**Workflow Step Added**:
```
process_query → search → generate → fill_gaps → conditional_resynthesis → persist_learning → END
```

**Gap Categories**:
| Category | fill_method | What it searches for |
|----------|------------|---------------------|
| topic_not_covered | web_chain_extraction | Extract logic chains from trusted web sources |
| historical_precedent_depth | web_search | Event DATES only (we compute impact ourselves) |
| quantified_relationships | data_fetch | Fetches instruments, computes correlation from price data |
| monitoring_thresholds | web_search | Analyst targets, intervention levels, price forecasts |
| event_calendar | web_search | Meeting dates, economic calendar |
| mechanism_conditions | web_search | Preconditions for causal mechanism |
| exit_criteria | web_search | Thesis resolution conditions |

**Key Functions**:
| Function | File | Purpose |
|----------|------|---------|
| `detect_knowledge_gaps()` | `knowledge_gap_detector.py` | LLM call to identify missing information |
| `fill_gaps_with_search()` | `knowledge_gap_detector.py` | Fill gaps via Tavily web search |
| `fill_gaps_with_data()` | `knowledge_gap_detector.py` | Fill gaps by computing from price data |
| `fill_gaps_with_web_chains()` | `knowledge_gap_detector.py` | Extract chains from trusted web sources |
| `expand_for_web_chain_extraction()` | `query_processing.py` | Generate multi-angle queries for web chain extraction |
| `merge_web_chains_with_db_chains()` | `knowledge_gap_detector.py` | Merge with confidence weighting |
| `detect_and_fill_gaps()` | `knowledge_gap_detector.py` | Main orchestration function |

**Multi-Angle Web Chain Extraction**:
When `topic_not_covered` gap is detected, generates multiple factor-focused queries instead of a single query:
```python
# Example: Query about "AI CAPEX impact on tech stocks"
# Instead of: "Bitcoin AI CAPEX tech stocks" (BTC-centric, wrong)
# Generates:
#   - "SaaS AI disruption software stocks"
#   - "hyperscaler CAPEX ROI concerns 2026"
#   - "BCA Research Goldman Sachs AI capex alternative view"
```

**Web Chain Query Angles** (`query_processing.py: expand_for_web_chain_extraction()`):
| # | Angle | Purpose |
|---|-------|---------|
| 1 | Direct trigger/catalyst | What event or announcement caused this |
| 2 | Structural enabler | Capital flows, policy decisions, market structure shifts |
| 3 | Alternative interpretation / regime-shift thesis | Named analyst/firm reading same data with different forward-looking conclusion |
| 4 | Quantitative impact | Dollar amounts, percentage moves, index levels |

**Resynthesis Prompt Rules** (`answer_generation_prompts.py: RESYNTHESIS_PROMPT`):
After gap filling, Sonnet integrates web chains with original synthesis. Key rules:
- Rules 1-7: Preserve original, integrate new chains, flag contradictions, weight DB (1.0) > web (0.7)
- **Rule 8 (Chain completeness)**: Verify full A→B→C chains. Common missing intermediate steps: real rates (nominal - inflation), yield curve dynamics (term premium, bear steepening), trade balance, fiscal deficit
- **Rule 9 (Regime-shift consideration)**: If web chains contain credible opposing views from named institutions, present as competing scenario. Do NOT force contrarian if no evidence supports one

**Configuration (`config.py`)**:
```python
ENABLE_GAP_DETECTION = True       # Run gap detection after answer generation
ENABLE_GAP_FILLING = True         # Attempt to fill detected gaps
MAX_GAP_SEARCHES = 6              # Maximum web searches for gap filling
MAX_ATTEMPTS_PER_GAP = 2          # Max refinement attempts per gap
```

**State Fields Added**:
- `knowledge_gaps`: Gap detection results
- `gap_enrichment_text`: Additional context from filled gaps
- `filled_gaps`: Gaps successfully filled
- `partially_filled_gaps`: Gaps with partial information
- `unfillable_gaps`: Gaps that could not be filled
- `extracted_web_chains`: Logic chains from web extraction
- `logic_chains`: Merged DB + web chains

**Return Format**:
```python
{
    "synthesis": "...",
    "logic_chains": [...],  # DB + web chains merged
    "knowledge_gaps": {...},
    "filled_gaps": [...],
    "gap_enrichment_text": "..."
}
```

**Cost**: ~$0.035 per query with Tavily (6 searches + 6 Haiku extractions + 1 gap detection)

### Web Chain Persistence — L1 Learning (NEW)

After gap filling and resynthesis, verified web chains are persisted to Pinecone so subsequent queries benefit from previously discovered knowledge.

**File**: `web_chain_persistence.py`

**How it works**:
1. Filters web chains: only `quote_verified=True` AND `confidence in ("high", "medium")`
2. Normalizes flat web chain schema to canonical `LogicChain` format
3. Generates embeddings via `call_openai_embedding()`
4. Upserts to Pinecone with metadata: `category: "web_chain"`, cause/effect normalized, source, mechanism
5. Chain ID format: `web_{md5(cause+effect+source)[:16]}`
6. Also updates `variable_frequency.json` with newly seen variables

**Key Functions**:
| Function | File | Purpose |
|----------|------|---------|
| `persist_web_chains()` | `web_chain_persistence.py` | Filter, embed, upsert web chains to Pinecone |
| `persist_learning()` | `retrieval_orchestrator.py` | Graph node wrapping persistence + frequency tracking |

### EDF Decomposition — Phase 0 (NEW)

**Status: Implemented, enabled by default. Toggle: `EDF_ENABLED=0` to disable.**

Solves the "doesn't know what it doesn't know" problem. Before retrieval begins, an Opus call decomposes the query into a structured knowledge tree across 7 dimensions. This replaces generic query expansion with targeted retrieval guided by the tree.

**The 7 Knowledge Types:**

| # | Type | What It Captures |
|---|------|-----------------|
| 1 | factual_specifics | Numbers, dates, scope, legal citations |
| 2 | actor_knowledge | Key people/institutions and their roles |
| 3 | structural_knowledge | System/process/legal framework mechanics |
| 4 | behavioral_precedent | What actors have done before in similar situations |
| 5 | reaction_space | What could happen next, alternative paths |
| 6 | historical_analogs | When has something similar happened before |
| 7 | impact_channels | Specific mechanisms connecting event to target |

Types 2-5 are the dimensions that distinguish deep analysis from shallow — they capture human and institutional dynamics. These were entirely absent from the previous generic coverage checks.

**How It Works:**

1. `edf_decomposer.py` calls Opus with the query → returns a knowledge tree (JSON with keywords × items × 7 types)
2. Each item has: `priority` (ESSENTIAL/IMPORTANT/SUPPLEMENTARY), `source_hint` (research_db/web_search/data_api/parametric), `searchable_query`
3. The retrieval agent receives the tree as a structured search plan in its initial message
4. Coverage assessment scores gathered material against the tree items (Y/P/N per item) instead of 6 generic binary flags
5. Unfilled ESSENTIAL items become explicit gap-fill targets with suggested queries

**Source Hint Routing:**
- `research_db` → Pinecone search queries (reasoning/mechanisms only — NEVER for specific data points)
- `web_search` → Tavily web search / web chain extraction (ground truth for factual data)
- `data_api` → deferred to Phase 2 (data grounding)
- `parametric` → no retrieval needed (LLM already knows this)

**Source Credibility Rules (CRITICAL):**

Pinecone contains institutional research logic chains from Telegram. These are **pointers** — they tell you what mechanisms exist, what variables matter, what causal paths to investigate. They are **NOT ground truth data sources**.

| Source | Can score Y (fully covered) for | Can only score P (partial) for |
|--------|--------------------------------|-------------------------------|
| Pinecone chunks / web chains | impact_channels, behavioral_precedent, structural_knowledge, reaction_space, actor_knowledge | factual_specifics with numbers/dates/amounts, historical_analogs with quantified outcomes |
| Web search results | Any item type (primary/verifiable source) | — |
| Parametric | Well-established frameworks (constitutional mechanics, basic economic theory) | — |

**Example:** If a Pinecone chain says "BoJ sold $1T USD → JPY/USD up 10%", the system should use this to know to *investigate BoJ FX interventions and track JPY/USD*, but must NEVER treat "$1T" or "10%" as verified data. Those specific numbers must come from web search or data API to score Y.

**Phase 0.5 — Mechanical Pre-Fetch:**

After decomposition, the search plan is executed deterministically before the agent loop starts:
- All `research_db` items → Pinecone queries (deduped, ~5 chunks per query)
- The original query → Pinecone (always, often the best single search)
- All ESSENTIAL `web_search` items → Tavily web search
- Main query → web chain extraction (saved chains first, then Tavily)

The agent loop then starts with material already gathered. Its first action is `assess_coverage` to score what's been found, then it adaptively fills any remaining gaps. This ensures every EDF item gets searched — the agent doesn't decide whether to search, only whether gaps need more targeted filling.

**Files:** `edf_decomposer.py`, `edf_decomposer_prompts.py`, pre-fetch logic in `retrieval_agent.py:_run_edf_prefetch()`

**Cost:** ~$0.15-0.30 extra per query (1 Opus call for decomposition + Sonnet calls for EDF coverage scoring + Pinecone queries are essentially free)

**Feature flag:** `shared/feature_flags.py: edf_enabled()` (env: `EDF_ENABLED`, default: enabled)

### Agentic Retrieval — Phase 1 (Tested 2026-02-24)

**Status: Tested on Cases 1, 2, 4. Two bugs fixed: dict key mismatch (`"web_chains"` → `"extracted_chains"` in handler) silently dropped all web chains, and agent prompt too weak (kept searching after ADEQUATE coverage instead of synthesizing). Fixed in commit b2151d1.**

When enabled, replaces the fixed LangGraph retrieval flow with an iterative ReAct agent that searches, assesses coverage, and iterates until material is sufficient.

**Files**: `retrieval_agent.py`, `retrieval_agent_tools.py`, `retrieval_agent_prompts.py`

The agentic retrieval agent is the default path for all queries (except lightweight theme refresh which uses `skip_gap_filling=True`).

**Tools** (6 total):
| Tool | Wraps | Purpose |
|------|-------|---------|
| `search_pinecone` | `vector_search.search_single_query()` | Vector DB search with optional reranking |
| `extract_web_chains` | `knowledge_gap_detector.fill_gaps_with_web_chains()` | Multi-angle web chain extraction |
| `web_search` | `_get_web_search_adapter()` + `_search_and_evaluate()` | Tavily web search for factual gaps |
| `generate_synthesis` | `answer_generation.generate_answer()` | 3-stage chain extraction + synthesis |
| `assess_coverage` | NEW — Sonnet call with rubric-aware prompt | Rates material as COMPLETE/ADEQUATE/INSUFFICIENT |
| `finish_retrieval` | Exit tool | Agent passes final state summary |

**Coverage Checker**: Two modes depending on whether EDF is enabled:

*EDF mode (default)*: Scores gathered material against the knowledge tree. Each item gets Y/P/N weighted by priority (ESSENTIAL=1.0, IMPORTANT=0.5, SUPPLEMENTARY=0.25). Source credibility rules enforce that Pinecone can only score P for factual data items. Rating:
- **COMPLETE**: 0 ESSENTIAL items scored N, 0-2 IMPORTANT items scored N
- **ADEQUATE**: 0-1 ESSENTIAL items scored N — proceed to synthesis
- **INSUFFICIENT**: 2+ ESSENTIAL items scored N — must search more

*Generic mode (fallback)*: 6 binary flags (has_causal_chains, has_counter_argument, etc.). Rates as:
- **COMPLETE**: All flags true
- **ADEQUATE**: has_causal_chains=true (proceed even if other flags false)
- **INSUFFICIENT**: has_causal_chains=false

**Max iterations**: 5 (configurable via `RETRIEVAL_MAX_ITER` env var)

**Stall Detection** (prevents wasted iterations on unfillable gaps):

The coverage scorer is stateless — it can return INSUFFICIENT repeatedly even when gaps are genuinely unfillable. Stall detection compares consecutive `assess_coverage` scores and intervenes when no progress is made.

Three mechanisms work together:
1. **Coverage history tracking**: `RetrievalAgentState.coverage_history` records the percentage from each assessment call
2. **Auto-assessment**: After 3 search tool calls without an `assess_coverage`, automatically triggers one. If coverage improved < 5 percentage points (stall), directly calls `handle_generate_synthesis()` — bypassing the agent's decision entirely
3. **Short-circuit**: Once stall is detected (`agent_state.stall_detected = True`), all subsequent search tool calls (`search_pinecone`, `extract_web_chains`, `web_search`) return immediately with a skip message instead of making real API calls

The stall handler generates synthesis directly because the agent reliably ignores ADEQUATE signals embedded in parallel tool results (the signal gets diluted when it's one of three results in a batch). Generating synthesis mechanically is more reliable than trying to convince the agent to do it.

**Returns**: Dict compatible with `RetrieverState` (same fields as `run_retrieval()`).

### skip_gap_filling Parameter (NEW)

`run_retrieval()` accepts `skip_gap_filling: bool = False`. When true:
- Gap detection and filling are skipped
- Web chain persistence is skipped
- Used by `theme_refresh.py` for lightweight retrieval during daily monitoring

**State Field Added**:
- `skip_gap_filling`: bool (in `RetrieverState`)

## Flexible Design Decisions (TBD)
The following are intentionally left flexible for future decisions:
- **Retrieval strategy** - Top-k, MMR, hybrid search, etc.
- **Chunk handling** - How to process and rank retrieved chunks
- **Answer format** - Structured vs. free-form responses
- **State schema details** - Add as we go along
- **Specific workflows** - Will be defined as needed

## Development Guidelines

### When Adding New Functionality
1. Create a new function module file (e.g., `new_feature.py`)
2. Create corresponding prompts file (e.g., `new_feature_prompts.py`)
3. Define inputs and outputs clearly
4. Update States if needed (in `states.py`)
5. Add routing logic in `retrieval_orchestrator.py`
6. Use AI calls via parent's `models.py`

### Code Style
- Keep function modules simple and focused
- Clear parameter naming
- Type hints where helpful
- Document complex logic
- Follow existing patterns in codebase

### Import Pattern
```python
# In any module that needs AI calls
import sys
sys.path.append('../')  # or appropriate path to parent
from models import call_claude, call_gpt4  # or whatever functions exist

# Load environment
from dotenv import load_dotenv
load_dotenv('../.env')  # or appropriate path to root .env

# Pinecone connection
from pinecone import Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("research-papers")
```

## Router Logic (Central Router in Main File)
- Routes execution flow between function modules
- Decides which function module to call next
- Handles state transitions
- Coordinates the agentic workflow
- Implements iteration logic for query refinement
- (Details to be defined during development)

## Notes for AI Assistants
- **Always read existing code** before suggesting modifications
- **Follow the established patterns** strictly:
  - Main file only for orchestration
  - Function modules for business logic
  - Prompts in separate files
  - AI calls via parent's models.py
- **Keep it flexible** - Many design decisions are intentionally TBD
- **Don't over-engineer** - Start simple, extend as needed
- **Ask for clarification** when design decisions need to be made
- **Print raw texts** according to the debug guidelines above
- **Use .env from parent directory** for all configuration
- **File organization may change** - be adaptable
- **CRITICAL: DO NOT OVERCOMPLICATE** - Focus ONLY on what is explicitly asked to do
- **DO NOT overthink** and add features, checks, or functionality that was never requested
- **DO NOT add stuff nobody asked for** - No extra error handling, logging, validation, or features unless explicitly requested
- **Keep it minimal and focused** - Only implement exactly what is asked, nothing more
- **Write all one-time test files to `tests/` folder** - Keep root directory clean

## Related Files

### In Parent Directory
- `models.py` - AI model functions (must use this for all AI calls)
- `.env` - Environment variables and API keys

### In database_manager (Reference Only)
- `pinecone_uploader.py` - Reference for Pinecone connection patterns
- `embedding_generation.py` - Reference for embedding patterns
- Data stored in Pinecone "research-papers" index

## TODO

### Gap Detection Prompt Fix (DONE)
- [x] **Prompt now checks "question answered?" instead of "topic mentioned?"**
  - **Fixed in**: commit `1071c53`
  - **Verified**: commit `49d3800` (successful pipeline run after fix)
  - **Prompt now says**: "COVERED = Synthesis directly ANSWERS the specific question asked" / "GAP = Synthesis does NOT answer the question, even if it mentions related topics"
  - **Result**: Web chain extraction now triggers correctly for tangentially-related but non-answering content

### Gap-Filling Result Cache (Level 2)
- [ ] **Cache full gap-filling output keyed by query hash**
  - Store: enrichment text, web chains, historical analog results (episodes, pattern probabilities), image extraction dates
  - On similar query: retrieve cached gap-fill results, skip image extraction + event study + web search
  - Only re-run `analyze_impact()` with fresh market data
  - Storage: JSON file alongside `btc_relationships.json` (e.g., `gap_fill_cache.json`)
  - Key: hash of (query + indicator_name), TTL-based expiry for staleness

### Original TODOs (mostly done)
- [x] Set up initial project structure
- [x] Create `states.py` with basic state definitions
- [x] Implement `retrieval_orchestrator.py` skeleton
- [x] Create vector search module
- [x] Create query processing module
- [x] Create answer generation module
- [x] Implement agentic iteration logic
- [x] Test basic query-answer workflow
- [x] Add gap detection and filling (moved from BTC Intelligence)
