"""
Configuration Management for Variable Mapper

Loads environment variables and provides configuration constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from shared.model_config import EXTRACTION_MODEL as _EXTRACTION_MODEL, FALLBACK_MODEL as _FALLBACK_MODEL

# Load .env from parent directory
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# File paths
PROJECT_ROOT = Path(__file__).parent
PARENT_DIR = Path(__file__).parent.parent

# Reference files from database_manager
LIQUIDITY_METRICS_CSV = PARENT_DIR / "subproject_database_manager" / "data" / "processed" / "liquidity_metrics" / "liquidity_metrics_mapping.csv"

# Sample input for testing
SAMPLE_INPUT_FILE = PARENT_DIR / "subproject_database_retriever" / "tests" / "query_result.md"

# Model settings
EXTRACTION_MODEL = _EXTRACTION_MODEL
FALLBACK_MODEL = _FALLBACK_MODEL

# Processing settings
MAX_VARIABLES_PER_EXTRACTION = 50  # Reasonable limit for a single synthesis

# Bug logging
BUGS_LOG_FILE = PROJECT_ROOT / "LIQUIDITY_METRICS_BUGS.md"

# Step-specific model settings
NORMALIZATION_MODEL = _EXTRACTION_MODEL
CHAIN_PARSING_MODEL = _EXTRACTION_MODEL

# Combined extraction settings (Optimization: merge Steps 1 & 3)
USE_COMBINED_EXTRACTION = True  # If True, Step 1 extracts both explicit AND implicit variables (skips Step 3)
BATCH_CHAIN_PARSING = True  # If True and USE_COMBINED_EXTRACTION=False, batch all chains in single LLM call

# Data ID Discovery settings
DISCOVERED_MAPPINGS_FILE = PROJECT_ROOT / "mappings" / "discovered_data_ids.json"
AUTO_DISCOVER = False  # Auto-trigger discovery for unmapped variables (disabled for faster testing)

# Known data APIs for discovery
KNOWN_DATA_APIS = [
    {
        "name": "FRED",
        "base_url": "https://api.stlouisfed.org/fred",
        "docs_url": "https://fred.stlouisfed.org/docs/api/fred/",
        "requires_key": True,
        "key_env_var": "FRED_API_KEY"
    },
    {
        "name": "World Bank",
        "base_url": "https://api.worldbank.org/v2",
        "docs_url": "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
        "requires_key": False
    },
    {
        "name": "BLS",
        "base_url": "https://api.bls.gov/publicAPI/v2",
        "docs_url": "https://www.bls.gov/developers/",
        "requires_key": True,
        "key_env_var": "BLS_API_KEY"
    },
    {
        "name": "OECD",
        "base_url": "https://stats.oecd.org/restsdmx/sdmx.ashx",
        "docs_url": "https://data.oecd.org/api/",
        "requires_key": False
    },
    {
        "name": "IMF",
        "base_url": "https://dataservices.imf.org/REST/SDMX_JSON.svc",
        "docs_url": "https://datahelp.imf.org/knowledgebase/articles/667681",
        "requires_key": False
    }
]
