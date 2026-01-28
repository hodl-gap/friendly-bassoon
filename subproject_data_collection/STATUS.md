# Data Collection Subproject - Status

**IMPORTANT**: Read `CLAUDE.md` first for project guidelines and patterns.

**Last Updated**: 2026-01-28

## Current State: Implementation Complete

### Completed
- [x] Phase 1: Foundation files (CLAUDE.md, STATUS.md, states.py, config.py, orchestrator)
- [x] Phase 2: Data adapters (base, FRED, Yahoo, CoinGecko, WebSearch)
- [x] Phase 3: Claim validation path (parsing, fetching, validation, output)
- [x] Phase 4: News collection path (RSS adapter, collection, analysis)
- [x] Phase 5: Tests and data directories
- [x] Phase 6: Institutional allocation scrapers

### Ready for Testing
- All modules implemented
- Unit tests created in `tests/`
- Integration testing needed with actual API calls
- Institutional scrapers ready for live testing

---

## Implementation Summary

### Phase 1: Foundation
| File | Purpose | Status |
|------|---------|--------|
| `CLAUDE.md` | Architecture documentation | ✅ |
| `STATUS.md` | Progress tracking | ✅ |
| `states.py` | LangGraph state definitions | ✅ |
| `config.py` | Configuration management | ✅ |
| `data_collection_orchestrator.py` | Main orchestrator with routing | ✅ |

### Phase 2: Data Adapters
| File | Purpose | Status |
|------|---------|--------|
| `adapters/__init__.py` | Package exports | ✅ |
| `adapters/base_adapter.py` | Abstract interface | ✅ |
| `adapters/fred_adapter.py` | FRED API | ✅ |
| `adapters/yahoo_adapter.py` | Yahoo Finance | ✅ |
| `adapters/coingecko_adapter.py` | CoinGecko | ✅ |
| `adapters/web_search_adapter.py` | Web search + LLM extraction | ✅ (NEW) |
| `web_search_prompts.py` | Extraction prompts | ✅ (NEW) |

### Phase 3: Claim Validation Path
| File | Purpose | Status |
|------|---------|--------|
| `claim_parsing.py` | Parse claims from synthesis | ✅ |
| `claim_parsing_prompts.py` | Extraction prompts | ✅ |
| `data_fetching.py` | Fetch via adapters | ✅ |
| `validation_logic.py` | Statistical validation | ✅ |
| `validation_prompts.py` | Result interpretation | ✅ |
| `output_formatter.py` | Format final output | ✅ |

### Phase 4: News Collection Path
| File | Purpose | Status |
|------|---------|--------|
| `adapters/news_adapters/__init__.py` | Package exports | ✅ |
| `adapters/news_adapters/base_news_adapter.py` | Abstract news interface | ✅ |
| `adapters/news_adapters/rss_adapter.py` | RSS feed adapter | ✅ |
| `news_collection.py` | Collect from sources | ✅ |
| `news_collection_prompts.py` | Relevance prompts | ✅ |
| `news_analysis.py` | Analyze actionability | ✅ |
| `news_analysis_prompts.py` | Analysis prompts | ✅ |

### Phase 5: Tests & Infrastructure
| File/Dir | Purpose | Status |
|----------|---------|--------|
| `tests/__init__.py` | Test package | ✅ |
| `tests/test_adapters.py` | Adapter unit tests | ✅ |
| `tests/test_validation.py` | Validation logic tests | ✅ |
| `tests/test_end_to_end.py` | Full workflow tests | ✅ |
| `data/cache/` | Cached API responses | ✅ |
| `data/validation_results/` | Output storage | ✅ |
| `logs/` | Debug logs | ✅ |

### Phase 6: Institutional Allocation Scrapers
| File | Purpose | Status |
|------|---------|--------|
| `adapters/institutional/__init__.py` | Package exports | ✅ |
| `adapters/institutional/base_scraper.py` | Abstract scraper interface | ✅ |
| `adapters/institutional/storage.py` | JSON file storage | ✅ |
| `adapters/institutional/scheduler.py` | APScheduler scheduling | ✅ |
| `adapters/institutional/scraper_config.py` | Schedule config | ✅ |
| `adapters/institutional/run_scrapers.py` | CLI runner | ✅ |
| **Fund Manager Scrapers** | | |
| `fund_manager/ici_scraper.py` | ICI weekly fund flows | ✅ |
| `fund_manager/aaii_sentiment_scraper.py` | AAII sentiment survey | ✅ |
| `fund_manager/aaii_allocation_scraper.py` | AAII asset allocation | ✅ |
| `fund_manager/bofa_fms_scraper.py` | BofA FMS (web search) | ✅ |
| **Insurer Scrapers** | | |
| `insurer/naic_scraper.py` | NAIC industry snapshots | ✅ |
| `insurer/acli_scraper.py` | ACLI fact book (PDF) | ✅ |
| `insurer/blackrock_insurance_scraper.py` | BlackRock report | ✅ |
| **Japan Scrapers** | | |
| `japan/boj_iip_scraper.py` | BOJ Int'l Investment Position | ✅ |
| `japan/boj_timeseries_scraper.py` | BOJ time-series data | ✅ |
| `japan/japan_insurer_news_scraper.py` | Japan insurer news | ✅ |
| **Data Storage** | | |
| `data/scraped/fund_manager/` | Fund manager data | ✅ |
| `data/scraped/insurer/` | Insurer data | ✅ |
| `data/scraped/japan/` | Japan data | ✅ |

