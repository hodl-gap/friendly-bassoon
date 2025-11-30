# Database Manager Subproject - Claude Context

## Project Overview
This subproject manages a vector database of research papers for an agentic research workflow. It handles building, updating, and tracking research papers for future retrieval (finding references, understanding data usage, interpretations, etc.).

## Parent Project Goal
The entire project aims to produce an agentic research workflow. This subproject is specifically for database management.

## Technology Stack
- **Vector Database**: Pinecone
- **Embeddings**: OpenAI embeddings
- **Framework**: LangGraph (workflow skeleton)
- **AI Model Calls**: Via `models.py` in parent directory
- **Environment**: `.env` file in project root folder (use `python-dotenv` to load)

## Architecture Principles

### Code Organization
```
subproject_database_manager/
├── database_management.py       # MAIN FILE - orchestrator only
├── paper_ingestion.py          # Function: add papers to database
├── embedding_generation.py     # Function: generate embeddings
├── metadata_extraction.py      # Function: extract paper metadata
├── paper_ingestion_prompts.py  # All prompts for ingestion workflow
├── {other}_prompts.py          # Prompts for other workflows
├── states.py                   # LangGraph state definitions
├── config.py                   # Configuration management
└── utils/                      # Utility functions
```

### Main File Structure (`database_management.py`)
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
- Example: `paper_ingestion.py` uses prompts from `paper_ingestion_prompts.py`

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
  ```

## Current Scope
**This subproject handles database building ONLY:**
- Adding papers to vector database
- Updating paper metadata
- Managing database state
- Tracking what papers exist

**NOT in scope (handled elsewhere):**
- Retrieval/querying (done in other parts of the system)
- Analysis workflows
- Research synthesis

## Structured Output Definition

**Structured output** refers to the JSON-formatted extraction of insights from raw financial research messages. The goal is to capture not just data points, but the full interpretive context needed for retrieval WITHOUT requiring the full raw text.

### Key Requirements for Quality Structured Output

1. **Retrievability**: Multiple semantic entry points
   - Example: "USDKRW affects liquidity" should be findable via "currency", "liquidity", "Korea", OR "Fed policy"
   - Technical terms AND plain language both present
   - Various domain experts (macro, rates, FX) can discover the insight

2. **Completeness of Context**: Preserve if-then logic
   - NOT: "USDKRW down = bad"
   - YES: "USDKRW down = bad WHEN below 1300 BECAUSE of trade deficit implications"
   - Include: thresholds, conditions, causality, context dependencies, relationships

3. **Answer-ability**: Can answer specific research questions
   - Example: "What level indicates stress?" → needs threshold numbers (not just "high"/"low")
   - Include: quantitative data, specific timeframes, relationships between variables
   - Support backward retrieval (e.g., "What indicators suggest Fed will end QT?" → retrieve RDE data)

### Current Structured Output Types

From Telegram workflow (see STATUS.md):
- **data_opinion**: Research interpretations of economic data
- **interview_meeting**: Fed statements, FOMC minutes, official commentary

### Real-World Use Cases

Questions the structured output should be able to answer:

**Example 1: Data Interpretation**
- Q: "When I find RDE (Reserve Demand Elasticity) rising from -0.2 to 0.5, what does it mean?"
- Required context:
  - What RDE measures (market reaction to Fed liquidity)
  - Historical context (this 0.7 change only occurred twice in 20 years)
  - Interpretation (system has no liquidity, extreme money demand)
  - Policy implications (QT likely to stop due to pressure)

**Example 2: Threshold Identification**
- Q: "What level of X indicates market stress?"
- Required: Specific threshold numbers, not vague terms like "high" or "low"

**Example 3: Backward Retrieval**
- Q: "Is Fed likely to end QT? What should I look at?"
- Required: System retrieves RDE and other relevant indicators with their interpretive context

### QA Validation

All structured outputs are validated by a QA agent that checks:
1. **Retrievability** - Can be found through multiple search paths
2. **Completeness** - Preserves if-then logic, thresholds, causality
3. **Answer-ability** - Contains specific, actionable information

See `qa_validation.py` for implementation details.

## Flexible Design Decisions (TBD)
The following are intentionally left flexible for future decisions:
- **Chunking strategy** - Not yet decided, don't constrain it
- **Metadata schema** - Will evolve, keep flexible
- **Paper processing details** - Will be clarified during development
- **State schema details** - Add as we go along
- **Specific workflows** - Will be defined as needed

## Development Guidelines

### When Adding New Functionality
1. Create a new function module file (e.g., `new_feature.py`)
2. Create corresponding prompts file (e.g., `new_feature_prompts.py`)
3. Define inputs and outputs clearly
4. Update States if needed (in `states.py`)
5. Add routing logic in `database_management.py`
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
```

## Router Logic (Central Router in Main File)
- Routes execution flow between function modules
- Decides which function module to call next
- Handles state transitions
- Coordinates the workflow
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

## TODO
- [ ] Set up initial project structure
- [ ] Create `states.py` with basic state definitions
- [ ] Implement `database_management.py` skeleton
- [ ] Create first function module (paper ingestion)
- [ ] Set up Pinecone connection
- [ ] Test basic paper upload workflow
- (More items will be added as development progresses)

## Related Files in Parent Directory
- `models.py` - AI model functions (must use this for all AI calls)
- `.env` - Environment variables and API keys
