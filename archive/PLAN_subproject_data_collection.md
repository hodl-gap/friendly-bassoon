# Plan: Create subproject_data_collection

## Project Intention

**Quant Alpha Harvesting using Market Microstructure Data** - A research/analysis system for harvesting quantitative alpha using market microstructure data.

**Current System Architecture:**
```
subproject_database_manager    → Telegram messages → Pinecone vector DB
subproject_database_retriever  → Query → RAG → Answer with logic chains
subproject_variable_mapper     → Logic chains → Data ID mappings
subproject_data_collection     → [NEW] Data fetching + Claim validation
```

**End-to-End Flow:**
1. **database_manager**: Extracts financial research from Telegram, stores in Pinecone
2. **database_retriever**: User queries → semantic search → synthesized answers with logic chains
3. **variable_mapper**: Extracts variables from synthesis → maps to data source IDs (FRED, etc.)
4. **data_collection** [NEW]: Fetches actual data → validates claims programmatically

---

## Subproject Intention

**subproject_data_collection** serves two primary purposes:

### Use Case 1: Historical Data Validation
When the retriever surfaces a claim like "BTC follows gold with 63-428 day lag", this subproject:
1. Parses the claim to identify variables and relationship type
2. Fetches historical data from APIs (FRED, Yahoo Finance, CoinGecko)
3. Runs statistical validation (correlation, lag analysis)
4. Returns: confirmed / partially_confirmed / refuted with evidence

### Use Case 2: Institutional Flow News Collection
Monitors news for institutional investor rebalancing decisions:
1. Collects news from RSS feeds (Reuters, Bloomberg, Nikkei)
2. Filters for relevance using LLM
3. Extracts actionable insights (institution, action, direction)
4. Generates queries for the retriever to get context

---

## Implementation Plan

### Phase 1: Foundation (Files: 5)

Create base structure following existing patterns.

**Files to create:**
```
subproject_data_collection/
├── CLAUDE.md                              # Architecture documentation
├── STATUS.md                              # Progress tracking
├── data_collection_orchestrator.py        # LangGraph orchestrator
├── states.py                              # State definitions
└── config.py                              # Configuration
```

**1.1 Create `states.py`**
```python
class DataCollectionState(TypedDict, total=False):
    # Input
    mode: str  # "news_collection" | "claim_validation"

    # For claim_validation
    claims_input: List[Dict[str, Any]]
    retriever_synthesis: str
    variable_mappings: Dict[str, Any]

    # For news_collection
    news_query: str
    news_sources: List[str]
    time_window_days: int

    # Claim validation outputs
    parsed_claims: List[Dict[str, Any]]
    fetched_data: Dict[str, Any]
    validation_results: List[Dict[str, Any]]

    # News collection outputs
    collected_articles: List[Dict[str, Any]]
    analyzed_news: List[Dict[str, Any]]
    retriever_queries: List[str]

    # Output
    final_output: Dict[str, Any]
    errors: List[str]
```

**1.2 Create `config.py`**
- Load `.env` from parent directory
- Define paths to shared resources (discovered_data_ids.json, liquidity_metrics_mapping.csv)
- Model settings (claude_haiku for parsing, claude_sonnet for analysis)
- API settings (FRED_API_KEY, cache settings)
- Feature flags (ENABLE_NEWS_COLLECTION, ENABLE_CLAIM_VALIDATION)

**1.3 Create `data_collection_orchestrator.py`**
- LangGraph StateGraph with conditional routing
- Entry router: `mode="claim_validation"` → claim path, `mode="news_collection"` → news path
- Pattern: Follow `variable_mapper_orchestrator.py` exactly

---

### Phase 2: Data Adapters (Files: 5)

Create adapters for fetching historical data.

**Files to create:**
```
subproject_data_collection/
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py          # Abstract interface
│   ├── fred_adapter.py          # FRED API
│   ├── yahoo_adapter.py         # Yahoo Finance
│   └── coingecko_adapter.py     # CoinGecko API
```

