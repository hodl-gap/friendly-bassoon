# Variable Mapper Subproject - Claude Context

## Project Overview
This subproject translates text-based logic chains and synthesis outputs into structured data queries. It takes the output from database_retriever (logic chains, key variables to monitor) and extracts actionable variables, thresholds, conditions, and data source mappings.

## Parent Project Goal
The entire project aims to produce an agentic research workflow. This subproject is specifically for **translating logic into data queries**.

## Technology Stack
- **Input**: Synthesis output from database_retriever (logic chains, variables to monitor)
- **Output**: Structured JSON with variables, thresholds, conditions, data source mappings
- **Framework**: LangGraph (workflow skeleton)
- **AI Model Calls**: Via `models.py` in parent directory
- **Environment**: `.env` file in project root folder (use `python-dotenv` to load)

## Architecture Principles

### Code Organization
```
subproject_variable_mapper/
├── variable_mapper_orchestrator.py  # MAIN FILE - orchestrator only
├── variable_extraction.py           # Function: extract variables from text
├── threshold_extraction.py          # Function: extract thresholds/conditions
├── source_mapping.py                # Function: map variables to data sources
├── query_builder.py                 # Function: build structured queries
├── {module}_prompts.py              # Prompts for each workflow
├── states.py                        # LangGraph state definitions
├── config.py                        # Configuration management
└── tests/                           # Test files
```

### Main File Structure (`variable_mapper_orchestrator.py`)
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
- Example: `variable_extraction.py` uses prompts from `variable_extraction_prompts.py`

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
  ANTHROPIC_API_KEY=...
  ```

## Current Scope
**This subproject handles logic-to-query translation ONLY:**
- Extracting variables from logic chains/synthesis text
- Identifying thresholds and conditions
- Mapping variables to known data sources
- Building structured JSON queries
- Normalizing variable names to standard metrics

**NOT in scope (handled elsewhere):**
- Retrieval/querying vector database (done by database_retriever)
- Building/updating vector database (done by database_manager)
- Executing data queries against external APIs
- Real-time monitoring/alerting

## Input Format (from database_retriever)

The subproject receives synthesis output containing:
- **Logic chains**: Multi-step causal reasoning paths
- **Key variables to monitor**: Extracted indicators with thresholds
- **Consensus chains**: Aggregated conclusions from multiple sources

Example input:
```
## Consensus Chains
- Conclusion: Fed will pause QT
  Supporting paths:
    - Path 1: RDE spike → funding stress → Fed forced to act → pause QT
    - Path 2: TGA drawdown → liquidity pressure → policy response needed

## Key Variables to Monitor
- RDE level (threshold: >0.3 indicates stress)
- TGA balance (watch for <$500B drawdown)
- ON RRP usage (elevated = tight conditions)
```

## Output Format (Structured JSON)

The subproject produces structured queries:
```json
{
  "query_group": "Fed_QT_Pause_Risk",
  "variables": [
    {
      "name": "RDE",
      "normalized_name": "reserve_demand_elasticity",
      "threshold": 0.3,
      "condition": "greater_than",
      "interpretation": "indicates stress",
      "source": "NY Fed"
    },
    {
      "name": "TGA",
      "normalized_name": "treasury_general_account",
      "threshold": 500,
      "unit": "billion_usd",
      "condition": "less_than",
      "interpretation": "drawdown pressure",
      "source": "Daily Treasury Statement"
    }
  ],
  "conditions": [
    {
      "if": "RDE > 0.3 AND TGA < $500B",
      "then": "Fed likely to pause QT"
    }
  ],
  "dependencies": [
    {"from": "RDE", "to": "TGA", "relationship": "correlated"}
  ]
}
```

## Flexible Design Decisions (TBD)
The following are intentionally left flexible for future decisions:
- **Variable normalization strategy** - How to map various names to canonical forms
- **Source mapping details** - Specific API endpoints and data sources
- **Threshold parsing** - How to handle various threshold expressions
- **State schema details** - Add as we go along
- **Specific workflows** - Will be defined as needed

## Development Guidelines

### When Adding New Functionality
1. Create a new function module file (e.g., `new_feature.py`)
2. Create corresponding prompts file (e.g., `new_feature_prompts.py`)
3. Define inputs and outputs clearly
4. Update States if needed (in `states.py`)
5. Add routing logic in `variable_mapper_orchestrator.py`
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
from models import call_gpt5_mini, call_claude_sonnet  # or whatever functions exist

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
- [ ] Implement `variable_mapper_orchestrator.py` skeleton
- [ ] Create variable extraction module
- [ ] Create threshold extraction module
- [ ] Create source mapping module
- [ ] Create query builder module
- [ ] Test basic extraction workflow
- (More items will be added as development progresses)

## Related Files

### In Parent Directory
- `models.py` - AI model functions (must use this for all AI calls)
- `.env` - Environment variables and API keys

### In database_retriever (Input Source)
- `answer_generation.py` - Produces synthesis output that this subproject consumes
- `states.py` - Reference for state patterns
