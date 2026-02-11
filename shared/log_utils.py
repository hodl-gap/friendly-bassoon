"""
Standardized logging helper.

Convention: [subproject.module] prefix in lowercase.
Examples: [retriever.gap_detector], [btc.impact_analysis]
"""


def log(module: str, message: str):
    """Print a log message with standardized prefix."""
    print(f"[{module}] {message}")
