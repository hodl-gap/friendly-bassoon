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
├── telegram_workflow_orchestrator.py  # MAIN ORCHESTRATOR - fetch + process + QA + cleanup
├── vector_db_orchestrator.py          # VECTOR DB ORCHESTRATOR - embed + upsert
│
├── telegram_fetcher.py               # Step 1: Fetch from Telegram API
├── message_pipeline.py               # Step 2: Single channel processing pipeline
├── extract_telegram_data.py          # Convert JSON to CSV
├── process_messages_v3.py            # Categorize + extract + metrics
├── qa_validation.py                  # QA sampling validation
├── qa_post_processor.py              # Standalone full QA CLI
│
├── embedding_generation.py           # Generate OpenAI embeddings
├── pinecone_uploader.py              # Upsert to Pinecone
│
├── categorization_prompts.py         # Prompts for message categorization
├── data_opinion_prompts.py           # Prompts for data_opinion extraction
├── interview_meeting_prompts.py      # Prompts for interview_meeting extraction
├── qa_validation_prompts.py          # Prompts for QA validation
├── cluster_assignment_prompts.py     # Prompts for LLM-based cluster assignment
├── image_extraction_prompts.py       # Prompts for image summarization + extraction
├── metrics_mapping_prompts.py        # Prompts for institution normalization
│
├── metrics_mapping_utils.py          # Metrics dictionary management + clustering
│
├── data/                             # Data folders (raw, processed, qa_logs)
└── tests/                            # Test files + obsolete modules
```

### Main Orchestrator Structure (`telegram_workflow_orchestrator.py`)
The main orchestrator contains:
1. CLI argument parsing
2. Step orchestration (fetch → process → QA → cleanup)
3. Calling function modules in sequence
4. NO business logic or implementation details

### Vector DB Orchestrator (`vector_db_orchestrator.py`)
Separate orchestrator for embedding workflow:
1. Generate embeddings from processed CSV
2. Upsert to Pinecone
3. Display index stats

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

## Workflow Architecture
- **Procedural Python** - Current implementation uses simple function calls, not LangGraph
- Data passes between modules via function return values and CSV files
- Orchestrators call function modules in sequence
- Keep it simple - only add complexity when needed

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

## Metrics Dictionary (liquidity_metrics_mapping.csv)

CSV file tracking all liquidity metrics discovered during extraction.

### CSV Schema
| Column | Description |
|--------|-------------|
| `normalized` | Canonical metric name (snake_case) |
| `variants` | Alternative names/spellings (pipe-delimited) |
| `category` | `direct` or `indirect` liquidity |
| `description` | What the metric measures |
| `sources` | Where metric was discovered (Institution, data_source) |
| `cluster` | Semantic grouping for data reproduction |
| `raw_data_source` | Raw data feed needed to reproduce |
| `is_liquidity` | `true` or `false` - flags non-liquidity entries |

### Cluster Examples
`fed_balance_sheet`, `etf_flows`, `cta_positioning`, `fx_liquidity`, `equity_flows`, `rate_expectations`

### Key Functions (metrics_mapping_utils.py)

**Core functions:**
- `load_metrics_mapping()` - Load metrics table for prompt injection
- `append_new_metrics()` - Add new metrics with validation + cluster assignment
- `get_existing_clusters()` - Get list of current clusters
- `assign_cluster_to_metric()` - LLM assigns single metric to cluster
- `assign_clusters_batch()` - Batch assign clusters to multiple metrics

**Validation functions (prevent duplicates/non-liquidity):**
- `validate_metric_name()` - Normalize to snake_case, truncate to 40 chars
- `is_liquidity_metric()` - Check against non-liquidity patterns/keywords
- `fuzzy_match_metric()` - Detect duplicates via variants/word overlap/Levenshtein

### Clustering Logic
- LLM-assisted assignment via GPT-4.1-mini
- New metrics get `suggested_cluster` from extraction prompt
- Defaults to existing clusters when possible
- One-to-one: each metric belongs to exactly one cluster

### Post-Mortem Cleanup (tests/cleanup_metrics.py)
Automated deduplication script that:
- Merges duplicates into canonical names (e.g., all CTA triggers → `cta_trigger_levels`)
- Flags non-liquidity entries with `is_liquidity=false`
- Standardizes all names to snake_case
- Runs automatically at end of orchestrator workflow

**Manual usage:**
```bash
python3 tests/cleanup_metrics.py           # Dry run
python3 tests/cleanup_metrics.py --execute # Apply changes
```

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

## Workflow Steps

### Telegram Workflow (`telegram_workflow_orchestrator.py`)
```
Step 1: telegram_fetcher.py        → Fetch messages from Telegram API
Step 2: message_pipeline.py        → For each channel:
        ├── extract_telegram_data.py   → Convert JSON to CSV
        ├── process_messages_v3.py     → Categorize, extract, update metrics
        └── qa_validation.py           → QA sampling validation
Step 3: tests/cleanup_metrics.py   → Post-mortem deduplication
```

### Vector DB Workflow (`vector_db_orchestrator.py`)
```
Step 1: embedding_generation.py    → Generate OpenAI embeddings
Step 2: pinecone_uploader.py       → Upsert to Pinecone
Step 3: Display index stats
```

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

## Completed
- [x] Telegram message fetching workflow
- [x] Message categorization and extraction (process_messages_v3.py)
- [x] Metrics dictionary with clustering
- [x] QA validation (sampling + full)
- [x] Post-mortem metrics cleanup
- [x] Vector DB embedding + Pinecone upload

## TODO
- [ ] Incremental updates (don't re-fetch already processed messages)
- [ ] Individual stock research category
- [ ] Keyword search support for Telegram fetching

## Related Files in Parent Directory
- `models.py` - AI model functions (must use this for all AI calls)
- `.env` - Environment variables and API keys
