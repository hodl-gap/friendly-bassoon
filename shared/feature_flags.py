"""Configuration for agentic pipeline iteration limits.

Tunable via environment variables:
    RETRIEVAL_MAX_ITER=5 python run_case_study.py --case 4 --run 1
    DATA_GROUNDING_MAX_ITER=6 python run_case_study.py --case 4 --run 1
"""

import os


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def retrieval_max_iterations() -> int:
    return _env_int("RETRIEVAL_MAX_ITER", 5)


def data_grounding_max_iterations() -> int:
    return _env_int("DATA_GROUNDING_MAX_ITER", 4)


def historical_max_iterations() -> int:
    return _env_int("HISTORICAL_MAX_ITER", 4)
