"""Synthesis self-check phase — verifies and patches insight output.

Phase 4: Structured synthesis with self-verification.
1. Call Opus with mode-specific tool (retrospective or prospective)
2. Send output to Sonnet verifier with mode-specific checks
3. If verifier finds gaps, one more Opus call with gap feedback appended
4. Return (possibly patched) output
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_sonnet

from .states import RiskImpactState
from .impact_analysis import (
    analyze_impact, _prepare_prompt_data,
    _get_retrospective_tool, _get_prospective_tool,
    _get_insight_tool, _parse_retrospective_result, _parse_prospective_result,
    _parse_insight_tool_result, _MODEL_SHORT_NAME,
    _get_temporal_direction, _extract_tool_input,
    _populate_legacy_fields_retrospective, _populate_legacy_fields_prospective,
)
from .impact_analysis_prompts import (
    SYSTEM_PROMPT_RETROSPECTIVE, SYSTEM_PROMPT_PROSPECTIVE,
    get_retrospective_prompt, get_prospective_prompt,
)
from .current_data_fetcher import format_current_values_for_prompt
from .synthesis_prompts import VERIFICATION_PROMPT_RETROSPECTIVE, VERIFICATION_PROMPT_PROSPECTIVE
from .asset_configs import get_asset_config
from . import config


def _format_insight_for_verification(insight_output: dict) -> str:
    """Format structured insight output as readable text for the verifier."""
    output_mode = insight_output.get("output_mode", "legacy")

    if output_mode == "retrospective":
        return _format_retrospective_for_verification(insight_output)
    elif output_mode == "prospective":
        return _format_prospective_for_verification(insight_output)
    else:
        return _format_legacy_for_verification(insight_output)


def _format_retrospective_for_verification(insight_output: dict) -> str:
    """Format retrospective output for verification."""
    lines = []
    trigger = insight_output.get("trigger_event", {})
    lines.append(f"TRIGGER: {trigger.get('description', 'N/A')} ({trigger.get('date', 'N/A')})")

    for i, track in enumerate(insight_output.get("causal_tracks", []), 1):
        lines.append(f"\nTRACK {i}: {track.get('title', 'Untitled')}")
        lines.append(f"  Mechanism: {track.get('mechanism', 'N/A')}")
        lines.append(f"  Evidence: {track.get('evidence_summary', 'N/A')}")
        lines.append(f"  Confidence: {track.get('confidence', 0):.0%}")
        for qd in track.get("quantitative_data", []):
            lines.append(f"  Data: {qd.get('metric', '?')}: {qd.get('value', '?')}")

    synth = insight_output.get("cross_track_synthesis", "")
    if synth:
        lines.append(f"\nSYNTHESIS: {synth}")

    return "\n".join(lines)


def _format_prospective_for_verification(insight_output: dict) -> str:
    """Format prospective output for verification."""
    lines = [f"SITUATION: {insight_output.get('current_situation', 'N/A')}"]

    for i, scenario in enumerate(insight_output.get("scenarios", []), 1):
        lines.append(f"\nSCENARIO {i}: {scenario.get('title', 'Untitled')}")
        lines.append(f"  Condition: {scenario.get('condition', 'N/A')}")
        lines.append(f"  Mechanism: {scenario.get('mechanism', 'N/A')}")
        lines.append(f"  Basis: {scenario.get('analog_basis', 'N/A')}")
        lines.append(f"  Falsification: {scenario.get('falsification', 'N/A')}")
        for pred in scenario.get("predictions", []):
            mag = ""
            if pred.get("magnitude_low") is not None and pred.get("magnitude_high") is not None:
                mag = f" {pred['magnitude_low']}% to {pred['magnitude_high']}%"
            lines.append(f"  Prediction: {pred.get('variable', '?')} {pred.get('direction', '?')}{mag} ({pred.get('timeframe_days', '?')}d)")

    dashboard = insight_output.get("monitoring_dashboard", [])
    if dashboard:
        lines.append("\nMONITORING:")
        for m in dashboard:
            lines.append(f"  {m.get('variable', '?')}: {m.get('current_value', '?')}")

    synth = insight_output.get("synthesis", "")
    if synth:
        lines.append(f"\nSYNTHESIS: {synth}")

    return "\n".join(lines)


def _format_legacy_for_verification(insight_output: dict) -> str:
    """Format legacy track-based output for verification."""
    tracks = insight_output.get("tracks", [])
    synthesis = insight_output.get("synthesis", "")
    uncertainties = insight_output.get("key_uncertainties", [])

    lines = []
    for i, track in enumerate(tracks, 1):
        lines.append(f"TRACK {i}: {track.get('title', 'Untitled')}")
        lines.append(f"  Mechanism: {track.get('causal_mechanism', 'N/A')}")
        lines.append(f"  Confidence: {track.get('confidence', 0):.0%}")

        evidence = track.get("historical_evidence", {})
        if evidence:
            lines.append(f"  Precedents: {evidence.get('precedent_count', 0)}, "
                        f"Success: {evidence.get('success_rate', 0):.0%}")

        for imp in track.get("asset_implications", []):
            lines.append(f"  {imp.get('asset', '?')}: {imp.get('direction', '?')} "
                        f"({imp.get('magnitude_range', '')}, {imp.get('timing', '')})")
        lines.append("")

    if synthesis:
        lines.append(f"SYNTHESIS: {synthesis}")
    if uncertainties:
        lines.append(f"UNCERTAINTIES: {', '.join(uncertainties)}")

    return "\n".join(lines)


def run_synthesis_phase(state: RiskImpactState, asset_class: str) -> RiskImpactState:
    """
    Phase 4: Structured synthesis with self-verification.

    Routes to retrospective or prospective mode based on EDF temporal_direction.
    """
    from shared.debug_logger import debug_log, debug_log_node

    asset_name = get_asset_config(asset_class)["name"]
    temporal_direction = _get_temporal_direction(state)
    debug_log_node("synthesis_phase", "ENTER", f"asset={asset_class} ({asset_name}), mode={temporal_direction}")
    print(f"\n[Synthesis Phase] Starting self-checked synthesis for {asset_name} ({temporal_direction})...")

    # Step 1: Initial analysis
    state = analyze_impact(state, asset_class=asset_class)

    insight_output = state.get("insight_output", {})
    output_mode = insight_output.get("output_mode", "legacy")

    # Check if output was produced
    has_content = False
    if output_mode == "retrospective":
        has_content = bool(insight_output.get("causal_tracks"))
    elif output_mode == "prospective":
        has_content = bool(insight_output.get("scenarios"))
    else:
        has_content = bool(insight_output.get("tracks"))

    if not has_content:
        print("[Synthesis Phase] No output produced, skipping verification")
        return state

    # Step 2: Verification
    print("[Synthesis Phase] Running Sonnet verification...")

    data = _prepare_prompt_data(state, asset_class)
    insight_text = _format_insight_for_verification(insight_output)

    # Select verification prompt by mode
    if output_mode == "retrospective":
        verification_template = VERIFICATION_PROMPT_RETROSPECTIVE
    elif output_mode == "prospective":
        verification_template = VERIFICATION_PROMPT_PROSPECTIVE
    else:
        verification_template = VERIFICATION_PROMPT_RETROSPECTIVE  # fallback

    current_data_text = data.get("current_values_text", "")
    verification_prompt = verification_template.format(
        synthesis=data.get("synthesis", ""),
        chain_graph_text=data.get("chain_graph_text", "(none)"),
        historical_analogs_text=data.get("historical_analogs_text", "(none)"),
        current_data_text=current_data_text if current_data_text else "(none)",
        claim_validation_text=data.get("claim_validation_text", "(none)"),
        insight_output_text=insight_text,
    )

    debug_log("SYNTHESIS_VERIFICATION_PROMPT", verification_prompt)

    verification_result = call_claude_sonnet(
        [{"role": "user", "content": verification_prompt}],
        temperature=0.1,
        max_tokens=2000,
    )

    debug_log("SYNTHESIS_VERIFICATION_RESULT", verification_result)
    print(f"[Synthesis Phase] Verification result:\n{verification_result[:500]}")

    # Strip confirmation lines — only gaps matter for the patch prompt
    gap_lines = []
    for line in verification_result.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith(("\u2713", "\u2714", "\u2705")) or stripped == "":
            continue
        gap_lines.append(line)
    verification_for_patch = "\n".join(gap_lines).strip() if gap_lines else verification_result

    # Step 3: Check if gaps were found
    if "NO_GAPS" in verification_result.upper():
        print("[Synthesis Phase] Verification passed — no gaps found")
        debug_log_node("synthesis_phase", "EXIT", "verification=PASSED (no gaps)")
        return state

    # Step 4: Patch — re-run analysis with gap feedback appended
    print("[Synthesis Phase] Gaps found, running patch synthesis...")

    original_insight = state.get("insight_output", {})

    from models import call_claude_with_tools

    # Build patch prompt based on mode
    if output_mode == "retrospective":
        tool = _get_retrospective_tool()
        tool_name = "output_causal_decomposition"
        system_prompt = SYSTEM_PROMPT_RETROSPECTIVE
        original_prompt = get_retrospective_prompt(**data)
        parser = _parse_retrospective_result
        legacy_populator = _populate_legacy_fields_retrospective
    elif output_mode == "prospective":
        tool = _get_prospective_tool()
        tool_name = "output_scenario_analysis"
        system_prompt = SYSTEM_PROMPT_PROSPECTIVE
        skeleton = state.get("scenario_skeleton", {})
        original_prompt = get_prospective_prompt(**data, scenario_skeleton=skeleton)
        parser = _parse_prospective_result
        legacy_populator = _populate_legacy_fields_prospective
    else:
        # Legacy fallback
        tool = _get_insight_tool(asset_class)
        tool_name = "output_insight"
        system_prompt = SYSTEM_PROMPT_RETROSPECTIVE
        original_prompt = get_retrospective_prompt(**data)
        parser = _parse_insight_tool_result
        legacy_populator = _populate_legacy_fields_retrospective

    patched_prompt = (
        f"{original_prompt}\n\n"
        f"## QUALITY REVIEW FEEDBACK (address these gaps in your output)\n"
        f"{verification_for_patch}\n\n"
        f"IMPORTANT: Address ALL feedback items above."
    )

    model_short = _MODEL_SHORT_NAME.get(config.ANALYSIS_MODEL, "sonnet")

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": patched_prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            model=model_short,
            temperature=0.3,
            max_tokens=8000,
            system=system_prompt,
        )

        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                tool_input = block.input
                break

        if tool_input is None:
            print("[Synthesis Phase] Patch call produced no tool output, keeping original")
            return state

        parsed = parser(tool_input)

        # Guard: check patch has content
        if output_mode == "retrospective" and not parsed.get("causal_tracks"):
            print("[Synthesis Phase] Patch produced empty output, keeping original")
            return state
        elif output_mode == "prospective" and not parsed.get("scenarios"):
            print("[Synthesis Phase] Patch produced empty output, keeping original")
            return state

        state["insight_output"] = parsed
        legacy_populator(state, parsed)

        print(f"[Synthesis Phase] Patch applied ({output_mode})")
        debug_log_node("synthesis_phase", "EXIT", f"verification=GAPS_FOUND, patched ({output_mode})")

    except Exception as e:
        print(f"[Synthesis Phase] Patch failed ({e}), keeping original")
        debug_log_node("synthesis_phase", "EXIT", f"verification=GAPS_FOUND, patch_failed={e}")

    return state
