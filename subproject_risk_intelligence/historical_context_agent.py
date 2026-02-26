"""Agentic historical context phase — replaces enrich_with_historical_event + characterize_regime.

Agent can: detect analogs, fetch data, compare regimes, discover that an analog
reveals a precondition worth checking in current data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.agent_loop import run_agent_loop
from shared.feature_flags import historical_max_iterations
from .historical_context_agent_prompts import HISTORICAL_CONTEXT_AGENT_SYSTEM_PROMPT
from .historical_context_agent_tools import (
    ALL_TOOLS,
    HistoricalAgentState,
    build_tool_handlers,
)
from .states import RiskImpactState
from . import config


def run_historical_context_agent(state: RiskImpactState) -> RiskImpactState:
    """
    Agentic historical context: iteratively detects analogs, fetches data,
    aggregates statistics, and characterizes the regime.

    Returns: Updated state with historical_analogs, historical_analogs_text,
             regime_characterization_text, etc.
    """
    from shared.debug_logger import debug_log_node

    if not config.ENABLE_HISTORICAL_EVENT_DETECTION:
        state["historical_event_data"] = {}
        return state

    debug_log_node("historical_context_agent", "ENTER", f"query={state.get('query', '')[:100]}")
    print("\n[Historical Context Agent] Starting agentic historical analysis...")

    agent_state = HistoricalAgentState(state)
    tool_handlers = build_tool_handlers(agent_state)

    query = state.get("query", "")
    synthesis_preview = state.get("synthesis", "")[:500]
    chain_count = len(state.get("logic_chains", []))
    current_values_count = len(state.get("current_values", {}))

    initial_message = (
        f"Research query: {query}\n\n"
        f"Synthesis preview: {synthesis_preview}\n\n"
        f"Logic chains available: {chain_count}\n"
        f"Current data variables: {current_values_count}\n\n"
        f"Find historical analogs for this event, fetch market data, "
        f"compute aggregate statistics, and characterize the current regime "
        f"relative to historical precedents."
    )

    loop_result = run_agent_loop(
        system_prompt=HISTORICAL_CONTEXT_AGENT_SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        tool_handlers=tool_handlers,
        initial_message=initial_message,
        exit_tool_name="finish_historical",
        model="sonnet",
        max_iterations=historical_max_iterations(),
        temperature=0.2,
        max_tokens=4000,
        phase_label="HistoricalContext",
    )

    print(f"\n[Historical Context Agent] Completed: {loop_result['exit_reason']} "
          f"({loop_result['iterations']} iterations, "
          f"{len(loop_result['tool_calls'])} tool calls)")

    # If agent didn't detect analogs or indicator extremes, run the standard enrichment as fallback
    if not agent_state.analogs and not agent_state.enriched_analogs and not agent_state.indicator_extremes_data:
        print("[Historical Context Agent] No analogs or indicator extremes found, running standard enrichment...")
        from .insight_orchestrator import enrich_with_historical_event
        state = enrich_with_historical_event(state)
        return state

    # Update state with gathered historical data
    if agent_state.enriched_analogs:
        state["historical_analogs"] = {
            "enriched": agent_state.enriched_analogs,
            "aggregated": agent_state.aggregated,
        }

    if agent_state.indicator_extremes_data:
        ha = state.get("historical_analogs", {})
        ha["indicator_extremes"] = agent_state.indicator_extremes_data
        state["historical_analogs"] = ha

    if agent_state.historical_analogs_text:
        state["historical_analogs_text"] = agent_state.historical_analogs_text

    if agent_state.regime_characterization_text:
        state["regime_characterization_text"] = agent_state.regime_characterization_text

    # Build historical_event_data from first analog for backward compat
    if agent_state.enriched_analogs:
        first = agent_state.enriched_analogs[0]
        market_data = first.get("market_data", {})
        state["historical_event_data"] = {
            "event_detected": True,
            "event_name": first.get("event_name", "Unknown"),
            "period": first.get("period", {}),
            "instruments": market_data.get("instruments", {}),
            "correlations": market_data.get("correlations", {}),
            "comparison_to_current": first.get("comparison", {}),
        }
    else:
        state["historical_event_data"] = {"event_detected": False}

    # Merge any additional data fetched by the agent into current_values
    if agent_state.additional_data:
        current_values = state.get("current_values", {})
        current_values.update(agent_state.additional_data)
        state["current_values"] = current_values

    analog_count = len(agent_state.enriched_analogs)
    print(f"[Historical Context Agent] Analogs: {analog_count}, "
          f"Regime: {'yes' if agent_state.regime_characterization_text else 'no'}")

    debug_log_node("historical_context_agent", "EXIT", (
        f"analogs={analog_count}, "
        f"regime={'yes' if agent_state.regime_characterization_text else 'no'}, "
        f"exit_reason={loop_result['exit_reason']}"
    ))
    return state
