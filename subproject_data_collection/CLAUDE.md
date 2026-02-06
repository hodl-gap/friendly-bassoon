# Data Collection Subproject - Claude Context

## Project Overview
This subproject handles data collection and validation for the agentic research workflow. It serves two primary purposes:
1. **Historical Data Validation** - Fetch historical data to programmatically validate claims from retrieval
2. **Institutional Flow News Collection** - Monitor news for institutional investor rebalancing decisions

## Parent Project Goal
The entire project aims to produce an agentic research workflow. This subproject is specifically for **data fetching and claim validation**.

## Technology Stack
- **Data Sources**: FRED API, Yahoo Finance, CoinGecko, RSS feeds
- **Framework**: LangGraph (workflow orchestration)
- **Statistical Analysis**: scipy, numpy, pandas
- **AI Model Calls**: Via `models.py` in parent directory
- **Environment**: `.env` file in project root folder (use `python-dotenv` to load)

## Architecture Principles

### Code Organization
```
subproject_data_collection/
├── data_collection_orchestrator.py  # MAIN FILE - LangGraph orchestrator
├── states.py                        # LangGraph state definitions
├── config.py                        # Configuration management
│
│  # Claim Validation Path
├── claim_parsing.py                 # Parse claims from retrieval output
├── claim_parsing_prompts.py
├── data_fetching.py                 # Fetch historical data from APIs
├── validation_logic.py              # Statistical validation (correlation, lag)
├── validation_prompts.py            # Validation result interpretation
├── output_formatter.py              # Format final output
│
│  # News Collection Path
├── news_collection.py               # Collect news from sources
├── news_collection_prompts.py
├── news_analysis.py                 # Analyze news for actionability
├── news_analysis_prompts.py
│
│  # Data Source Adapters
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py              # Abstract adapter interface
│   ├── fred_adapter.py              # FRED API adapter
│   ├── yahoo_adapter.py             # Yahoo Finance adapter
│   ├── coingecko_adapter.py         # CoinGecko API adapter
│   ├── web_search_adapter.py        # Web search + LLM extraction
│   ├── trusted_domains.py           # Trusted domain filtering for web chains
│   ├── news_adapters/
│   │   ├── __init__.py
│   │   ├── base_news_adapter.py     # Abstract news adapter
│   │   └── rss_adapter.py           # RSS feed adapter
│   │
│   └── institutional/               # Institutional allocation scrapers
│       ├── __init__.py
│       ├── base_scraper.py          # Abstract scraper interface
│       ├── storage.py               # JSON file storage
│       ├── scheduler.py             # APScheduler-based scheduling
│       ├── scraper_config.py        # Schedule configuration
│       ├── run_scrapers.py          # CLI runner
│       ├── fund_manager/            # Fund manager positioning
│       │   ├── ici_scraper.py       # ICI weekly fund flows
│       │   ├── aaii_sentiment_scraper.py
│       │   ├── aaii_allocation_scraper.py
│       │   └── bofa_fms_scraper.py  # BofA FMS via web search
│       ├── insurer/                 # Insurer allocation
│       │   ├── naic_scraper.py      # NAIC annual data
│       │   ├── acli_scraper.py      # ACLI fact book (PDF)
│       │   └── blackrock_insurance_scraper.py
│       └── japan/                   # Japan-specific
│           ├── boj_iip_scraper.py   # BOJ Int'l Investment Position
│           ├── boj_timeseries_scraper.py
│           └── japan_insurer_news_scraper.py
│
├── data/
│   ├── cache/                       # Cached API responses
│   ├── validation_results/          # Validation outputs
│   └── scraped/                     # Institutional allocation data
│       ├── fund_manager/
│       ├── insurer/
│       └── japan/
│
├── logs/                            # Debug logs
└── tests/                           # Test files
```

### Main File Structure (`data_collection_orchestrator.py`)
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
- Example: `claim_parsing.py` uses prompts from `claim_parsing_prompts.py`

