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
├── variable_mapper_orchestrator.py  # MAIN FILE - LangGraph orchestrator
├── states.py                        # LangGraph state definitions
├── config.py                        # Configuration management
│
│  # 4-Step Pipeline
├── variable_extraction.py           # Step 1: Extract variables from text
├── variable_extraction_prompts.py
├── normalization.py                 # Step 2: Normalize to canonical names
├── normalization_prompts.py
├── missing_variable_detection.py    # Step 3: Find missing chain variables
├── missing_variable_detection_prompts.py
├── data_id_mapping.py               # Step 4: Map to data source IDs (auto-discovers if unmapped)
│
│  # Data ID Discovery (auto-triggered or stand-alone)
├── data_id_discovery.py             # Claude Agent SDK discovery
├── data_id_discovery_prompts.py
├── data_id_validation.py            # API ping validation
│
├── mappings/
│   └── discovered_data_ids.json     # Discovered data ID mappings
│
├── logs/                            # Debug logs (timestamped per run)
│   └── discovery_YYYYMMDD_HHMMSS.log
│
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
- **LLM responses**: Print FULL raw texts (no truncation)
- **Other outputs**: Print raw texts, but NOT full (summary/truncated is fine)
- Always print raw texts (not processed/formatted versions)
- **File logging**: All debug output must be logged to `logs/` folder with timestamps
- Discovery logs: `logs/discovery_YYYYMMDD_HHMMSS.log`

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

The subproject produces structured queries with **full data source details** for downstream data fetching:
```json
{
  "variables": [
    {
      "raw_name": "TGA",
      "normalized_name": "tga",
      "category": "direct",
      "type": "needs_registration",
      "data_id": "FRED:WTREGEN",
      "source": "FRED",
      "description": "Treasury General Account - U.S. Treasury deposits held at Federal Reserve Banks...",
      "api_url": "https://api.stlouisfed.org/fred/series/observations?series_id=WTREGEN&api_key=YOUR_API_KEY&file_type=json",
      "frequency": "weekly",
      "notes": "Free API but requires registration for API key...",
      "registration_url": "https://fred.stlouisfed.org/docs/api/api_key.html",
      "api_docs_url": "https://fred.stlouisfed.org/docs/api/fred/series_observations.html",
      "validated": true,
      "discovered_at": "2026-01-14T04:25:25.117759+00:00"
    },
    {
      "raw_name": "WDI",
      "normalized_name": "wdi",
      "type": "api",
      "data_id": "WorldBank:WDI",
      "source": "WorldBank",
      "description": "World Development Indicators - comprehensive database of global development indicators...",
      "api_url": "https://api.worldbank.org/v2/country/all/indicator/{INDICATOR_CODE}?format=json",
      "frequency": "annual",
      "notes": "WDI is a database/collection, not a single indicator...",
      "example_indicators": {
        "gdp": "NY.GDP.MKTP.CD",
        "population": "SP.POP.TOTL"
      }
    }
  ],
  "unmapped_variables": ["unknown_metric"],
  "missing_variables": ["fci", "yield_curve"],
  "dependencies": [
    {"from": "tga", "to": "liquidity", "relationship": "causes"}
  ]
}
```

**Key output fields per variable:**
- `api_url` - Ready-to-use API endpoint (replace YOUR_API_KEY)
- `description` - What this metric measures
- `notes` - Usage notes, data availability, units
- `frequency` - daily/weekly/monthly/annual
- `example_indicators` - For collection-type sources (e.g., WDI)
- `validated` - Whether API ping confirmed the data ID exists

## Design Decisions (Implemented)

- **Variable normalization**: Uses `liquidity_metrics_mapping.csv` from database_manager. Exact match first, then LLM fuzzy match via Claude Haiku.
- **Source mapping**: Claude Agent SDK discovers data sources dynamically. Searches known APIs (FRED, World Bank, BLS, OECD, IMF) first, then web.
- **Data ID storage**: JSON file (`mappings/discovered_data_ids.json`) stores discovered mappings persistently.
- **Validation**: API ping test before accepting mappings (FRED, World Bank, BLS supported).

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

## Bug Tracking for Liquidity Metrics CSV

When processing variables, if ANY strange or incorrect entries are detected in `liquidity_metrics_mapping.csv`:
1. **DO NOT** attempt to fix the CSV directly (it's in `subproject_database_manager`)
2. **Log the issue** in `LIQUIDITY_METRICS_BUGS.md` in this subproject
3. Use this format:
   ```
   ## [DATE] Issue Description
   - **Row**: normalized name or variant
   - **Problem**: What's wrong
   - **Suggested Fix**: How to fix it
   - **Detected During**: Which step/operation found this
   ```
4. Continue processing - don't block on CSV issues

Examples of "strange" entries to log:
- Duplicate normalized names
- Missing or malformed variants
- Wrong category assignments (direct vs indirect)
- Variables that should exist but are missing
- Typos in normalized names or descriptions

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

## Current Implementation Status

### Completed
- [x] `states.py` - LangGraph state definitions
- [x] `config.py` - Configuration with known APIs
- [x] `variable_mapper_orchestrator.py` - LangGraph workflow
- [x] Step 1: `variable_extraction.py` - Extract variables from text
- [x] Step 2: `normalization.py` - Normalize using liquidity_metrics_mapping.csv
- [x] Step 3: `missing_variable_detection.py` - Parse chains for missing variables
- [x] Step 4: `data_id_mapping.py` - Map using discovered_data_ids.json
- [x] `data_id_discovery.py` - Claude Agent SDK discovery (stand-alone)
- [x] `data_id_validation.py` - API ping validation

### TODO
- [ ] End-to-end test with real synthesis input
- [ ] Query builder module (optional, for structured output formatting)

## Data ID Discovery

Data ID discovery uses Claude Agent SDK to find data sources. It runs **automatically** in the pipeline when unmapped variables are detected (`AUTO_DISCOVER = True` in config.py).

### Auto-Discovery (Default Behavior)
When the pipeline encounters unmapped variables in Step 4:
1. Automatically triggers discovery for each unmapped variable
2. Saves results to `mappings/discovered_data_ids.json`
3. Re-maps the variables with the newly discovered data IDs
4. Logs full debug output to `logs/discovery_YYYYMMDD_HHMMSS.log`

### Manual Discovery (Stand-alone)
```bash
# Discover data IDs for specific variables
python data_id_discovery.py -v tga,vix,cpi

# The agent will:
# 1. Search known APIs (FRED, World Bank, BLS, OECD, IMF)
# 2. If not found, search the web for alternatives
# 3. Validate by pinging the APIs
# 4. Save to mappings/discovered_data_ids.json
```

### Discovery Outcomes
- `api` - Found in known API (e.g., FRED:WTREGEN)
- `needs_registration` - Found API but requires API key registration
- `scrape` - No API, but web scrapable (includes Python code)
- `not_found` - No public data source found

### Performance
- ~30-45 seconds per variable
- ~$0.10-0.15 per variable (Claude API cost)
- Cached in JSON - only runs once per variable

## Related Files

### In Parent Directory
- `models.py` - AI model functions (must use this for all AI calls)
- `.env` - Environment variables and API keys

### In database_retriever (Input Source)
- `answer_generation.py` - Produces synthesis output that this subproject consumes
- `states.py` - Reference for state patterns
