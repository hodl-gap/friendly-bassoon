"""Impact analysis module - LLM-based insight generation.

Two output modes:
- Retrospective (output_causal_decomposition): causal tracks explaining what happened
- Prospective (output_scenario_analysis): scenario-based forward analysis with predictions
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# Add parent to path for models import
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_with_tools

from .impact_analysis_prompts import (
    SYSTEM_PROMPT_RETROSPECTIVE,
    SYSTEM_PROMPT_PROSPECTIVE,
    get_retrospective_prompt,
    get_prospective_prompt,
)
from .current_data_fetcher import format_current_values_for_prompt
from .relationship_store import get_relevant_historical_chains, format_historical_chains_for_prompt
from .historical_data_fetcher import format_historical_data_for_prompt
from .asset_configs import get_asset_config
from .states import RiskImpactState
from . import config

# Map config model names to call_claude_with_tools short names
_MODEL_SHORT_NAME = {
    "claude_opus": "opus",
    "claude_sonnet": "sonnet",
    "claude_haiku": "haiku",
}


def _get_retrospective_tool() -> dict:
    """Tool schema for retrospective causal decomposition."""
    return {
        "name": "output_causal_decomposition",
        "description": "Output structured causal decomposition explaining what happened and why",
        "input_schema": {
            "type": "object",
            "properties": {
                "trigger_event": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "maxLength": 200},
                        "date": {"type": "string"},
                    },
                    "required": ["description"],
                },
                "causal_tracks": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "maxLength": 80},
                            "mechanism": {
                                "type": "string",
                                "maxLength": 200,
                                "description": "Arrow notation: A → B → C",
                            },
                            "evidence_summary": {"type": "string", "maxLength": 300},
                            "quantitative_data": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "metric": {"type": "string"},
                                        "value": {"type": "string"},
                                        "source": {"type": "string"},
                                    },
                                    "required": ["metric", "value"],
                                },
                            },
                            "confidence": {"type": "number"},
                        },
                        "required": ["title", "mechanism", "evidence_summary", "confidence"],
                    },
                },
                "cross_track_synthesis": {
                    "type": "string",
                    "maxLength": 500,
                    "description": "How tracks interact. 2-3 sentences max.",
                },
                "residual_forward_view": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Optional: what to watch going forward. NOT scored.",
                },
                "key_data_gaps": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {"type": "string", "maxLength": 100},
                },
            },
            "required": ["trigger_event", "causal_tracks", "cross_track_synthesis"],
        },
    }


def _get_prospective_tool() -> dict:
    """Tool schema for prospective scenario analysis."""
    return {
        "name": "output_scenario_analysis",
        "description": "Output structured scenario analysis with predictions grounded in historical data",
        "input_schema": {
            "type": "object",
            "properties": {
                "current_situation": {"type": "string", "maxLength": 300},
                "scenarios": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "maxLength": 80},
                            "condition": {
                                "type": "string",
                                "maxLength": 200,
                                "description": "What must be true for this scenario",
                            },
                            "mechanism": {
                                "type": "string",
                                "maxLength": 200,
                                "description": "Arrow notation causal chain",
                            },
                            "analog_basis": {
                                "type": "string",
                                "maxLength": 200,
                                "description": "Which historical analogs support this. Reference the base rate data.",
                            },
                            "predictions": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "variable": {"type": "string"},
                                        "direction": {
                                            "type": "string",
                                            "enum": ["bullish", "bearish", "neutral"],
                                        },
                                        "magnitude_low": {"type": "number"},
                                        "magnitude_high": {"type": "number"},
                                        "timeframe_days": {"type": "integer"},
                                    },
                                    "required": ["variable", "direction", "timeframe_days"],
                                },
                            },
                            "falsification": {
                                "type": "string",
                                "maxLength": 150,
                                "description": "What would prove this scenario wrong",
                            },
                        },
                        "required": ["title", "condition", "mechanism", "predictions", "falsification"],
                    },
                },
                "monitoring_dashboard": {
                    "type": "array",
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "variable": {"type": "string"},
                            "current_value": {"type": "number"},
                            "scenario_1_threshold": {"type": "string", "maxLength": 30},
                            "scenario_2_threshold": {"type": "string", "maxLength": 30},
                        },
                        "required": ["variable"],
                    },
                },
                "synthesis": {
                    "type": "string",
                    "maxLength": 500,
                    "description": "3-4 sentence bottom line connecting scenarios",
                },
            },
            "required": ["current_situation", "scenarios", "monitoring_dashboard", "synthesis"],
        },
    }


# Keep legacy tool for backward compat during transition
def _get_insight_tool(asset_class: str = "btc") -> dict:
    """Get legacy tool definition — used only by synthesis_phase patch path."""
    cfg = get_asset_config(asset_class)
    return {
        "name": "output_insight",
        "description": f"Output structured insight report with independent reasoning tracks for {cfg['name']}",
        "input_schema": {
            "type": "object",
            "properties": {
                "tracks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "causal_mechanism": {"type": "string"},
                            "historical_evidence": {"type": "object"},
                            "asset_implications": {"type": "array", "items": {"type": "object"}},
                            "monitoring_variables": {"type": "array", "items": {"type": "object"}},
                            "confidence": {"type": "number"},
                            "time_horizon": {"type": "string"},
                        },
                        "required": ["title", "causal_mechanism", "confidence"],
                    },
                },
                "key_uncertainties": {"type": "array", "items": {"type": "string"}},
                "synthesis": {"type": "string"},
            },
            "required": ["tracks", "synthesis"],
        },
    }


def _parse_retrospective_result(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Parse output_causal_decomposition tool result."""
    return {
        "output_mode": "retrospective",
        "trigger_event": tool_input.get("trigger_event", {}),
        "causal_tracks": tool_input.get("causal_tracks", []),
        "cross_track_synthesis": tool_input.get("cross_track_synthesis", ""),
        "residual_forward_view": tool_input.get("residual_forward_view", ""),
        "key_data_gaps": tool_input.get("key_data_gaps", []),
    }