**2.1 Create `base_adapter.py`**
```python
class BaseDataAdapter(ABC):
    @abstractmethod
    def fetch(self, series_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
        """Returns {"data": [(date, value), ...], "metadata": {...}}"""

    @abstractmethod
    def validate_series(self, series_id: str) -> bool:
        """Check if series exists"""
```

**2.2 Create `fred_adapter.py`**
- Reuse validation logic from `subproject_variable_mapper/data_id_validation.py`
- Handle rate limiting and caching
- Return normalized time series data

**2.3 Create `yahoo_adapter.py`**
- Use `yfinance` library
- Support tickers for stocks, ETFs, currencies
- Handle corporate actions

**2.4 Create `coingecko_adapter.py`**
- Free API for crypto prices
- Rate limiting (10-50 calls/min on free tier)
- Historical OHLCV data

---

### Phase 3: Claim Validation Path (Files: 6)

Implement the claim validation workflow.

**Files to create:**
```
subproject_data_collection/
├── claim_parsing.py               # Parse claims from synthesis
├── claim_parsing_prompts.py       # Extraction prompts
├── data_fetching.py               # Fetch data via adapters
├── validation_logic.py            # Statistical validation
├── validation_prompts.py          # Result interpretation
└── output_formatter.py            # Format final output
```

**3.1 Create `claim_parsing.py`**
- Input: `retriever_synthesis` (full text from answer_generation.py)
- Output: `parsed_claims` with structure:
  ```python
  {
      "claim_text": "BTC follows gold with 63-428 day lag",
      "variable_a": "btc",
      "variable_b": "gold",
      "relationship_type": "correlation",  # correlation|lag|threshold|trend
      "expected_lag": {"min": 63, "max": 428, "unit": "days"},
      "testability_score": 0.9
  }
  ```

**3.2 Create `data_fetching.py`**
- Input: `parsed_claims`, `variable_mappings` (from variable_mapper)
- Resolve data IDs using `discovered_data_ids.json`
- Call appropriate adapter based on source (FRED, Yahoo, CoinGecko)
- Align time series for comparison
- Output: `fetched_data` keyed by variable

**3.3 Create `validation_logic.py`**
- Input: `parsed_claims`, `fetched_data`
- Implement validation functions:
  - `_validate_correlation(claim, data)` - Pearson/Spearman correlation
  - `_validate_lag(claim, data)` - Cross-correlation lag analysis
  - `_validate_threshold(claim, data)` - Threshold breach checking
  - `_validate_trend(claim, data)` - Trend direction verification
- Output: `validation_results` with status, actual values, p-value, interpretation

---

### Phase 4: News Collection Path (Files: 5)

Implement the news collection workflow.

**Files to create:**
```
subproject_data_collection/
├── adapters/
│   └── news_adapters/
│       ├── __init__.py
│       ├── base_news_adapter.py   # Abstract news interface
│       └── rss_adapter.py         # RSS feed adapter
├── news_collection.py             # Collect from sources
├── news_collection_prompts.py     # Relevance prompts
├── news_analysis.py               # Analyze actionability
└── news_analysis_prompts.py       # Analysis prompts
```

**4.1 Create `rss_adapter.py`**
- Use `feedparser` library
- Support Reuters, Bloomberg, Nikkei RSS feeds
- Filter by date range

**4.2 Create `news_collection.py`**
- Input: `news_query`, `news_sources`, `time_window_days`
- Collect articles from configured RSS feeds
- Output: `collected_articles`

**4.3 Create `news_analysis.py`**
- `filter_relevant_articles(state)` - LLM relevance scoring
- `analyze_news_actionability(state)` - Extract institution, action, direction
- `generate_retriever_queries(state)` - Create follow-up queries for retriever
- Output: `analyzed_news`, `retriever_queries`

---

