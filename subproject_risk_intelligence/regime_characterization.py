"""
Regime Characterization Module

Compares current macro regime vs historical analogs to produce
a structured "then vs now" assessment.
"""

import sys
from pathlib import Path

# Add parent for models import
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import call_claude_with_tools

from .states import RiskImpactState
from .current_data_fetcher import format_current_values_for_prompt
from .impact_analysis_prompts import REGIME_CHARACTERIZATION_PROMPT


REGIME_TOOL = {
    "name": "output_regime",
    "description": "Output regime characterization",
    "input_schema": {
        "type": "object",
        "properties": {
            "regime_name": {"type": "string"},
            "closest_analog": {"type": "string"},
            "similarities": {"type": "array", "items": {"type": "string"}},
            "differences": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"}
        },
        "required": ["regime_name", "summary"]
    }
}


def characterize_regime(state: RiskImpactState) -> RiskImpactState:
    """Characterize current macro regime vs historical analogs."""
    current_values = state.get("current_values", {})
    historical_analogs_text = state.get("historical_analogs_text", "")

    if not current_values or not historical_analogs_text:
        return state

    current_values_text = format_current_values_for_prompt(current_values)

    prompt = REGIME_CHARACTERIZATION_PROMPT.format(
        current_values_text=current_values_text,
        historical_analogs_text=historical_analogs_text,
    )

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[REGIME_TOOL],
            tool_choice={"type": "tool", "name": "output_regime"},
            model="haiku",
            temperature=0.2,
            max_tokens=1500,
        )

        regime = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_regime":
                regime = block.input
                break

        if regime is None:
            print("[Regime Characterization] No tool_use block found")
            return state

        text_lines = [f"**Current Regime**: {regime['regime_name']}"]
        if regime.get("closest_analog"):
            text_lines.append(f"**Closest Analog**: {regime['closest_analog']}")
        if regime.get("similarities"):
            text_lines.append("**Similarities**:")
            for s in regime["similarities"]:
                text_lines.append(f"  - {s}")
        if regime.get("differences"):
            text_lines.append("**Key Differences (this time is different)**:")
            for d in regime["differences"]:
                text_lines.append(f"  - {d}")
        text_lines.append(f"\n{regime.get('summary', '')}")

        state["regime_characterization_text"] = "\n".join(text_lines)
        print(f"[Regime Characterization] Regime: {regime['regime_name']}")

    except Exception as e:
        print(f"[Regime Characterization] Failed: {e}")

    return state