---

## Architecture

```
data_collection_orchestrator.py (MAIN ENTRY POINT)
    │
    ├── mode="claim_validation"
    │   ├── claim_parsing.py        → Parse claims from synthesis
    │   ├── data_fetching.py        → Fetch via adapters
    │   │   ├── adapters/fred_adapter.py      (time series)
    │   │   ├── adapters/yahoo_adapter.py     (time series)
    │   │   ├── adapters/coingecko_adapter.py (time series)
    │   │   └── adapters/web_search_adapter.py (qualitative - data points + announcements)
    │   ├── validation_logic.py     → Statistical validation
    │   └── output_formatter.py     → Format results
    │
    ├── mode="news_collection"
    │   ├── news_collection.py      → Collect from RSS feeds
    │   │   └── adapters/news_adapters/rss_adapter.py
    │   ├── news_analysis.py        → LLM analysis for actionability
    │   └── output_formatter.py     → Format results + retriever queries
    │
    └── adapters/institutional/     → Scheduled data collection (standalone)
        ├── run_scrapers.py         → CLI runner (--all, --scraper, --daemon)
        ├── fund_manager/           → ICI, AAII, BofA FMS
        ├── insurer/                → NAIC, ACLI, BlackRock
        └── japan/                  → BOJ IIP, BOJ Time-Series, News
```

---

## Usage

```bash
# Claim validation mode
python data_collection_orchestrator.py --mode claim_validation --input "synthesis text..."

# News collection mode
python data_collection_orchestrator.py --mode news_collection --input "Japanese insurers rebalancing" --days 7

# Run tests
python tests/test_adapters.py
python tests/test_validation.py
python tests/test_end_to_end.py
```

---

## Dependencies

### Python Packages
```
yfinance>=0.2.0           # Yahoo Finance
fredapi>=0.5.0            # FRED API (optional, using requests)
pycoingecko>=3.1.0        # CoinGecko
feedparser>=6.0.0         # RSS parsing
scipy>=1.10.0             # Statistical functions
pandas>=2.0.0             # Time series handling
numpy>=1.24.0             # Numerical operations
langgraph>=0.0.50         # Workflow orchestration
duckduckgo-search>=6.0.0  # Web search
requests>=2.31.0          # HTTP requests
beautifulsoup4>=4.12.0    # HTML parsing
openpyxl>=3.1.0           # Excel reading
pdfplumber>=0.10.0        # PDF extraction (for ACLI, BlackRock)
apscheduler>=3.10.0       # Scheduling (for daemon mode)
```

### External APIs / Data Sources
- FRED API (requires free API key from `.env`)
- Yahoo Finance (free, no key required)
- CoinGecko (free tier: 10-50 calls/min)
- RSS feeds (free, no auth) - DISABLED pending testing
- DuckDuckGo Search (free, no key required)
- ICI.org (free, no auth)
- AAII.com (free, some features require membership)
- BOJ stat-search (free, no auth)
- NAIC.org (free, no auth)
- ACLI.com (free PDF download)
- BlackRock.com (free PDF download)

---

## TODO / Next Steps

### Integration Testing
- [ ] Test with real API keys
- [ ] Verify FRED adapter with actual data
- [ ] Test Yahoo Finance fetching
- [ ] Test CoinGecko rate limiting
- [ ] Verify RSS feed parsing with live feeds

### Enhancements (Future)
- [ ] Add caching layer for API responses
- [ ] Add more news sources beyond RSS
- [ ] Implement batch validation for efficiency
- [ ] Add database storage for validation results

---

## Configuration

See `config.py` for all settings:
- Model settings (claude_haiku for parsing, claude_sonnet for analysis)
- API settings (FRED_API_KEY, cache expiry)
- Feature flags (ENABLE_NEWS_COLLECTION, ENABLE_CLAIM_VALIDATION)
- Paths to shared resources from other subprojects

See `adapters/institutional/scraper_config.py` for scraper schedules:
- Fund manager scrapers: weekly/monthly
- Insurer scrapers: quarterly checks for annual data
- Japan scrapers: daily/weekly/monthly

### Scraper Schedule Overview
| Scraper | Frequency | Day/Time |
|---------|-----------|----------|
| ici_flows | Weekly | Friday 18:00 |
| aaii_sentiment | Weekly | Thursday 12:00 |
| aaii_allocation | Monthly | 1st, 10:00 |
| bofa_fms | Monthly | 15th, 10:00 |
| naic | Quarterly | Jan/Apr/Jul/Oct 1st |
| acli | Quarterly | Jan/Apr/Jul/Oct 1st |
| blackrock_insurance | Quarterly | Jan/Apr/Jul/Oct 1st |
| boj_iip | Monthly | 1st, 09:00 |
| boj_timeseries | Weekly | Monday 09:00 |
| japan_insurer_news | Daily | 08:00 |