def _parse_prospective_result(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Parse output_scenario_analysis tool result."""
    return {
        "output_mode": "prospective",
        "current_situation": tool_input.get("current_situation", ""),
        "scenarios": tool_input.get("scenarios", []),
        "monitoring_dashboard": tool_input.get("monitoring_dashboard", []),
        "synthesis": tool_input.get("synthesis", ""),
    }


def _parse_insight_tool_result(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Parse legacy output_insight tool result — kept for patch path."""
    tracks = tool_input.get("tracks", [])
    parsed_tracks = []
    for i, t in enumerate(tracks):
        track_data = {
            "track_id": f"track_{i+1}",
            "title": t.get("title", f"Track {i+1}"),
            "causal_mechanism": t.get("causal_mechanism", ""),
            "causal_steps": [],
            "historical_evidence": t.get("historical_evidence", {}),
            "asset_implications": t.get("asset_implications", []),
            "monitoring_variables": t.get("monitoring_variables", []),
            "confidence": t.get("confidence", 0.5),
            "time_horizon": t.get("time_horizon", "unknown"),
        }
        if t.get("sequence_position") is not None:
            track_data["sequence_position"] = t["sequence_position"]
        parsed_tracks.append(track_data)

    return {
        "output_mode": "legacy",
        "tracks": parsed_tracks,
        "key_uncertainties": tool_input.get("key_uncertainties", []),
        "synthesis": tool_input.get("synthesis", ""),
    }


def analyze_impact(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """
    Analyze the impact of a macro event using retrieved context.

    Routes to retrospective (causal decomposition) or prospective (scenario analysis)
    based on temporal_direction from the EDF knowledge tree.
    """
    temporal_direction = _get_temporal_direction(state)
    print(f"\n[Impact Analysis] Output mode: {temporal_direction}")

    if temporal_direction == "retrospective":
        return _analyze_retrospective(state, asset_class)
    else:
        return _analyze_prospective(state, asset_class)


def _get_temporal_direction(state: RiskImpactState) -> str:
    """Get temporal direction from EDF tree, default to prospective."""
    tree = state.get("_edf_knowledge_tree", {})
    direction = tree.get("temporal_direction", "prospective")
    if direction not in ("retrospective", "prospective"):
        return "prospective"
    return direction


def _prepare_prompt_data(state: RiskImpactState, asset_class: str) -> dict:
    """Prepare shared prompt data used by both analysis modes."""
    current_values = state.get("current_values", {})
    current_values_text = format_current_values_for_prompt(current_values) if current_values else ""

    historical_chains = state.get("historical_chains", [])
    query = state.get("query", "")
    relevant_chains = get_relevant_historical_chains(query, historical_chains, limit=5)
    historical_chains_text = format_historical_chains_for_prompt(relevant_chains)

    historical_event_data = state.get("historical_event_data", {})
    historical_event_text = format_historical_data_for_prompt(historical_event_data)

    # Format claim validation results
    claim_validation_text = ""
    claim_results = state.get("claim_validation_results", [])
    if claim_results:
        lines = ["## CLAIM VALIDATION (Data-Tested)"]
        for r in claim_results:
            claim = r.get("claim", "Unknown claim")
            status = r.get("status", "unknown")
            correlation = r.get("actual_correlation")
            p_value = r.get("p_value")
            interpretation = r.get("interpretation", "")

            status_upper = status.upper().replace("_", " ")
            stats_parts = []
            if correlation is not None:
                stats_parts.append(f"correlation={correlation:.2f}")
            if p_value is not None:
                stats_parts.append(f"p={p_value:.3f}")
            stats_str = f" ({', '.join(stats_parts)})" if stats_parts else ""

            line = f'- "{claim}": {status_upper}{stats_str}'
            if interpretation:
                line += f" — {interpretation}"
            lines.append(line)
        claim_validation_text = "\n".join(lines)

    return {
        "query": query,
        "synthesis": state.get("synthesis", ""),
        "logic_chains": state.get("logic_chains", []),
        "confidence_metadata": state.get("confidence_metadata", {}),
        "current_values_text": current_values_text,
        "historical_chains_text": historical_chains_text,
        "historical_event_text": historical_event_text,
        "knowledge_gaps": state.get("knowledge_gaps", {}),
        "gap_enrichment_text": state.get("gap_enrichment_text", ""),
        "asset_class": asset_class,
        "theme_states": state.get("theme_states", None),
        "chain_graph_text": state.get("chain_graph_text", ""),
        "historical_analogs_text": state.get("historical_analogs_text", ""),
        "claim_validation_text": claim_validation_text,
        "regime_characterization_text": state.get("regime_characterization_text", ""),
    }


def _analyze_retrospective(state: RiskImpactState, asset_class: str) -> RiskImpactState:
    """Produce causal decomposition (retrospective mode)."""
    data = _prepare_prompt_data(state, asset_class)
    prompt = get_retrospective_prompt(**data)

    model_short = _MODEL_SHORT_NAME.get(config.ANALYSIS_MODEL, "sonnet")
    asset_name = get_asset_config(asset_class)["name"]
    print(f"\n[Impact Analysis] Calling {config.ANALYSIS_MODEL} ({model_short}) for {asset_name} RETROSPECTIVE mode...")

    tool = _get_retrospective_tool()
    tool_name = "output_causal_decomposition"

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            model=model_short,
            temperature=0.3,
            max_tokens=8000,
            system=SYSTEM_PROMPT_RETROSPECTIVE,
        )

        tool_input = _extract_tool_input(response, tool_name)
        parsed = _parse_retrospective_result(tool_input)
        state["insight_output"] = parsed
        _populate_legacy_fields_retrospective(state, parsed)
        return state

    except Exception as e:
        print(f"\n[Impact Analysis] Retrospective analysis failed: {e}")
        raise


def _analyze_prospective(state: RiskImpactState, asset_class: str) -> RiskImpactState:
    """Produce scenario analysis (prospective mode)."""
    data = _prepare_prompt_data(state, asset_class)
    scenario_skeleton = state.get("scenario_skeleton", {})
    prompt = get_prospective_prompt(**data, scenario_skeleton=scenario_skeleton)

    model_short = _MODEL_SHORT_NAME.get(config.ANALYSIS_MODEL, "sonnet")
    asset_name = get_asset_config(asset_class)["name"]
    print(f"\n[Impact Analysis] Calling {config.ANALYSIS_MODEL} ({model_short}) for {asset_name} PROSPECTIVE mode...")

    tool = _get_prospective_tool()
    tool_name = "output_scenario_analysis"

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            model=model_short,
            temperature=0.3,
            max_tokens=8000,
            system=SYSTEM_PROMPT_PROSPECTIVE,
        )

        tool_input = _extract_tool_input(response, tool_name)
        parsed = _parse_prospective_result(tool_input)

        # Inject analog_count from skeleton into parsed scenarios
        skeleton_scenarios = scenario_skeleton.get("scenarios", [])
        for i, scenario in enumerate(parsed.get("scenarios", [])):
            if i < len(skeleton_scenarios):
                scenario["analog_count"] = skeleton_scenarios[i].get("analog_count")
                scenario["total_episodes"] = skeleton_scenarios[i].get("total_episodes")

        state["insight_output"] = parsed
        _populate_legacy_fields_prospective(state, parsed)
        return state

    except Exception as e:
        print(f"\n[Impact Analysis] Prospective analysis failed: {e}")
        raise


