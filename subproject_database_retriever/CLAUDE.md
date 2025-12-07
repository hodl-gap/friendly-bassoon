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
