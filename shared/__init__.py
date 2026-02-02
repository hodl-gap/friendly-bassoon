"""
Shared utilities package for execution_only_test project.

Provides common utilities used across subprojects:
- data_id_utils: Data ID format parsing (SOURCE:SERIES)
- variable_resolver: Centralized variable to data source resolution
- integration: Cross-subproject wiring (Mapper → Collection)
"""

from .data_id_utils import (
    parse_data_id,
    get_series_id,
    get_source,
    format_data_id,
)

from .variable_resolver import (
    resolve_variable,
    load_mappings,
    get_all_mappings,
    list_known_variables,
)