### Debug Print Guidelines
- **LLM responses**: Print FULL raw texts (no truncation)
- **Other outputs**: Print raw texts, but NOT full (summary/truncated is fine)
- Always print raw texts (not processed/formatted versions)
- **File logging**: Debug output logged to `logs/` folder with timestamps

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
  FRED_API_KEY=...
  ```

## Current Scope

### Use Case 1: Claim Validation
When retrieval surfaces a claim like "BTC follows gold with 63-428 day lag":
1. Parse claim to identify variables and relationship type
2. Fetch historical data from APIs (FRED, Yahoo Finance, CoinGecko)
3. Run statistical validation (correlation, lag analysis)
4. Return: confirmed / partially_confirmed / refuted with evidence

**Example flow:**
```
Retrieval output: "BTC follows gold with decreasing lag" →
Fetch: Gold prices, BTC prices (historical) →
Validate: Calculate actual correlation/lag →
Confirm or refute the claim with data
```

### Use Case 2: Institutional Flow News Collection
Monitor news for institutional investor rebalancing decisions:
1. Collect news from RSS feeds (Reuters, Bloomberg, Nikkei)
2. Filter for relevance using LLM
3. Extract actionable insights (institution, action, direction)
4. Generate queries for the retriever to get context

**Example flow:**
```
News source → "Japanese insurers rebalancing into JGBs" →
Query retriever: "What does this mean for risk assets?" → Actionable insight
```

**NOT in scope (handled elsewhere):**
- Building/updating vector database (done by database_manager)
- Retrieval/querying (done by database_retriever)
- Variable normalization (done by variable_mapper)

## Integration Points

### Upstream: database_retriever
- Receives `retriever_synthesis` - Full synthesis text from answer_generation.py
- Receives `confidence_metadata` - Confidence scores from retriever
- Receives `logic_chains` - Extracted chains with cause/effect

### Upstream: variable_mapper
- Uses `discovered_data_ids.json` - Data ID mappings
- Uses `liquidity_metrics_mapping.csv` - Normalized variable names

### Downstream
- `retriever_queries` - Generated follow-up queries for database_retriever
- `validation_results` - Structured validation outputs

## Institutional Allocation Scrapers

Located in `adapters/institutional/`, these scrapers collect positioning data from institutional investors.

### Categories

| Category | Sources | Frequency |
|----------|---------|-----------|
| **Fund Manager** | ICI fund flows, AAII sentiment/allocation, BofA FMS | Weekly/Monthly |
| **Insurer** | NAIC, ACLI, BlackRock Insurance Report | Annual (check quarterly) |
| **Japan** | BOJ IIP, BOJ Time-Series, Insurer News | Daily/Weekly/Quarterly |

### Usage

```bash
# List available scrapers
python adapters/institutional/run_scrapers.py --list

# Run all scrapers
python adapters/institutional/run_scrapers.py --all

# Run by category
python adapters/institutional/run_scrapers.py --category japan

# Run specific scraper
python adapters/institutional/run_scrapers.py --scraper bofa_fms

# Check for updates only
python adapters/institutional/run_scrapers.py --check-only

