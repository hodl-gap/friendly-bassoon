"""
Data ID Format Utilities

Standardizes data_id format (SOURCE:SERIES) across all subprojects.

Format: "SOURCE:SERIES_ID" (e.g., "FRED:WTREGEN", "Yahoo:BTC-USD")

For backward compatibility, bare series IDs without source prefix
default to FRED (the most common source).
"""

from typing import Tuple, Optional


# Default source when no prefix is provided
DEFAULT_SOURCE = "FRED"


def parse_data_id(data_id: str) -> Tuple[str, str]:
    """
    Parse a data_id string into (source, series_id) tuple.

    Handles both formats:
    - "FRED:WTREGEN" -> ("FRED", "WTREGEN")
    - "WTREGEN" -> ("FRED", "WTREGEN")  # backward compatibility

    Args:
        data_id: Data ID string, with or without source prefix

    Returns:
        Tuple of (source, series_id)

    Examples:
        >>> parse_data_id("FRED:WTREGEN")
        ('FRED', 'WTREGEN')
        >>> parse_data_id("Yahoo:BTC-USD")
        ('Yahoo', 'BTC-USD')
        >>> parse_data_id("WTREGEN")
        ('FRED', 'WTREGEN')
        >>> parse_data_id("WorldBank:WDI")
        ('WorldBank', 'WDI')
    """
    if not data_id:
        return ("", "")

    data_id = data_id.strip()

    if ":" in data_id:
        parts = data_id.split(":", 1)
        source = parts[0].strip()
        series_id = parts[1].strip()
        return (source, series_id)
    else:
        # No prefix - default to FRED for backward compatibility
        return (DEFAULT_SOURCE, data_id)


def get_series_id(data_id: str) -> str:
    """
    Extract just the series ID from a data_id.

    Args:
        data_id: Data ID string (e.g., "FRED:WTREGEN" or "WTREGEN")

    Returns:
        The series ID without source prefix

    Examples:
        >>> get_series_id("FRED:WTREGEN")
        'WTREGEN'
        >>> get_series_id("WTREGEN")
        'WTREGEN'
    """
    _, series_id = parse_data_id(data_id)
    return series_id


def get_source(data_id: str) -> str:
    """
    Extract the source from a data_id.

    Args:
        data_id: Data ID string (e.g., "FRED:WTREGEN" or "WTREGEN")

    Returns:
        The source (defaults to FRED if not specified)

    Examples:
        >>> get_source("FRED:WTREGEN")
        'FRED'
        >>> get_source("Yahoo:BTC-USD")
        'Yahoo'
        >>> get_source("WTREGEN")
        'FRED'
    """
    source, _ = parse_data_id(data_id)
    return source


def format_data_id(source: str, series_id: str) -> str:
    """
    Create a canonical data_id from source and series_id.

    Args:
        source: Data source name (e.g., "FRED", "Yahoo")
        series_id: Series identifier (e.g., "WTREGEN", "BTC-USD")

    Returns:
        Canonical data_id in "SOURCE:SERIES" format

    Examples:
        >>> format_data_id("FRED", "WTREGEN")
        'FRED:WTREGEN'
        >>> format_data_id("Yahoo", "BTC-USD")
        'Yahoo:BTC-USD'
    """
    source = source.strip() if source else DEFAULT_SOURCE
    series_id = series_id.strip() if series_id else ""
    return f"{source}:{series_id}"


def is_valid_data_id(data_id: str) -> bool:
    """
    Check if a data_id is valid (has both source and series_id).

    Args:
        data_id: Data ID string to validate

    Returns:
        True if valid, False otherwise
    """
    if not data_id:
        return False
    source, series_id = parse_data_id(data_id)
    return bool(source) and bool(series_id)
