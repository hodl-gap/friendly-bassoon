"""
Shared utilities package for execution_only_test project.

Provides common utilities used across subprojects:
- schemas: Canonical LogicChain, ConfidenceMetadata types
- paths: PROJECT_ROOT, SUBPROJECTS
- model_config: Central model selection
- log_utils: Standardized logging
- data_id_utils: Data ID format parsing (SOURCE:SERIES)
- variable_resolver: Centralized variable to data source resolution
- integration: Cross-subproject wiring (Mapper → Collection)
"""

import sys
from dotenv import load_dotenv

# Centralized path setup
from .paths import PROJECT_ROOT, SUBPROJECTS

# Load .env once from project root
load_dotenv(PROJECT_ROOT / '.env')

# Ensure project root is on path (for models.py access)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Canonical schemas
from .schemas import (
    LogicChainStep,
    LogicChain,
    ConfidenceMetadata,
)

# Model config
from .model_config import (
    EXTRACTION_MODEL,
    ANALYSIS_MODEL,
    RERANK_MODEL,
    FALLBACK_MODEL,
    IMPACT_ANALYSIS_MODEL,
)

# Log utility
from .log_utils import log

# Data ID utilities
from .data_id_utils import (
    parse_data_id,
    get_series_id,
    get_source,
    format_data_id,
)

# Variable resolver
from .variable_resolver import (
    resolve_variable,
    load_mappings,
    get_all_mappings,
    list_known_variables,
)

# State snapshot utility
from .snapshot import snapshot_state, start_run, ENABLE_SNAPSHOTS
