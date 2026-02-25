"""Tool schemas and handlers for the historical context agent."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from .states import RiskImpactState


# =============================================================================
# Tool Schemas
# =============================================================================

DETECT_ANALOGS_TOOL = {
    "name": "detect_analogs",
    "description": "Detect up to 5 historical analogs for the current event by extracting events explicitly mentioned in retrieved research context. Returns analog descriptions with relevance scores.",
    "input_schema": {
        "type": "object",
        "properties": {
            "max_analogs": {
                "type": "integer",
                "description": "Maximum number of analogs to detect (default: 5)",
                "default": 5
            }
        },
    }
}

FETCH_ANALOG_DATA_TOOL = {
    "name": "fetch_analog_data",
    "description": "Fetch actual market data for detected historical analogs. Retrieves prices, computes metrics, and compares to current conditions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "notes": {
                "type": "string",
                "description": "Optional notes about which analogs to prioritize"
            }
        },
    }
}

AGGREGATE_ANALOGS_TOOL = {
    "name": "aggregate_analogs",
    "description": "Compute aggregate statistics across all fetched analogs: direction distribution, magnitude (median/min/max), timing (recovery days).",
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

CHARACTERIZE_REGIME_TOOL = {
    "name": "characterize_regime",
    "description": "Compare current macro conditions vs historical analogs. Produces a 'then vs now' assessment with regime name, closest analog, similarities, and differences.",
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

LOAD_THEME_CHAINS_TOOL = {
    "name": "load_theme_chains",
    "description": "Load logic chains from specific macro themes (liquidity, positioning, rates, risk_appetite, crypto_specific, event_calendar) for additional context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Theme names to load chains from"
            }
        },
        "required": ["themes"]
    }
}

FETCH_ADDITIONAL_DATA_TOOL = {
    "name": "fetch_additional_data",
    "description": "Fetch additional market data for a specific variable. Use when analog analysis reveals a precondition worth checking in current data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "variable_name": {
                "type": "string",
                "description": "Variable to fetch (e.g., 'us10y', 'vix', 'usdjpy')"
            },
            "source": {
                "type": "string",
                "enum": ["fred", "yahoo", "auto"],
                "description": "Data source (default: auto)",
                "default": "auto"
            }
        },
        "required": ["variable_name"]
    }
}

FINISH_HISTORICAL_TOOL = {
    "name": "finish_historical",
    "description": "Signal that historical context analysis is complete.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analogs_found": {
                "type": "integer",
                "description": "Number of historical analogs found"
            },
            "summary": {
                "type": "string",
                "description": "Brief summary of historical analysis"
            }
        },
        "required": ["summary"]
    }
}

ALL_TOOLS = [
    DETECT_ANALOGS_TOOL,
    FETCH_ANALOG_DATA_TOOL,
    AGGREGATE_ANALOGS_TOOL,
    CHARACTERIZE_REGIME_TOOL,
    LOAD_THEME_CHAINS_TOOL,
    FETCH_ADDITIONAL_DATA_TOOL,
    FINISH_HISTORICAL_TOOL,
]


# =============================================================================
# Tool Handlers
# =============================================================================

class HistoricalAgentState:
    """Mutable state for historical context agent."""

    def __init__(self, state: RiskImpactState):
        self.state = state
        self.analogs = []
        self.enriched_analogs = []
        self.aggregated = {}
        self.historical_event_data = {}
        self.historical_analogs_text = ""
        self.regime_characterization_text = ""
        self.additional_data = {}


def build_tool_handlers(agent_state: HistoricalAgentState) -> dict:
    """Build tool handler dict bound to agent state."""

    def handle_detect_analogs(max_analogs: int = 5) -> dict:
        from .historical_event_detector import detect_historical_analogs
        from . import config

        query = agent_state.state.get("query", "")
        synthesis = agent_state.state.get("synthesis", "")
        logic_chains = agent_state.state.get("logic_chains", [])

        analogs = detect_historical_analogs(
            query, synthesis, logic_chains,
            max_analogs=max_analogs,
            relevance_threshold=config.ANALOG_RELEVANCE_THRESHOLD,
        )
        agent_state.analogs = analogs

        return {
            "analogs_found": len(analogs),
            "analogs": [
                {
                    "event": a.get("event_name", a.get("event_description", "Unknown")),
                    "year": a.get("year", "?"),
                    "relevance": a.get("relevance_score", 0),
                    "mechanism": a.get("mechanism_match", "")[:100],
                }
                for a in analogs[:5]
            ],
        }

    def handle_fetch_analog_data(notes: str = "") -> dict:
        if not agent_state.analogs:
            return {"error": "No analogs detected. Call detect_analogs first."}

        from .historical_aggregator import fetch_multiple_analogs
        from .asset_configs import get_asset_config

        query = agent_state.state.get("query", "")
        synthesis = agent_state.state.get("synthesis", "")
        logic_chains = agent_state.state.get("logic_chains", [])
        current_values = agent_state.state.get("current_values", {})
        asset_class = agent_state.state.get("asset_class", "btc")

        # Build condition_variables from extracted variables for Then vs Now
        condition_variables = []
        for var in agent_state.state.get("extracted_variables", []):
            normalized = var.get("normalized", "")
            if normalized:
                from .current_data_fetcher import resolve_variable
                resolved = resolve_variable(normalized)
                if resolved:
                    condition_variables.append({
                        "normalized": normalized,
                        "ticker": resolved["series_id"],
                        "source": resolved["source"],
                    })

        enriched = fetch_multiple_analogs(
            agent_state.analogs, query, synthesis, logic_chains,
            current_values, asset_class,
            condition_variables=condition_variables,
        )
        agent_state.enriched_analogs = enriched

        return {
            "analogs_fetched": len(enriched),
            "summaries": [
                {
                    "event": e.get("event_name", "Unknown"),
                    "instruments_fetched": len(e.get("market_data", {}).get("instruments", {})),
                    "has_comparison": bool(e.get("comparison", {})),
                }
                for e in enriched[:5]
            ],
        }

    def handle_aggregate_analogs(notes: str = "") -> dict:
        if not agent_state.enriched_analogs:
            return {"error": "No enriched analogs. Call fetch_analog_data first."}

        from .historical_aggregator import aggregate_analogs, format_analogs_for_prompt
        from .asset_configs import get_asset_config

        asset_class = agent_state.state.get("asset_class", "btc")
        target_asset_name = get_asset_config(asset_class)["name"]
        current_values = agent_state.state.get("current_values", {})

        aggregated = aggregate_analogs(agent_state.enriched_analogs, target_asset_name)
        agent_state.aggregated = aggregated

        text = format_analogs_for_prompt(
            aggregated,
            enriched_analogs=agent_state.enriched_analogs,
            current_conditions=current_values,
        )
        agent_state.historical_analogs_text = text

        return {
            "analog_count": aggregated.get("analog_count", 0),
            "direction_distribution": aggregated.get("direction_distribution", {}),
            "magnitude_median": aggregated.get("magnitude", {}).get("median"),
            "summary": text[:500],
        }

    def handle_characterize_regime(notes: str = "") -> dict:
        if not agent_state.historical_analogs_text:
            return {"error": "No analog data. Call aggregate_analogs first."}

        from .regime_characterization import characterize_regime
        from .current_data_fetcher import format_current_values_for_prompt

        temp_state = dict(agent_state.state)
        temp_state["historical_analogs_text"] = agent_state.historical_analogs_text

        result_state = characterize_regime(temp_state)
        agent_state.regime_characterization_text = result_state.get("regime_characterization_text", "")

        return {
            "characterization": agent_state.regime_characterization_text[:500],
        }

    def handle_load_theme_chains(themes: list) -> dict:
        from .relationship_store import load_chains_by_theme

        asset_class = agent_state.state.get("asset_class", "btc")
        chains = load_chains_by_theme(themes, asset_class=asset_class)

        return {
            "chains_loaded": len(chains),
            "themes": themes,
            "chain_summaries": [
                {
                    "cause": c.get("logic_chain", {}).get("steps", [{}])[0].get("cause_normalized", "?") if c.get("logic_chain", {}).get("steps") else "?",
                    "effect": c.get("logic_chain", {}).get("steps", [{}])[-1].get("effect_normalized", "?") if c.get("logic_chain", {}).get("steps") else "?",
                }
                for c in chains[:10]
            ],
        }

    def handle_fetch_additional_data(variable_name: str, source: str = "auto") -> dict:
        from .current_data_fetcher import resolve_variable, fetch_fred_with_history, fetch_yahoo_with_history

        resolved = resolve_variable(variable_name)
        if not resolved:
            return {"error": f"Could not resolve variable: {variable_name}"}

        series_id = resolved["series_id"]
        data_source = resolved["source"]

        try:
            if data_source.upper() == "FRED":
                data = fetch_fred_with_history(series_id)
            else:
                data = fetch_yahoo_with_history(series_id)

            if data and data.get("value") is not None:
                agent_state.additional_data[variable_name] = {
                    "value": data["value"],
                    "date": data.get("date", ""),
                    "source": data_source,
                }
                return {
                    "variable": variable_name,
                    "value": data["value"],
                    "date": data.get("date", ""),
                    "source": data_source,
                }
            return {"error": f"No data for {variable_name}"}
        except Exception as e:
            return {"error": str(e)}

    def handle_finish_historical(summary: str = "", analogs_found: int = 0) -> dict:
        return {"status": "completed", "summary": summary}

    return {
        "detect_analogs": handle_detect_analogs,
        "fetch_analog_data": handle_fetch_analog_data,
        "aggregate_analogs": handle_aggregate_analogs,
        "characterize_regime": handle_characterize_regime,
        "load_theme_chains": handle_load_theme_chains,
        "fetch_additional_data": handle_fetch_additional_data,
        "finish_historical": handle_finish_historical,
    }
