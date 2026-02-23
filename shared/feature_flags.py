"""Feature flags for the hybrid pipeline.

All flags default to False (old pipeline). Enable via environment variables:
    AGENT_RETRIEVAL=true python run_case_study.py --case 4 --run 1
    USE_HYBRID_PIPELINE=true python run_case_study.py --case 4 --run 1
    python run_case_study.py --case 4 --run 1 --hybrid
"""

import os


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def is_agentic_retrieval() -> bool:
    return _env_bool("AGENT_RETRIEVAL") or _env_bool("USE_HYBRID_PIPELINE")


def is_agentic_data_grounding() -> bool:
    return _env_bool("AGENT_DATA_GROUNDING") or _env_bool("USE_HYBRID_PIPELINE")


def is_agentic_historical() -> bool:
    return _env_bool("AGENT_HISTORICAL") or _env_bool("USE_HYBRID_PIPELINE")


def is_synthesis_self_check() -> bool:
    return _env_bool("AGENT_SYNTHESIS_CHECK") or _env_bool("USE_HYBRID_PIPELINE")


def retrieval_max_iterations() -> int:
    return _env_int("RETRIEVAL_MAX_ITER", 5)


def data_grounding_max_iterations() -> int:
    return _env_int("DATA_GROUNDING_MAX_ITER", 4)


def historical_max_iterations() -> int:
    return _env_int("HISTORICAL_MAX_ITER", 4)