def _extract_tool_input(response, tool_name: str) -> Dict[str, Any]:
    """Extract tool_use input from LLM response."""
    print("\n[Impact Analysis] Raw LLM Response:")
    print("-" * 40)
    print(response)
    print("-" * 40)

    tool_input = None
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            tool_input = block.input
            break

    if tool_input is None:
        raise ValueError(f"No {tool_name} tool_use block found in response")

    print(f"\n[Impact Analysis] {tool_name} output (structured):")
    print("-" * 40)
    print(json.dumps(tool_input, indent=2))
    print("-" * 40)

    return tool_input


def _populate_legacy_fields_retrospective(state: RiskImpactState, parsed: Dict[str, Any]):
    """Populate legacy fields from retrospective output for backward compat."""
    tracks = parsed.get("causal_tracks", [])
    if tracks:
        best = max(tracks, key=lambda t: t.get("confidence", 0))
        state["direction"] = "NEUTRAL"
        state["confidence"] = {"score": best.get("confidence", 0.5)}
        state["time_horizon"] = "unknown"
        state["rationale"] = parsed.get("cross_track_synthesis", "")
        state["risk_factors"] = parsed.get("key_data_gaps", [])
    else:
        state["direction"] = "NEUTRAL"
        state["confidence"] = {"score": 0.5}
        state["rationale"] = parsed.get("cross_track_synthesis", "")
        state["risk_factors"] = []


def _populate_legacy_fields_prospective(state: RiskImpactState, parsed: Dict[str, Any]):
    """Populate legacy fields from prospective output for backward compat."""
    scenarios = parsed.get("scenarios", [])
    if scenarios:
        # Pick direction from first scenario's first prediction
        first_pred = scenarios[0].get("predictions", [{}])[0] if scenarios[0].get("predictions") else {}
        direction = first_pred.get("direction", "neutral").upper()
        if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
            direction = "NEUTRAL"
        state["direction"] = direction
        state["confidence"] = {"score": 0.5}
        state["time_horizon"] = "unknown"
        state["rationale"] = parsed.get("synthesis", "")
        state["risk_factors"] = [s.get("falsification", "") for s in scenarios if s.get("falsification")]
    else:
        state["direction"] = "NEUTRAL"
        state["confidence"] = {"score": 0.5}
        state["rationale"] = parsed.get("synthesis", "")
        state["risk_factors"] = []