# Daemon mode (scheduled)
python adapters/institutional/run_scrapers.py --daemon
```

### Storage Format

Data stored as JSON in `data/scraped/{category}/{source_name}/`:
- `{date}.json` - Dated snapshots
- `latest.json` - Most recent data

### Web Search Scrapers

Some sources (BofA FMS, Japan insurer news) use web search + LLM extraction:
1. Search via configurable backend (Tavily or DuckDuckGo)
2. Claude Haiku extracts structured data from search results
3. Captures publicly available data points only

**Search Backend** (`WEB_SEARCH_BACKEND` in `config.py`):
- `"tavily"` (default) — Tavily API, returns full page content, `topic="finance"`, requires `TAVILY_API_KEY`
- `"duckduckgo"` — Free, snippets only, no API key needed

### Web Chain Extraction (On-the-Fly)

When the retriever finds no relevant chunks for a topic, the system can extract logic chains from trusted web sources on-the-fly.

**Trusted Domain Filtering** (`adapters/trusted_domains.py`):
- **Tier 1**: Investment banks (Goldman, Morgan Stanley, JPMorgan, BofA, Citi, UBS), major news (Bloomberg, Reuters, FT, WSJ), central banks (Fed, ECB, BOJ), research firms (Fundstrat, Yardeni, BCA), asset managers (BlackRock, Bridgewater, VanEck, ARK)
- **Tier 2**: Secondary news (CNBC, MarketWatch), crypto sources (Grayscale, Glassnode, CoinDesk)

**Key Functions** (`adapters/web_search_adapter.py`):
- `search_and_extract_chains(query, topic, min_tier)` — Main extraction method
- Filters search results to trusted domains before LLM extraction
- Verifies evidence quotes appear verbatim in source content

**Configuration** (`config.py`):
```python
ENABLE_WEB_CHAIN_EXTRACTION = True   # Toggle feature
ENFORCE_TRUSTED_DOMAINS = True       # Only extract from trusted sources
TRUSTED_DOMAIN_MIN_TIER = 1          # 1 = Tier 1 only, 2 = include Tier 2
MAX_WEB_CHAINS_PER_QUERY = 5         # Limit chains per query
MIN_TRUSTED_SOURCES = 2              # Minimum sources required
WEB_CHAIN_CONFIDENCE_WEIGHT = 0.7    # Weight vs DB chains (1.0)
```

**Output Format**:
```json
{
  "cause": "AI boom and need for advanced AI models",
  "effect": "Data center capex investment increases",
  "mechanism": "Companies must build infrastructure to support AI",
  "polarity": "positive",
  "evidence_quote": "VERBATIM quote from source",
  "source_name": "Goldman Sachs",
  "source_url": "https://...",
  "confidence": "high",
  "quote_verified": true
}
```

**Usage**: Called by `btc_intelligence/knowledge_gap_detector.py` when `topic_not_covered` gap detected. Chains are transient (not persisted to Pinecone).

## Data Adapter Pattern

All data adapters inherit from `BaseDataAdapter`:
```python
class BaseDataAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the source name (e.g., 'FRED', 'Yahoo')."""
        pass

    @abstractmethod
    def fetch(self, series_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
        """Fetch historical data for a series."""
        pass

    @abstractmethod
    def validate_series(self, series_id: str) -> bool:
        """Check if series exists and is accessible."""
        pass
```

## Validation Types

| Type | Method | Output |
|------|--------|--------|
| `correlation` | Pearson/Spearman correlation | correlation coefficient, p-value |
| `lag` | Cross-correlation analysis | optimal lag, correlation at lag |
| `threshold` | Threshold breach checking | breach count, dates |
| `trend` | Trend direction verification | trend direction, significance |

## Output Formats

### Claim Validation Output
```json
{
  "mode": "claim_validation",
  "timestamp": "2026-01-27T10:30:00Z",
  "results": [
    {
      "claim": "BTC follows gold with 63-428 day lag",
      "status": "partially_confirmed",
      "actual_correlation": 0.45,
      "optimal_lag_days": 127,
      "p_value": 0.001,
      "interpretation": "Correlation exists but weaker than implied"
    }
  ]
}
```

### News Collection Output
```json
{
  "mode": "news_collection",
  "timestamp": "2026-01-27T10:30:00Z",
  "insights": [
    {
      "institution": "GPIF",
      "action": "rebalancing_to_jgb",
      "direction": "buy",
      "confidence": 0.85,
      "actionable_insight": "Japanese pension fund buying JGBs signals risk-off"
    }
  ],
  "retriever_queries": [
    "What does Japanese insurer rebalancing into JGBs mean for risk assets?"
  ]
}
```

## Development Guidelines

### When Adding New Functionality
1. Create a new function module file (e.g., `new_feature.py`)
2. Create corresponding prompts file (e.g., `new_feature_prompts.py`)
3. Define inputs and outputs clearly
4. Update States if needed (in `states.py`)
5. Add routing logic in `data_collection_orchestrator.py`
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
from models import call_claude_haiku, call_claude_sonnet

# Load environment
from dotenv import load_dotenv
load_dotenv('../.env')  # or appropriate path to root .env
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

## Related Files

### In Parent Directory
- `models.py` - AI model functions (must use this for all AI calls)
- `.env` - Environment variables and API keys

### In variable_mapper (Shared Resources)
- `mappings/discovered_data_ids.json` - Data ID mappings
- `data_id_validation.py` - API validation logic to reuse

### In database_manager (Shared Resources)
- `data/processed/liquidity_metrics/liquidity_metrics_mapping.csv` - Metric names

### In database_retriever (Input Source)
- `answer_generation.py` - Produces synthesis output that this subproject consumes
