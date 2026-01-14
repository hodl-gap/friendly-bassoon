"""
Configuration Management for Variable Mapper

Loads environment variables and provides configuration constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

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
EXTRACTION_MODEL = "gpt5_mini"  # Primary model for variable extraction
FALLBACK_MODEL = "claude_sonnet"  # Fallback if primary fails

# Processing settings
MAX_VARIABLES_PER_EXTRACTION = 50  # Reasonable limit for a single synthesis

# Bug logging
BUGS_LOG_FILE = PROJECT_ROOT / "LIQUIDITY_METRICS_BUGS.md"

# Step-specific model settings
NORMALIZATION_MODEL = "claude_haiku"  # Fast, simple matching task
CHAIN_PARSING_MODEL = "gpt5_mini"     # Good for structured extraction

# Data ID Discovery settings
DISCOVERED_MAPPINGS_FILE = PROJECT_ROOT / "mappings" / "discovered_data_ids.json"
AUTO_DISCOVER = True  # Auto-trigger discovery for unmapped variables

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
