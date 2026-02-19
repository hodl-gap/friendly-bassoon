"""Impact analysis module - LLM-based BTC impact assessment."""

import sys
import re
import json
from pathlib import Path
from typing import Dict, Any, List

import anthropic

# Add parent to path for models import
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_sonnet

from .impact_analysis_prompts import (
    SYSTEM_PROMPT,
    BELIEF_SPACE_SYSTEM_PROMPT,
    INSIGHT_SYSTEM_PROMPT,
    get_impact_analysis_prompt,
    get_insight_prompt,
)
from .current_data_fetcher import format_current_values_for_prompt
from .relationship_store import get_relevant_historical_chains, format_historical_chains_for_prompt
from .pattern_validator import format_validated_patterns_for_prompt
from .historical_data_fetcher import format_historical_data_for_prompt
from .asset_configs import get_asset_config
from .states import RiskImpactState
from . import config

# Anthropic client for tool_use calls
_client = anthropic.Anthropic()

# Map config model names to Anthropic model IDs
_MODEL_ID_MAP = {
    "claude_opus": "claude-opus-4-5-20251101",
    "claude_sonnet": "claude-sonnet-4-5-20250929",
    "claude_haiku": "claude-haiku-4-5-20251001",
}

def _get_impact_tool(asset_class: str = "btc") -> dict:
    """Get the tool definition for structured impact analysis output."""
    cfg = get_asset_config(asset_class)
    return {
        "name": "output_impact_analysis",
        "description": f"Output structured {cfg['name']} impact analysis with scenarios and belief space",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "direction": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
                            "likelihood": {"type": "number", "description": "Likelihood as integer percentage 0-100 (e.g., 65 means 65%)"},
                            "chain": {"type": "string"},
                            "rationale": {"type": "string"}
                        },
                        "required": ["name", "direction", "likelihood", "chain"]
                    }
                },
                "contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "thesis_a": {"type": "string"},
                            "thesis_b": {"type": "string"},
                            "implication": {"type": "string"}
                        }
                    }
                },
                "confidence": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "number"},
                        "chain_count": {"type": "integer"},
                        "source_diversity": {"type": "integer"},
                        "strongest_chain": {"type": "string"}
                    },
                    "required": ["score"]
                },
                "time_horizon": {"type": "string"},
                "decay_profile": {"type": "string"},
                "rationale": {"type": "string"},
                "risk_factors": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["scenarios", "confidence", "time_horizon", "rationale", "risk_factors"]
        }
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
                "synthesis": {
                    "type": "string",
                    "description": "Narrative connecting the tracks"
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


def _parse_tool_use_result(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert tool_use input into the same structure that parse_impact_response produces.

    This ensures backward compatibility with the rest of the pipeline.
    """
    result = {
        "direction": "NEUTRAL",
        "scenarios": [],
        "belief_space": {},
        "confidence": {},
        "time_horizon": "unknown",
        "decay_profile": "unknown",
        "rationale": "",
        "risk_factors": []
    }

    # Scenarios
    scenarios = tool_input.get("scenarios", [])
    parsed_scenarios = []
    for s in scenarios:
        scenario = {
            "name": s.get("name", ""),
            "direction": s.get("direction", "NEUTRAL"),
            "polarity": s.get("direction", "NEUTRAL"),
            "likelihood": s.get("likelihood", 0) / 100.0,
            "chain": s.get("chain", ""),
        }
        if s.get("rationale"):
            scenario["rationale"] = s["rationale"]
        parsed_scenarios.append(scenario)
    result["scenarios"] = parsed_scenarios

    # Contradictions -> belief_space
    contradictions = tool_input.get("contradictions", [])
    result["belief_space"] = {
        "contradictions": contradictions,
        "narrative_count": len(parsed_scenarios),
        "regime_uncertainty": (
            "high" if len(parsed_scenarios) > 2
            else "medium" if len(parsed_scenarios) == 2
            else "low"
        )
    }

    # Primary direction from highest likelihood scenario
    if parsed_scenarios:
        sorted_scenarios = sorted(parsed_scenarios, key=lambda s: s.get("likelihood", 0), reverse=True)
        result["direction"] = sorted_scenarios[0].get("direction", "NEUTRAL")
        result["belief_space"]["dominant_narrative"] = sorted_scenarios[0].get("name", "Unknown")

    # Confidence
    confidence_raw = tool_input.get("confidence", {})
    result["confidence"] = {
        k: v for k, v in confidence_raw.items() if v is not None
    }

    # Time horizon
    result["time_horizon"] = tool_input.get("time_horizon", "unknown")

    # Decay profile
    result["decay_profile"] = tool_input.get("decay_profile", "unknown")

    # Rationale
    result["rationale"] = tool_input.get("rationale", "")

    # Risk factors
    result["risk_factors"] = tool_input.get("risk_factors", [])

    return result


def analyze_impact(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """
    Analyze the impact of a macro event using retrieved context.

    Dispatches to insight mode or belief_space mode based on state["output_mode"].

    Args:
        state: Current state with retrieval results
        asset_class: Asset class to analyze impact for

    Returns:
        Updated state with analysis results
    """
    output_mode = state.get("output_mode", "insight")
    if output_mode == "insight":
        return _analyze_insight(state, asset_class)
    else:
        return _analyze_belief_space(state, asset_class)


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
    """
    Insight mode: produces multi-track reasoning with independent evidence.

    Falls back to belief_space mode on error.
    """
    data = _prepare_prompt_data(state, asset_class)
    prompt = get_insight_prompt(**data)

    model_id = _MODEL_ID_MAP.get(config.ANALYSIS_MODEL, "claude-sonnet-4-5-20250929")
    asset_name = get_asset_config(asset_class)["name"]
    print(f"\n[Impact Analysis] Calling {config.ANALYSIS_MODEL} ({model_id}) for {asset_name} INSIGHT mode...")

    insight_tool = _get_insight_tool(asset_class)

    try:
        response = _client.messages.create(
            model=model_id,
            max_tokens=6000,
            temperature=0.3,
            system=INSIGHT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            tools=[insight_tool],
            tool_choice={"type": "tool", "name": "output_insight"}
        )

        try:
            from shared.run_logger import log_llm_call
            log_llm_call(model_id, response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

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
        state["output_mode"] = "insight"

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

        state["decay_profile"] = "unknown"

        return state

    except Exception as e:
        print(f"\n[Impact Analysis] Insight mode failed ({e}), falling back to belief_space mode...")
        state["output_mode"] = "belief_space"
        return _analyze_belief_space(state, asset_class)


def _analyze_belief_space(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """
    Belief space mode: produces scenarios with contradictions (legacy).

    Uses Anthropic tool_use for structured output. Falls back to regex parsing.
    """
    data = _prepare_prompt_data(state, asset_class)
    prompt = get_impact_analysis_prompt(**data)

    model_id = _MODEL_ID_MAP.get(config.ANALYSIS_MODEL, "claude-sonnet-4-5-20250929")
    asset_name = get_asset_config(asset_class)["name"]
    print(f"\n[Impact Analysis] Calling {config.ANALYSIS_MODEL} ({model_id}) for {asset_name} BELIEF_SPACE mode...")

    impact_tool = _get_impact_tool(asset_class)

    try:
        response = _client.messages.create(
            model=model_id,
            max_tokens=4000,
            temperature=0.3,
            system=BELIEF_SPACE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            tools=[impact_tool],
            tool_choice={"type": "tool", "name": "output_impact_analysis"}
        )

        try:
            from shared.run_logger import log_llm_call
            log_llm_call(model_id, response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        print("\n[Impact Analysis] Raw LLM Response:")
        print("-" * 40)
        print(response)
        print("-" * 40)

        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_impact_analysis":
                tool_input = block.input
                break

        if tool_input is None:
            raise ValueError("No tool_use block found in response")

        print("\n[Impact Analysis] Tool use input (structured):")
        print("-" * 40)
        print(json.dumps(tool_input, indent=2))
        print("-" * 40)

        parsed = _parse_tool_use_result(tool_input)

    except Exception as e:
        print(f"\n[Impact Analysis] tool_use failed ({e}), falling back to regex parsing...")

        messages = [{"role": "user", "content": prompt}]
        fallback_response = call_claude_sonnet(messages, temperature=0.3, max_tokens=2000)

        print("\n[Impact Analysis] Fallback Raw LLM Response:")
        print("-" * 40)
        print(fallback_response)
        print("-" * 40)

        parsed = parse_impact_response(fallback_response)

    state["scenarios"] = parsed.get("scenarios", [])
    state["belief_space"] = parsed.get("belief_space", {})
    state["direction"] = parsed.get("direction", "NEUTRAL")
    state["confidence"] = parsed.get("confidence", {})
    state["time_horizon"] = parsed.get("time_horizon", "unknown")
    state["decay_profile"] = parsed.get("decay_profile", "unknown")
    state["rationale"] = parsed.get("rationale", "")
    state["risk_factors"] = parsed.get("risk_factors", [])
    state["output_mode"] = "belief_space"

    return state


def parse_scenarios(response: str) -> List[Dict[str, Any]]:
    """Parse all scenarios from the SCENARIOS section of the LLM response."""
    scenarios = []

    # Find the SCENARIOS section
    scenarios_match = re.search(
        r"SCENARIOS:\s*\n(.+?)(?=\nPRIMARY_DIRECTION:|\nCONTRADICTIONS:|\nDIRECTION:|\Z)",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if not scenarios_match:
        return scenarios

    scenarios_text = scenarios_match.group(1)

    # Split by "- Scenario" to get each scenario block
    scenario_blocks = re.split(r"\n-\s*Scenario\s*", scenarios_text)

    for block in scenario_blocks:
        if not block.strip():
            continue

        scenario = {}

        # Extract scenario name (first line or after letter like "A:")
        # Handle various formats: "A: Name", "A - Name", just "Name"
        first_line = block.strip().split('\n')[0].strip()
        # Remove leading "- Scenario" prefix if present (edge case from split)
        first_line = re.sub(r'^-?\s*Scenario\s*', '', first_line, flags=re.IGNORECASE)
        # Parse "A: Name" or "A - Name" or just "Name"
        name_match = re.match(r"([A-Z])[\s:.-]+(.+?)$", first_line.strip())
        if name_match:
            scenario["name"] = name_match.group(2).strip()
        else:
            scenario["name"] = first_line.strip()

        # Extract Chain
        chain_match = re.search(r"-\s*Chain:\s*(.+?)(?:\n|$)", block)
        if chain_match:
            scenario["chain"] = chain_match.group(1).strip()

        # Extract Direction
        dir_match = re.search(r"-\s*Direction:\s*(BULLISH|BEARISH|NEUTRAL)", block, re.IGNORECASE)
        if dir_match:
            scenario["direction"] = dir_match.group(1).upper()
            scenario["polarity"] = dir_match.group(1).upper()

        # Extract Likelihood
        likelihood_match = re.search(r"-\s*Likelihood:\s*(\d+)%?\s*(?:based on\s*)?(.+)?(?:\n|$)", block, re.IGNORECASE)
        if likelihood_match:
            scenario["likelihood"] = int(likelihood_match.group(1)) / 100.0
            if likelihood_match.group(2):
                scenario["likelihood_basis"] = likelihood_match.group(2).strip()

        # Extract Rationale if present
        rationale_match = re.search(r"-\s*Rationale:\s*(.+?)(?:\n-|\n\n|$)", block, re.DOTALL)
        if rationale_match:
            scenario["rationale"] = rationale_match.group(1).strip()

        if scenario.get("name") or scenario.get("chain"):
            scenarios.append(scenario)

    return scenarios


def parse_contradictions(response: str) -> List[Dict[str, Any]]:
    """Parse contradictions from the CONTRADICTIONS section."""
    contradictions = []

    # Find CONTRADICTIONS section
    contra_match = re.search(
        r"CONTRADICTIONS:\s*\n(.+?)(?=\nPRIMARY_DIRECTION:|\nCONFIDENCE:|\nTIME_HORIZON:|\Z)",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if not contra_match:
        return contradictions

    contra_text = contra_match.group(1)

    # Parse each contradiction block (marked by - or bullet)
    contra_blocks = re.findall(
        r"-\s*(.+?)(?=\n-|\n\n|$)",
        contra_text,
        re.DOTALL
    )

    for block in contra_blocks:
        contradiction = {}

        # Try to parse structured format: "Thesis A vs Thesis B"
        vs_match = re.search(r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\n|$)", block, re.IGNORECASE)
        if vs_match:
            contradiction["thesis_a"] = vs_match.group(1).strip()
            contradiction["thesis_b"] = vs_match.group(2).strip()
        else:
            contradiction["description"] = block.strip()

        # Extract implication if present
        impl_match = re.search(r"(?:Implication|Result|Means):\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
        if impl_match:
            contradiction["implication"] = impl_match.group(1).strip()

        if contradiction:
            contradictions.append(contradiction)

    return contradictions


def parse_impact_response(response: str) -> Dict[str, Any]:
    """Parse the structured LLM response into components."""
    result = {
        "direction": "NEUTRAL",
        "scenarios": [],
        "belief_space": {},
        "confidence": {},
        "time_horizon": "unknown",
        "decay_profile": "unknown",
        "rationale": "",
        "risk_factors": []
    }

    # Parse all scenarios (CRITICAL for belief-space output)
    scenarios = parse_scenarios(response)
    result["scenarios"] = scenarios

    # Parse contradictions
    contradictions = parse_contradictions(response)
    result["belief_space"] = {
        "contradictions": contradictions,
        "narrative_count": len(scenarios),
        "regime_uncertainty": "high" if len(scenarios) > 2 else "medium" if len(scenarios) == 2 else "low"
    }

    # Determine primary direction from highest likelihood scenario
    if scenarios:
        sorted_scenarios = sorted(scenarios, key=lambda s: s.get("likelihood", 0), reverse=True)
        result["direction"] = sorted_scenarios[0].get("direction", "NEUTRAL")
        result["belief_space"]["dominant_narrative"] = sorted_scenarios[0].get("name", "Unknown")
    else:
        # Fallback: Parse PRIMARY_DIRECTION (or DIRECTION for backward compatibility)
        direction_match = re.search(r"PRIMARY_DIRECTION:\s*(BULLISH|BEARISH|NEUTRAL)", response, re.IGNORECASE)
        if not direction_match:
            direction_match = re.search(r"DIRECTION:\s*(BULLISH|BEARISH|NEUTRAL)", response, re.IGNORECASE)
        if direction_match:
            result["direction"] = direction_match.group(1).upper()

    # Parse CONFIDENCE section
    confidence = {}
    score_match = re.search(r"score:\s*([\d.]+)", response, re.IGNORECASE)
    if score_match:
        try:
            confidence["score"] = float(score_match.group(1))
        except ValueError:
            confidence["score"] = 0.5

    chain_count_match = re.search(r"chain_count:\s*(\d+)", response, re.IGNORECASE)
    if chain_count_match:
        confidence["chain_count"] = int(chain_count_match.group(1))

    source_div_match = re.search(r"source_diversity:\s*(\d+)", response, re.IGNORECASE)
    if source_div_match:
        confidence["source_diversity"] = int(source_div_match.group(1))

    strongest_match = re.search(r"strongest_chain:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
    if strongest_match:
        confidence["strongest_chain"] = strongest_match.group(1).strip().strip('"\'')

    result["confidence"] = confidence

    # Parse TIME_HORIZON
    horizon_match = re.search(r"TIME_HORIZON:\s*(intraday|days|weeks|months|regime_shift)", response, re.IGNORECASE)
    if horizon_match:
        result["time_horizon"] = horizon_match.group(1).lower()

    # Parse DECAY_PROFILE
    decay_match = re.search(r"DECAY_PROFILE:\s*(fast|medium|slow)", response, re.IGNORECASE)
    if decay_match:
        result["decay_profile"] = decay_match.group(1).lower()

    # Parse RATIONALE
    rationale_match = re.search(r"RATIONALE:\s*\n(.+?)(?=\nRISK_FACTORS:|\Z)", response, re.DOTALL | re.IGNORECASE)
    if rationale_match:
        result["rationale"] = rationale_match.group(1).strip()

    # Parse RISK_FACTORS
    risks_match = re.search(r"RISK_FACTORS:\s*\n(.+?)(?:\Z)", response, re.DOTALL | re.IGNORECASE)
    if risks_match:
        risks_text = risks_match.group(1)
        # Extract bullet points
        risks = re.findall(r"[-•]\s*(.+?)(?:\n|$)", risks_text)
        result["risk_factors"] = [r.strip() for r in risks if r.strip()]

    return result
