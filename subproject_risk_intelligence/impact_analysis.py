"""Impact analysis module - LLM-based insight generation."""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# Add parent to path for models import
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_with_tools

from .impact_analysis_prompts import (
    SYSTEM_PROMPT,
    get_insight_prompt,
)
from .current_data_fetcher import format_current_values_for_prompt
from .relationship_store import get_relevant_historical_chains, format_historical_chains_for_prompt
from .pattern_validator import format_validated_patterns_for_prompt
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

def _get_insight_tool(asset_class: str = "btc") -> dict:
    """Get the tool definition for structured insight output."""
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
                            "causal_mechanism": {"type": "string", "description": "Arrow notation chain"},
                            "historical_evidence": {
                                "type": "object",
                                "properties": {
                                    "precedent_count": {"type": "integer"},
                                    "success_rate": {"type": "number"},
                                    "precedent_summary": {"type": "string"},
                                    "precedents": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "event": {"type": "string"},
                                                "outcome": {"type": "string"},
                                                "magnitude": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            },
                            "asset_implications": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "asset": {"type": "string"},
                                        "direction": {"type": "string"},
                                        "magnitude_range": {"type": "string"},
                                        "timing": {"type": "string"}
                                    },
                                    "required": ["asset", "direction"]
                                }
                            },
                            "monitoring_variables": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "variable": {"type": "string"},
                                        "condition": {"type": "string"},
                                        "meaning": {"type": "string"}
                                    },
                                    "required": ["variable", "condition"]
                                }
                            },
                            "confidence": {"type": "number"},
                            "time_horizon": {"type": "string"},
                            "sequence_position": {
                                "type": "integer",
                                "description": "Temporal order (1=first, 2=next...). Use when tracks have sequential dependency."
                            }
                        },
                        "required": ["title", "causal_mechanism", "asset_implications", "confidence"]
                    }
                },
                "key_uncertainties": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "outlook": {
                    "type": "string",
                    "description": "Forward projections, seasonal patterns, and predictions about what happens next. Content that is temporally AFTER the queried event belongs here, not in causal tracks."
                },
                "synthesis": {
                    "type": "string",
                    "description": "Narrative connecting the causal tracks"
                }
            },
            "required": ["tracks", "synthesis"]
        }
    }


def _parse_insight_tool_result(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Convert insight tool_use input into structured insight output."""
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
        "tracks": parsed_tracks,
        "key_uncertainties": tool_input.get("key_uncertainties", []),
        "synthesis": tool_input.get("synthesis", ""),
    }


def analyze_impact(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """
    Analyze the impact of a macro event using retrieved context.

    Produces multi-track insight output with independent reasoning tracks.

    Args:
        state: Current state with retrieval results
        asset_class: Asset class to analyze impact for

    Returns:
        Updated state with analysis results
    """
    return _analyze_insight(state, asset_class)


def _prepare_prompt_data(state: RiskImpactState, asset_class: str) -> dict:
    """Prepare shared prompt data used by both analysis modes."""
    current_values = state.get("current_values", {})
    current_values_text = format_current_values_for_prompt(current_values) if current_values else ""

    historical_chains = state.get("historical_chains", [])
    query = state.get("query", "")
    relevant_chains = get_relevant_historical_chains(query, historical_chains, limit=5)
    historical_chains_text = format_historical_chains_for_prompt(relevant_chains)

    validated_patterns = state.get("validated_patterns", [])
    validated_patterns_text = format_validated_patterns_for_prompt(validated_patterns)

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
        "retrieval_answer": state.get("retrieval_answer", ""),
        "synthesis": state.get("synthesis", ""),
        "logic_chains": state.get("logic_chains", []),
        "confidence_metadata": state.get("confidence_metadata", {}),
        "current_values_text": current_values_text,
        "historical_chains_text": historical_chains_text,
        "validated_patterns_text": validated_patterns_text,
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


def _analyze_insight(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """Produce multi-track reasoning with independent evidence."""
    data = _prepare_prompt_data(state, asset_class)
    prompt = get_insight_prompt(**data)

    model_short = _MODEL_SHORT_NAME.get(config.ANALYSIS_MODEL, "sonnet")
    asset_name = get_asset_config(asset_class)["name"]
    print(f"\n[Impact Analysis] Calling {config.ANALYSIS_MODEL} ({model_short}) for {asset_name} INSIGHT mode...")

    insight_tool = _get_insight_tool(asset_class)

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[insight_tool],
            tool_choice={"type": "tool", "name": "output_insight"},
            model=model_short,
            temperature=0.3,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
        )

        # Retry with higher limit if truncated
        if getattr(response, "stop_reason", None) == "max_tokens":
            print("[Impact Analysis] Response truncated at 8192 tokens, retrying with 12000...")
            response = call_claude_with_tools(
                messages=[{"role": "user", "content": prompt}],
                tools=[insight_tool],
                tool_choice={"type": "tool", "name": "output_insight"},
                model=model_short,
                temperature=0.3,
                max_tokens=12000,
                system=SYSTEM_PROMPT,
            )

        print("\n[Impact Analysis] Raw LLM Response (insight):")
        print("-" * 40)
        print(response)
        print("-" * 40)

        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_insight":
                tool_input = block.input
                break

        if tool_input is None:
            raise ValueError("No output_insight tool_use block found in response")

        print("\n[Impact Analysis] Insight tool output (structured):")
        print("-" * 40)
        print(json.dumps(tool_input, indent=2))
        print("-" * 40)

        parsed = _parse_insight_tool_result(tool_input)

        state["insight_output"] = parsed

        # Populate legacy fields from best track for backward compatibility
        tracks = parsed.get("tracks", [])
        if tracks:
            best_track = max(tracks, key=lambda t: t.get("confidence", 0))
            implications = best_track.get("asset_implications", [])
            if implications:
                direction = implications[0].get("direction", "NEUTRAL").upper()
                if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
                    direction = "NEUTRAL"
                state["direction"] = direction
            else:
                state["direction"] = "NEUTRAL"
            state["confidence"] = {"score": best_track.get("confidence", 0.5)}
            state["time_horizon"] = best_track.get("time_horizon", "unknown")
            state["rationale"] = parsed.get("synthesis", "")
            state["risk_factors"] = parsed.get("key_uncertainties", [])
        else:
            state["direction"] = "NEUTRAL"
            state["confidence"] = {"score": 0.5}
            state["rationale"] = parsed.get("synthesis", "")
            state["risk_factors"] = parsed.get("key_uncertainties", [])

        return state

    except Exception as e:
        print(f"\n[Impact Analysis] Insight analysis failed: {e}")
        raise
