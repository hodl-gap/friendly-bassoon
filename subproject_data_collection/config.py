"""
Configuration Management for Data Collection Subproject

Loads environment variables and defines configuration constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent
PARENT_DIR = Path(__file__).parent.parent

# Load .env from parent directory
env_path = PARENT_DIR / '.env'
load_dotenv(env_path)

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
VALIDATION_RESULTS_DIR = DATA_DIR / "validation_results"
LOGS_DIR = PROJECT_ROOT / "logs"

# Shared resources from other subprojects
DISCOVERED_DATA_IDS = PARENT_DIR / "subproject_variable_mapper" / "mappings" / "discovered_data_ids.json"
LIQUIDITY_METRICS_CSV = PARENT_DIR / "subproject_database_manager" / "data" / "processed" / "liquidity_metrics" / "liquidity_metrics_mapping.csv"

# =============================================================================
# API KEYS (from .env)
# =============================================================================

FRED_API_KEY = os.getenv("FRED_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")  # Optional: for NewsAPI.org

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# Models for different tasks
CLAIM_PARSING_MODEL = "claude_haiku"  # Fast, good for extraction
NEWS_ANALYSIS_MODEL = "claude_sonnet"  # Better reasoning for actionability
VALIDATION_INTERPRETATION_MODEL = "claude_haiku"  # Summarize stats

# Fallback model
FALLBACK_MODEL = "claude_sonnet"

# =============================================================================
# NEWS COLLECTION SETTINGS
# =============================================================================

# Default news sources (RSS feeds)
DEFAULT_NEWS_SOURCES = [
    "reuters_markets",
    "bloomberg_markets",
    "nikkei_markets"
]

# RSS feed URLs
RSS_FEEDS = {
    "reuters_markets": "https://www.reuters.com/markets/rss",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "nikkei_markets": "https://www.nikkei.com/rss/markets.xml",
    # Add more as needed
}

# Collection settings
DEFAULT_TIME_WINDOW_DAYS = 7
MAX_ARTICLES_PER_SOURCE = 50
MIN_RELEVANCE_SCORE = 0.6  # Minimum LLM relevance score to keep article

# =============================================================================
# DATA FETCHING SETTINGS
# =============================================================================

# Lookback period for historical data
DEFAULT_LOOKBACK_YEARS = 5

# Cache settings
CACHE_EXPIRY_HOURS = 24
ENABLE_CACHE = True

# API rate limiting
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

# =============================================================================
# VALIDATION SETTINGS
# =============================================================================

# Statistical thresholds
MIN_DATA_POINTS = 100  # Minimum for statistical significance
CORRELATION_SIGNIFICANCE_THRESHOLD = 0.05  # p-value threshold
LAG_SEARCH_RANGE_DAYS = 500  # Max lag to search for cross-correlation

# Validation status thresholds
CONFIRMED_THRESHOLD = 0.7  # Correlation >= this = confirmed
PARTIAL_THRESHOLD = 0.3  # Correlation >= this but < confirmed = partial

# =============================================================================
# FEATURE FLAGS
# =============================================================================

ENABLE_NEWS_COLLECTION = False  # Disabled - RSS sources not tested yet
ENABLE_CLAIM_VALIDATION = True
AUTO_DISCOVER_MISSING_DATA_IDS = True  # Auto-trigger discovery for unknown variables

# =============================================================================
# WEB SEARCH SETTINGS
# =============================================================================

# Web search adapter settings
WEB_SEARCH_BACKEND = os.getenv("WEB_SEARCH_BACKEND", "tavily")  # "tavily" or "duckduckgo"
WEB_SEARCH_MAX_RESULTS = 8  # Number of search results to fetch
WEB_SEARCH_DELAY_SECONDS = 1.0  # Delay between searches to avoid rate limiting
WEB_SEARCH_EXTRACTION_MODEL = "claude_haiku"  # Model for extraction (cheap)

# =============================================================================
# WEB CHAIN EXTRACTION SETTINGS
# =============================================================================

# On-the-fly logic chain extraction from trusted web sources
ENABLE_WEB_CHAIN_EXTRACTION = True  # Enable/disable web chain extraction feature
ENFORCE_TRUSTED_DOMAINS = True  # Only extract from trusted domains (Tier 1/2)
TRUSTED_DOMAIN_MIN_TIER = 1  # Minimum tier: 1 = Tier 1 only, 2 = include Tier 2
MAX_WEB_CHAINS_PER_QUERY = 5  # Maximum chains to extract per query
MIN_TRUSTED_SOURCES = 2  # Minimum trusted sources required to proceed
WEB_CHAIN_CONFIDENCE_WEIGHT = 0.7  # Confidence weight for web chains (vs 1.0 for DB chains)

# =============================================================================
# KNOWN DATA SOURCES
# =============================================================================

# Data source adapters and their capabilities
KNOWN_DATA_SOURCES = {
    "FRED": {
        "adapter": "fred_adapter",
        "requires_key": True,
        "base_url": "https://api.stlouisfed.org/fred",
        "rate_limit": 120,  # requests per minute
        "data_type": "time_series",
    },
    "Yahoo": {
        "adapter": "yahoo_adapter",
        "requires_key": False,
        "rate_limit": 2000,
        "data_type": "time_series",
    },
    "CoinGecko": {
        "adapter": "coingecko_adapter",
        "requires_key": False,
        "rate_limit": 50,  # free tier
        "data_type": "time_series",
    },
    "WebSearch": {
        "adapter": "web_search_adapter",
        "requires_key": False,
        "rate_limit": 60,  # be conservative with DuckDuckGo
        "data_type": "qualitative",  # extracts data points + announcements from web
    },
}

# =============================================================================
# INSTITUTION TYPES (for news analysis)
# =============================================================================

INSTITUTION_TYPES = [
    "pension_fund",
    "insurer",
    "asset_manager",
    "central_bank",
    "sovereign_wealth",
    "hedge_fund",
    "bank",
    "other"
]

ACTION_TYPES = [
    "rebalancing",
    "accumulating",
    "divesting",
    "hedging",
    "other"
]
