# Database Retriever - Status

**IMPORTANT**: Read `CLAUDE.md` first for project guidelines and patterns.

## Current State: Initial Structure Complete

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
