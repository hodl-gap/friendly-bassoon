"""Configuration for BTC Impact Module."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment from parent directory
PROJECT_ROOT = Path(__file__).parent
PARENT_DIR = PROJECT_ROOT.parent
load_dotenv(PARENT_DIR / ".env")

# Paths
DATA_DIR = PROJECT_ROOT / "data"
RELATIONSHIPS_FILE = DATA_DIR / "btc_relationships.json"
REGIME_STATE_FILE = DATA_DIR / "regime_state.json"

# Sibling subprojects
RETRIEVER_DIR = PARENT_DIR / "subproject_database_retriever"
DATA_COLLECTION_DIR = PARENT_DIR / "subproject_data_collection"
VARIABLE_MAPPER_DIR = PARENT_DIR / "subproject_variable_mapper"

# Model configuration
ANALYSIS_MODEL = "claude_sonnet"  # For impact analysis
EXTRACTION_MODEL = "claude_haiku"  # For variable extraction (Phase 2)

# Output settings
VERBOSE = os.getenv("BTC_IMPACT_VERBOSE", "false").lower() == "true"
OUTPUT_JSON = False  # Set via CLI --json flag

# Historical Event Detection (Phase 4)
ENABLE_HISTORICAL_EVENT_DETECTION = os.getenv("BTC_HISTORICAL_DETECTION", "true").lower() == "true"
HISTORICAL_DATE_BUFFER_DAYS = 7  # Days to add before/after detected event dates
MAX_INSTRUMENTS_PER_EVENT = 6  # Maximum instruments to fetch for historical event

# Knowledge Gap Detection (Phase 5)
ENABLE_GAP_FILLING = os.getenv("BTC_GAP_FILLING", "true").lower() == "true"  # Attempt to fill gaps with web search
MAX_GAP_SEARCHES = 6  # Maximum web searches to attempt for gap filling (covers all 6 gap categories)
MAX_ATTEMPTS_PER_GAP = 2  # Max attempts per gap (primary + 1 refinement)
