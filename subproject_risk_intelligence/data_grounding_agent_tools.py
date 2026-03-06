"""Tool schemas and handlers for the data grounding agent."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from .states import RiskImpactState


# =============================================================================
# Tool Schemas
# =============================================================================

EXTRACT_VARIABLES_TOOL = {
    "name": "extract_variables",
    "description": "Extract normalized variable names from research chains and synthesis text. Returns list of variables that should be fetched.",
    "input_schema": {
        "type": "object",
        "properties": {
            "notes": {
                "type": "string",
                "description": "Optional notes about what to focus on"
            }
        },
    }
}

FETCH_VARIABLE_DATA_TOOL = {
    "name": "fetch_variable_data",
    "description": "Fetch current market data for a specific variable from FRED, Yahoo Finance, or local CSV series. Returns current value, date, and period-over-period changes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "variable_name": {
                "type": "string",
                "description": "Normalized variable name (e.g., 'us10y', 'vix', 'sp500', 'fed_funds')"
            },
            "source": {
                "type": "string",
                "enum": ["fred", "yahoo", "csv", "auto"],
                "description": "Data source. Use 'auto' to let the system resolve (default).",
                "default": "auto"
            }
        },
        "required": ["variable_name"]
    }
}

VALIDATE_CLAIM_TOOL = {
    "name": "validate_claim",
    "description": "Validate a specific quantitative claim DERIVED FROM RESEARCH against actual data. Tests correlation and statistical significance. Only use for research-derived claims (e.g., 'BTC follows gold with 63-428 day lag'). Do NOT validate numbers from the trader's original query — those are ground truth input data, not claims.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claim_text": {
                "type": "string",
                "description": "The quantitative claim to validate (e.g., 'BTC follows gold with 63-428 day lag')"
            }
        },
        "required": ["claim_text"]
    }
}

COMPUTE_DERIVED_TOOL = {
    "name": "compute_derived",
    "description": "Compute derived macro metrics (term premium, real yield, credit spreads, etc.) from already-fetched raw data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "notes": {
                "type": "string",
                "description": "Optional notes"
            }
        },
    }
}

COMPUTE_CORRELATION_TOOL = {
    "name": "compute_correlation",
    "description": "Compute return correlation between two variables over a specified window. Use this to verify coupling/decoupling claims (e.g., 'KOSPI moved in tandem with Nikkei during the selloff'). Fetches price history for both variables, computes daily returns, and calculates Pearson correlation over the window.",
    "input_schema": {
        "type": "object",
        "properties": {
            "variable_a": {
                "type": "string",
                "description": "First variable name (e.g., 'kospi', 'ewy', 'nikkei')"
            },
            "variable_b": {
                "type": "string",
                "description": "Second variable name (e.g., 'nikkei', 'ewt', 'sp500')"
            },
            "window_days": {
                "type": "integer",
                "description": "Lookback window in calendar days for correlation calculation. Use 5-10 for event-specific coupling, 30 for short-term, 90 for medium-term.",
                "default": 30
            }
        },
        "required": ["variable_a", "variable_b"]
    }
}

FINISH_GROUNDING_TOOL = {
    "name": "finish_grounding",
    "description": "Signal that data grounding is complete. Call after all variables are fetched and validated.",
    "input_schema": {
        "type": "object",
        "properties": {
            "variables_fetched": {
                "type": "integer",
                "description": "Number of variables successfully fetched"
            },
            "patterns_validated": {
                "type": "integer",
                "description": "Number of patterns validated"
            },
            "summary": {
                "type": "string",
                "description": "Brief summary of data grounding results"
            }
        },
        "required": ["summary"]
    }
}

ALL_TOOLS = [
    EXTRACT_VARIABLES_TOOL,
    FETCH_VARIABLE_DATA_TOOL,
    VALIDATE_CLAIM_TOOL,
    COMPUTE_DERIVED_TOOL,
    COMPUTE_CORRELATION_TOOL,
    FINISH_GROUNDING_TOOL,
]


# =============================================================================
# Tool Handlers
# =============================================================================

class DataGroundingAgentState:
    """Mutable state for data grounding agent."""

    def __init__(self, state: RiskImpactState):
        self.state = state
        self.extracted_variables = []
        self.current_values = {}
        self.claim_validation_results = []
        self.fetch_errors = []


def build_tool_handlers(agent_state: DataGroundingAgentState) -> dict:
    """Build tool handler dict bound to agent state."""

    def handle_extract_variables(notes: str = "") -> dict:
        from .variable_extraction import extract_variables
        result_state = extract_variables(dict(agent_state.state))
        agent_state.extracted_variables = result_state.get("extracted_variables", [])
        agent_state.state["extracted_variables"] = agent_state.extracted_variables

        var_names = [v.get("normalized", v.get("raw", "?")) for v in agent_state.extracted_variables]
        return {
            "count": len(agent_state.extracted_variables),
            "variables": var_names[:20],
        }

    def handle_fetch_variable_data(variable_name: str, source: str = "auto") -> dict:
        from .current_data_fetcher import (
            resolve_variable, fetch_fred_with_history, fetch_yahoo_with_history,
            fetch_csv_with_history,
            calculate_changes, MONTHLY_FRED_SERIES, MONTHLY_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS,
        )

        resolved = resolve_variable(variable_name)
        if not resolved:
            agent_state.fetch_errors.append(variable_name)
            return {"error": f"Could not resolve variable: {variable_name}"}

        series_id = resolved["series_id"]
        data_source = resolved["source"]
        # Use extended lookback for monthly FRED series (GDP, CPI, etc.)
        lookback = MONTHLY_LOOKBACK_DAYS if series_id in MONTHLY_FRED_SERIES else DEFAULT_LOOKBACK_DAYS

        try:
            if data_source.upper() == "FRED":
                data = fetch_fred_with_history(series_id, lookback)
            elif data_source.upper() == "CSV":
                data = fetch_csv_with_history(series_id, lookback)
            else:
                data = fetch_yahoo_with_history(series_id, lookback)

            if data and data.get("value") is not None:
                history = data.pop("history", [])
                changes = calculate_changes(history)
                data["changes"] = changes
                agent_state.current_values[variable_name] = data

                # Build compact change summary for agent
                change_summary = []
                for period in ["change_1w", "change_1m", "change_3m", "change_6m"]:
                    c = changes.get(period)
                    if c:
                        label = period.replace("change_", "")
                        change_summary.append(f"{c['direction']}{abs(c['percentage']):.1f}% {label}")
                pct = changes.get("percentile_1y")
                if pct is not None:
                    change_summary.append(f"{pct:.0f}th pct 1y")

                return {
                    "variable": variable_name,
                    "value": data["value"],
                    "date": data.get("date", ""),
                    "source": data_source,
                    "series_id": series_id,
                    "changes": ", ".join(change_summary) if change_summary else "",
                }
            else:
                agent_state.fetch_errors.append(variable_name)
                return {"error": f"No data returned for {variable_name} ({series_id})"}
        except Exception as e:
            agent_state.fetch_errors.append(variable_name)
            return {"error": f"Fetch failed for {variable_name}: {str(e)}"}

    def handle_validate_claim(claim_text: str) -> dict:
        try:
            from . import config as risk_config
            import sys
            dc_path = str(risk_config.DATA_COLLECTION_DIR)
            saved_config = sys.modules.pop("config", None)
            saved_states = sys.modules.pop("states", None)
            if dc_path not in sys.path:
                sys.path.insert(0, dc_path)

            from subproject_data_collection.data_collection_orchestrator import run_claim_validation

            if saved_config is not None:
                sys.modules["config"] = saved_config
            if saved_states is not None:
                sys.modules["states"] = saved_states

            result = run_claim_validation(synthesis_text=claim_text)
            final_output = result.get("final_output", {})
            validation_results = final_output.get("results", [])
            agent_state.claim_validation_results.extend(validation_results)

            return {
                "claims_validated": len(validation_results),
                "results": [
                    {
                        "claim": r.get("claim", ""),
                        "status": r.get("status", "unknown"),
                        "correlation": r.get("actual_correlation"),
                    }
                    for r in validation_results[:5]
                ],
            }
        except Exception as e:
            return {"error": f"Claim validation failed: {str(e)}"}

    def handle_compute_derived(notes: str = "") -> dict:
        from .current_data_fetcher import compute_derived_metrics

        derived = compute_derived_metrics(agent_state.current_values)
        agent_state.current_values.update(derived)

        return {
            "derived_count": len(derived),
            "metrics": {
                k: {"value": v.get("value"), "source": "derived"}
                for k, v in derived.items()
            },
        }

    def handle_compute_correlation(variable_a: str, variable_b: str, window_days: int = 30) -> dict:
        from .current_data_fetcher import (
            resolve_variable, fetch_fred_with_history, fetch_yahoo_with_history,
            fetch_csv_with_history,
            MONTHLY_FRED_SERIES, MONTHLY_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS,
        )
        from datetime import datetime, timedelta
        import math

        def _fetch_history(var_name: str) -> list:
            resolved = resolve_variable(var_name)
            if not resolved:
                return []
            series_id = resolved["series_id"]
            source = resolved["source"]
            lookback = max(window_days + 30, DEFAULT_LOOKBACK_DAYS)
            if source.upper() == "FRED":
                data = fetch_fred_with_history(series_id, lookback)
            elif source.upper() == "CSV":
                data = fetch_csv_with_history(series_id, lookback)
            else:
                data = fetch_yahoo_with_history(series_id, lookback)
            if data and data.get("history"):
                return data["history"]  # list of (date_str, value)
            return []

        hist_a = _fetch_history(variable_a)
        hist_b = _fetch_history(variable_b)

        if not hist_a:
            return {"error": f"Could not fetch history for {variable_a}"}
        if not hist_b:
            return {"error": f"Could not fetch history for {variable_b}"}

        # Build date->value dicts
        dict_a = {d: v for d, v in hist_a}
        dict_b = {d: v for d, v in hist_b}

        # Find common dates within the window
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        common_dates = sorted(d for d in dict_a if d in dict_b and d >= cutoff)

        if len(common_dates) < 3:
            return {"error": f"Not enough overlapping data points ({len(common_dates)}) in {window_days}-day window"}

        # Compute daily returns for common dates
        returns_a = []
        returns_b = []
        dates_used = []
        for i in range(1, len(common_dates)):
            prev_d = common_dates[i - 1]
            curr_d = common_dates[i]
            va_prev, va_curr = dict_a[prev_d], dict_a[curr_d]
            vb_prev, vb_curr = dict_b[prev_d], dict_b[curr_d]
            if va_prev != 0 and vb_prev != 0:
                returns_a.append((va_curr - va_prev) / va_prev)
                returns_b.append((vb_curr - vb_prev) / vb_prev)
                dates_used.append(curr_d)

        n = len(returns_a)
        if n < 2:
            return {"error": f"Not enough return observations ({n}) for correlation"}

        # Pearson correlation
        mean_a = sum(returns_a) / n
        mean_b = sum(returns_b) / n
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(returns_a, returns_b)) / n
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in returns_a) / n)
        std_b = math.sqrt(sum((b - mean_b) ** 2 for b in returns_b) / n)

        if std_a == 0 or std_b == 0:
            return {"error": "Zero variance in one of the series — correlation undefined"}

        corr = cov / (std_a * std_b)

        # t-statistic for significance
        if abs(corr) < 1.0:
            t_stat = corr * math.sqrt((n - 2) / (1 - corr ** 2))
        else:
            t_stat = float('inf')

        # Cumulative returns over the window
        cum_a = (dict_a[common_dates[-1]] / dict_a[common_dates[0]] - 1) * 100
        cum_b = (dict_b[common_dates[-1]] / dict_b[common_dates[0]] - 1) * 100

        return {
            "variable_a": variable_a,
            "variable_b": variable_b,
            "window_days": window_days,
            "correlation": round(corr, 4),
            "t_statistic": round(t_stat, 2),
            "observations": n,
            "date_range": f"{dates_used[0]} to {dates_used[-1]}",
            "cumulative_return_a": f"{cum_a:+.2f}%",
            "cumulative_return_b": f"{cum_b:+.2f}%",
            "interpretation": (
                "strong positive" if corr > 0.7 else
                "moderate positive" if corr > 0.4 else
                "weak positive" if corr > 0.1 else
                "negligible" if corr > -0.1 else
                "weak negative" if corr > -0.4 else
                "moderate negative" if corr > -0.7 else
                "strong negative"
            ),
        }

    def handle_finish_grounding(summary: str = "", variables_fetched: int = 0, patterns_validated: int = 0) -> dict:
        return {"status": "completed", "summary": summary}

    return {
        "extract_variables": handle_extract_variables,
        "fetch_variable_data": handle_fetch_variable_data,
        "validate_claim": handle_validate_claim,
        "compute_derived": handle_compute_derived,
        "compute_correlation": handle_compute_correlation,
        "finish_grounding": handle_finish_grounding,
    }
