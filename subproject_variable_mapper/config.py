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
