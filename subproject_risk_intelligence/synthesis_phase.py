"""Synthesis self-check phase — verifies and patches insight output.

Phase 4: Structured synthesis with self-verification.
1. Call Opus with output_insight tool (same as current _analyze_insight)
2. Send output to Sonnet verifier: "Does this report address all mechanisms?"
3. If verifier finds gaps, one more Opus call with gap feedback appended
4. Return (possibly patched) output
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_sonnet

from .states import RiskImpactState
from .impact_analysis import analyze_impact, _prepare_prompt_data, _get_insight_tool, _parse_insight_tool_result, _MODEL_SHORT_NAME
from .impact_analysis_prompts import INSIGHT_SYSTEM_PROMPT, get_insight_prompt
from .current_data_fetcher import format_current_values_for_prompt
from .synthesis_prompts import VERIFICATION_PROMPT
from .asset_configs import get_asset_config
from . import config


def _format_insight_for_verification(insight_output: dict) -> str:
    """Format structured insight output as readable text for the verifier."""
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
            for p in evidence.get("precedents", [])[:3]:
                lines.append(f"    - {p.get('event', '')}: {p.get('outcome', '')} ({p.get('magnitude', '')})")

        for imp in track.get("asset_implications", []):
            lines.append(f"  {imp.get('asset', '?')}: {imp.get('direction', '?')} "
                        f"({imp.get('magnitude_range', '')}, {imp.get('timing', '')})")

        for m in track.get("monitoring_variables", []):
            lines.append(f"  Monitor: {m.get('variable', '?')} {m.get('condition', '?')}: {m.get('meaning', '')}")

        lines.append("")

    if synthesis:
        lines.append(f"SYNTHESIS: {synthesis}")
    if uncertainties:
        lines.append(f"UNCERTAINTIES: {', '.join(uncertainties)}")

    return "\n".join(lines)


def run_synthesis_phase(state: RiskImpactState, asset_class: str) -> RiskImpactState:
    """
    Phase 4: Structured synthesis with self-verification.

    Step 1: Call analyze_impact (same as current pipeline — Opus + output_insight tool)
    Step 2: Sonnet verifier checks if all evidence was addressed
    Step 3: If gaps found, one more Opus call with gap feedback
    Step 4: Return (possibly patched) output
    """
    from shared.debug_logger import debug_log, debug_log_node

    asset_name = get_asset_config(asset_class)["name"]
    debug_log_node("synthesis_phase", "ENTER", f"asset={asset_class} ({asset_name})")
    print(f"\n[Synthesis Phase] Starting self-checked synthesis for {asset_name}...")

    # Step 1: Initial analysis (reuses existing _analyze_insight)
    state = analyze_impact(state, asset_class=asset_class)

    insight_output = state.get("insight_output", {})
    if not insight_output or not insight_output.get("tracks"):
        print("[Synthesis Phase] No tracks produced, skipping verification")
        return state

    # Step 2: Verification
    print("[Synthesis Phase] Running Sonnet verification...")

    data = _prepare_prompt_data(state, asset_class)
    insight_text = _format_insight_for_verification(insight_output)

    current_data_text = data.get("current_values_text", "")
    verification_prompt = VERIFICATION_PROMPT.format(
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
        max_tokens=800,
    )

    debug_log("SYNTHESIS_VERIFICATION_RESULT", verification_result)
    print(f"[Synthesis Phase] Verification result:\n{verification_result[:500]}")

    # Step 3: Check if gaps were found
    if "NO_GAPS" in verification_result.upper():
        print("[Synthesis Phase] Verification passed — no gaps found")
        debug_log_node("synthesis_phase", "EXIT", "verification=PASSED (no gaps)")
        return state

    # Step 4: Patch — re-run analysis with gap feedback appended
    print("[Synthesis Phase] Gaps found, running patch synthesis...")

    from models import call_claude_with_tools
    insight_tool = _get_insight_tool(asset_class)
    original_prompt = get_insight_prompt(**data)

    patched_prompt = (
        f"{original_prompt}\n\n"
        f"## QUALITY REVIEW FEEDBACK (address these gaps in your output)\n"
        f"{verification_result}\n\n"
        f"IMPORTANT: Address ALL feedback items above. "
        f"Ensure every causal mechanism from the evidence appears in a track. "
        f"Include quantified historical precedents. "
        f"Add specific monitoring thresholds."
    )

    model_short = _MODEL_SHORT_NAME.get(config.ANALYSIS_MODEL, "sonnet")

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": patched_prompt}],
            tools=[insight_tool],
            tool_choice={"type": "tool", "name": "output_insight"},
            model=model_short,
            temperature=0.3,
            max_tokens=8192,
            system=INSIGHT_SYSTEM_PROMPT,
        )

        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_insight":
                tool_input = block.input
                break

        if tool_input is None:
            print("[Synthesis Phase] Patch call produced no tool output, keeping original")
            return state

        parsed = _parse_insight_tool_result(tool_input)
        state["insight_output"] = parsed
        state["output_mode"] = "insight"

        # Update legacy fields from patched output
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

        print(f"[Synthesis Phase] Patch applied — {len(tracks)} tracks")
        debug_log_node("synthesis_phase", "EXIT", f"verification=GAPS_FOUND, patched={len(tracks)} tracks")

    except Exception as e:
        print(f"[Synthesis Phase] Patch failed ({e}), keeping original")
        debug_log_node("synthesis_phase", "EXIT", f"verification=GAPS_FOUND, patch_failed={e}")

    return state
