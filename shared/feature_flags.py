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
    return _env_int("DATA_GROUNDING_MAX_ITER", 5)


def historical_max_iterations() -> int:
    return _env_int("HISTORICAL_MAX_ITER", 4)


def edf_enabled() -> bool:
    """Enable EDF (Epistemic Decomposition Framework) as Phase 0 of retrieval.

    When enabled, an Opus call decomposes the query into a structured knowledge
    tree before retrieval begins, replacing generic query expansion with
    targeted 7-dimension search planning.

    Toggle: EDF_ENABLED=0 to disable (default: enabled)
    """
    val = os.environ.get("EDF_ENABLED", "1")
    return val.strip().lower() not in ("0", "false", "no")


def step_mode_enabled() -> bool:
    """Enable step-by-step execution mode for agentic phases.

    When enabled, the agent loop pauses after each LLM decision and after
    each tool execution, displaying full reasoning and results for inspection.
    The user presses Enter to advance each step.

    Toggle: STEP_MODE=1 python run_case_study.py --case 1 --run 1
    Or:     python run_case_study.py --case 1 --run 1 --step
    """
    val = os.environ.get("STEP_MODE", "0")
    return val.strip().lower() not in ("0", "false", "no", "")
