# Database Retriever Subproject - Claude Context

## Project Overview
This subproject implements an agentic RAG (Retrieval-Augmented Generation) pipeline for querying the vector database of financial research data. It handles semantic search, iterative query refinement, and generating answers to research questions using retrieved context.

## Parent Project Goal
The entire project aims to produce an agentic research workflow. This subproject is specifically for **retrieval and question-answering**.

## Technology Stack
- **Vector Database**: Pinecone (queries the "research-papers" index built by database_manager)
- **Embeddings**: OpenAI embeddings (text-embedding-3-large, 3072 dimensions)
- **Framework**: LangGraph (workflow skeleton)
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
├── query_routing.py             # Function: route queries to appropriate handlers
├── {other}_prompts.py           # Prompts for each workflow
├── states.py                    # LangGraph state definitions
├── config.py                    # Configuration management
└── utils/                       # Utility functions
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
8. **LLM re-ranking** - Score retrieved chunks for causal relevance (NEW)

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

### Contradiction Detection (NEW)

Stage 3 runs on **every query** to identify evidence that contradicts or weakens consensus:
- Sources that explicitly disagree
- Conditions where logic chain breaks down
- Historical examples where similar logic failed
- Missing considerations that could invalidate conclusions

Output includes impact assessment (High/Medium/Low) and recommendation.

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

**Configuration (`config.py`):**
```python
ENABLE_LLM_RERANK = True           # Toggle for cost control
BROAD_RETRIEVAL_TOP_K = 20         # Stage 1: candidates to retrieve
BROAD_SIMILARITY_THRESHOLD = 0.40  # Stage 1: lower threshold for recall
RERANK_TOP_K = 10                  # Stage 2: keep top N after re-ranking
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
- [ ] Set up initial project structure
- [ ] Create `states.py` with basic state definitions
- [ ] Implement `retrieval_orchestrator.py` skeleton
- [ ] Create vector search module
- [ ] Create query processing module
- [ ] Create answer generation module
- [ ] Implement agentic iteration logic
- [ ] Test basic query-answer workflow
- (More items will be added as development progresses)
