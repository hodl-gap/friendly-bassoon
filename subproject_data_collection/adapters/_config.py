"""
Data Collection config loaded via explicit file path.

All adapter files should import config values from here instead of bare
"from config import ...", which resolves to the wrong config.py when the
adapters package is imported cross-module (e.g., from subproject_database_retriever).
"""

import sys
import importlib.util
from pathlib import Path

_dc_root = Path(__file__).parent.parent
_project_root = _dc_root.parent

# Ensure project root is on sys.path (needed by config.py's shared.model_config import)
if str(_project_root) not in sys.path:
    sys.path.append(str(_project_root))

_spec = importlib.util.spec_from_file_location("_dc_config", str(_dc_root / "config.py"))
_dc_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dc_config)

# Re-export config values used by adapters
CACHE_DIR = _dc_config.CACHE_DIR
ENABLE_CACHE = _dc_config.ENABLE_CACHE
CACHE_EXPIRY_HOURS = _dc_config.CACHE_EXPIRY_HOURS
FRED_API_KEY = _dc_config.FRED_API_KEY
MAX_RETRIES = _dc_config.MAX_RETRIES
RETRY_DELAY_SECONDS = _dc_config.RETRY_DELAY_SECONDS
WEB_SEARCH_BACKEND = _dc_config.WEB_SEARCH_BACKEND