### Phase 5: Integration & Testing (Files: 3)

**Files to create:**
```
subproject_data_collection/
├── tests/
│   ├── test_adapters.py           # Adapter unit tests
│   ├── test_validation.py         # Validation logic tests
│   └── test_end_to_end.py         # Full workflow tests
├── data/
│   ├── cache/                     # Cached API responses
│   └── validation_results/        # Output storage
└── logs/                          # Debug logs
```

---

## LangGraph Workflow Diagram

```
                    START
                      │
                      ▼
              ┌───────────────┐
              │ route_by_mode │
              └───────┬───────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  "news_collection"  "claim_validation"  "hybrid"
       │              │                    │
       ▼              ▼                    │
┌─────────────┐ ┌─────────────┐           │
│collect_news │ │parse_claims │           │
└──────┬──────┘ └──────┬──────┘           │
       │               │                   │
       ▼               ▼                   │
┌─────────────┐ ┌─────────────┐           │
│filter_relev │ │resolve_ids  │           │
└──────┬──────┘ └──────┬──────┘           │
       │               │                   │
       ▼               ▼                   │
┌─────────────┐ ┌─────────────┐           │
│analyze_news │ │ fetch_data  │           │
└──────┬──────┘ └──────┬──────┘           │
       │               │                   │
       ▼               ▼                   │
┌─────────────┐ ┌─────────────┐           │
│gen_queries  │ │validate     │           │
└──────┬──────┘ └──────┬──────┘           │
       │               │                   │
       └───────┬───────┘                   │
               ▼                           │
        ┌─────────────┐                    │
        │format_output│◄───────────────────┘
        └──────┬──────┘
               │
               ▼
              END
```

---

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

---

## Critical Files to Reference

| File | Purpose |
|------|---------|
| `subproject_variable_mapper/variable_mapper_orchestrator.py` | LangGraph pattern |
| `subproject_variable_mapper/states.py` | State schema pattern |
| `subproject_variable_mapper/config.py` | Config pattern |
| `subproject_variable_mapper/data_id_validation.py` | API validation logic to reuse |
| `subproject_variable_mapper/mappings/discovered_data_ids.json` | Data ID mappings |
| `subproject_database_retriever/answer_generation.py` | Upstream synthesis source |
| `models.py` | AI model functions |

---

## Dependencies to Add

```
yfinance>=0.2.0        # Yahoo Finance
fredapi>=0.5.0         # FRED API
pycoingecko>=3.1.0     # CoinGecko
feedparser>=6.0.0      # RSS parsing
scipy>=1.10.0          # Statistical functions
```

---

## Implementation Order

1. **Phase 1**: Foundation (CLAUDE.md, STATUS.md, orchestrator, states, config)
2. **Phase 2**: Data adapters (base, FRED, Yahoo, CoinGecko)
3. **Phase 3**: Claim validation path (parsing, fetching, validation)
4. **Phase 4**: News collection path (RSS adapter, collection, analysis)
5. **Phase 5**: Integration tests and documentation

---

## Files to Create (Total: 24)

```
subproject_data_collection/
├── CLAUDE.md
├── STATUS.md
├── data_collection_orchestrator.py
├── states.py
├── config.py
├── claim_parsing.py
├── claim_parsing_prompts.py
├── data_fetching.py
├── validation_logic.py
├── validation_prompts.py
├── output_formatter.py
├── news_collection.py
├── news_collection_prompts.py
├── news_analysis.py
├── news_analysis_prompts.py
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py
│   ├── fred_adapter.py
│   ├── yahoo_adapter.py
│   ├── coingecko_adapter.py
│   └── news_adapters/
│       ├── __init__.py
│       ├── base_news_adapter.py
│       └── rss_adapter.py
├── data/
│   ├── cache/
│   └── validation_results/
├── logs/
└── tests/
    ├── test_adapters.py
    ├── test_validation.py
    └── test_end_to_end.py
```
