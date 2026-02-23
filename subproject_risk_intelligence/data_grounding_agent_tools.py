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
    "description": "Fetch current market data for a specific variable from FRED or Yahoo Finance. Returns current value, date, and period-over-period changes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "variable_name": {
                "type": "string",
                "description": "Normalized variable name (e.g., 'us10y', 'vix', 'sp500', 'fed_funds')"
            },
            "source": {
                "type": "string",
                "enum": ["fred", "yahoo", "auto"],
                "description": "Data source. Use 'auto' to let the system resolve (default).",
                "default": "auto"
            }
        },
        "required": ["variable_name"]
    }
}

VALIDATE_CLAIM_TOOL = {
    "name": "validate_claim",
    "description": "Validate a specific quantitative claim from the synthesis against actual data. Tests correlation and statistical significance.",
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

VALIDATE_PATTERNS_TOOL = {
    "name": "validate_patterns",
    "description": "Extract quantitative patterns from research and validate against current data. Returns triggered/not-triggered for each pattern.",
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
    VALIDATE_PATTERNS_TOOL,
    COMPUTE_DERIVED_TOOL,
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
        self.validated_patterns = []
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
        from .current_data_fetcher import resolve_variable, fetch_fred_with_history, fetch_yahoo_with_history

        resolved = resolve_variable(variable_name)
        if not resolved:
            agent_state.fetch_errors.append(variable_name)
            return {"error": f"Could not resolve variable: {variable_name}"}

        series_id = resolved["series_id"]
        data_source = resolved["source"]

        try:
            if data_source == "fred":
                data = fetch_fred_with_history(series_id)
            else:
                data = fetch_yahoo_with_history(series_id)

            if data and data.get("value") is not None:
                agent_state.current_values[variable_name] = {
                    "value": data["value"],
                    "date": data.get("date", ""),
                    "source": data_source,
                    "series_id": series_id,
                    "history": data.get("history", []),
                }
                return {
                    "variable": variable_name,
                    "value": data["value"],
                    "date": data.get("date", ""),
                    "source": data_source,
                    "series_id": series_id,
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
            saved_states = sys.modules.pop("states", None)
            if dc_path not in sys.path:
                sys.path.insert(0, dc_path)

            from subproject_data_collection.data_collection_orchestrator import run_claim_validation

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

    def handle_validate_patterns(notes: str = "") -> dict:
        from .pattern_validator import validate_patterns

        # Build state with current values for pattern validation
        temp_state = dict(agent_state.state)
        temp_state["current_values"] = agent_state.current_values
        result_state = validate_patterns(temp_state)

        agent_state.validated_patterns = result_state.get("validated_patterns", [])

        return {
            "patterns_found": len(agent_state.validated_patterns),
            "patterns": [
                {
                    "pattern": p.get("pattern_description", "")[:100],
                    "triggered": p.get("triggered", False),
                    "current_value": p.get("current_value"),
                }
                for p in agent_state.validated_patterns[:10]
            ],
        }

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

    def handle_finish_grounding(summary: str = "", variables_fetched: int = 0, patterns_validated: int = 0) -> dict:
        return {"status": "completed", "summary": summary}

    return {
        "extract_variables": handle_extract_variables,
        "fetch_variable_data": handle_fetch_variable_data,
        "validate_claim": handle_validate_claim,
        "validate_patterns": handle_validate_patterns,
        "compute_derived": handle_compute_derived,
        "finish_grounding": handle_finish_grounding,
    }
