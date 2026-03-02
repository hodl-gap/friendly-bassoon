"""Agentic data grounding phase — replaces the sequential extract/fetch/validate flow.

Agent can adaptively: fetch more variables, retry failed fetches,
validate claims iteratively, compute additional derived metrics.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.agent_loop import run_agent_loop
from shared.feature_flags import data_grounding_max_iterations
from .data_grounding_agent_prompts import DATA_GROUNDING_AGENT_SYSTEM_PROMPT
from .data_grounding_agent_tools import (
    ALL_TOOLS,
    DataGroundingAgentState,
    build_tool_handlers,
)
from .states import RiskImpactState


def run_data_grounding_agent(state: RiskImpactState) -> RiskImpactState:
    """
    Agentic data grounding: iteratively extracts variables, fetches data,
    validates claims and patterns.

    Returns: Updated state with current_values, claim_validation_results, etc.
    """
    from shared.debug_logger import debug_log_node
    debug_log_node("data_grounding_agent", "ENTER", f"query={state.get('query', '')[:100]}")
    print("\n[Data Grounding Agent] Starting agentic data grounding...")

    agent_state = DataGroundingAgentState(state)
    tool_handlers = build_tool_handlers(agent_state)

    # Build context summary for the agent
    query = state.get("query", "")
    synthesis = state.get("synthesis", "")
    chain_count = len(state.get("logic_chains", []))

    # Extract EDF routing directive: which data_api variables to ground
    data_directive = ""
    edf_tree = state.get("_edf_knowledge_tree")
    if edf_tree:
        from edf_decomposer import get_data_api_items
        items = get_data_api_items(edf_tree)
        if items:
            data_directive = "\n\nEDF data variables to ground:\n" + "\n".join(
                f"- {item['id']}: {item['description'][:80]}" for item in items
            )

    initial_message = (
        f"Research query: {query}\n\n"
        f"Synthesis:\n{synthesis}\n\n"
        f"Logic chains available: {chain_count}"
        f"{data_directive}\n\n"
        f"Extract variables from the research, fetch current data for each, "
        f"compute derived metrics, and validate patterns against current data."
    )

    loop_result = run_agent_loop(
        system_prompt=DATA_GROUNDING_AGENT_SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        tool_handlers=tool_handlers,
        initial_message=initial_message,
        exit_tool_name="finish_grounding",
        model="sonnet",
        max_iterations=data_grounding_max_iterations(),
        temperature=0.2,
        max_tokens=4000,
        phase_label="DataGrounding",
    )

    print(f"\n[Data Grounding Agent] Completed: {loop_result['exit_reason']} "
          f"({loop_result['iterations']} iterations, "
          f"{len(loop_result['tool_calls'])} tool calls)")

    # If agent didn't extract variables, do it now
    if not agent_state.extracted_variables:
        print("[Data Grounding Agent] Extracting variables (agent didn't do it)...")
        tool_handlers["extract_variables"]()

    # If agent didn't fetch any data, do it now
    if not agent_state.current_values and agent_state.extracted_variables:
        print("[Data Grounding Agent] Fetching data (agent didn't do it)...")
        from .current_data_fetcher import fetch_current_data
        temp_state = dict(state)
        temp_state["extracted_variables"] = agent_state.extracted_variables
        result = fetch_current_data(temp_state)
        agent_state.current_values = result.get("current_values", {})

    # Ensure always_include_variable is fetched + compute derived metrics
    from .asset_configs import get_asset_config
    from .current_data_fetcher import (
        resolve_variable, fetch_fred_with_history, fetch_yahoo_with_history,
        calculate_changes, compute_derived_metrics,
        MONTHLY_FRED_SERIES, MONTHLY_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS,
    )

    asset_class = state.get("asset_class", "btc")
    cfg = get_asset_config(asset_class)
    primary_var = cfg["always_include_variable"]

    if primary_var not in agent_state.current_values:
        print(f"[Data Grounding Agent] Fetching always_include_variable: {primary_var}")
        resolved = resolve_variable(primary_var)
        if resolved:
            series_id = resolved["series_id"]
            data_source = resolved["source"]
            lookback = MONTHLY_LOOKBACK_DAYS if series_id in MONTHLY_FRED_SERIES else DEFAULT_LOOKBACK_DAYS
            if data_source.upper() == "FRED":
                data = fetch_fred_with_history(series_id, lookback)
            else:
                data = fetch_yahoo_with_history(series_id, lookback)
            if data and data.get("value") is not None:
                history = data.pop("history", [])
                data["changes"] = calculate_changes(history)
                agent_state.current_values[primary_var] = data

    # Compute derived metrics from fetched data
    derived = compute_derived_metrics(agent_state.current_values)
    if derived:
        print(f"[Data Grounding Agent] Computed {len(derived)} derived metrics")
        agent_state.current_values.update(derived)

    # Update state with gathered data
    state["extracted_variables"] = agent_state.extracted_variables
    state["current_values"] = agent_state.current_values
    state["claim_validation_results"] = agent_state.claim_validation_results
    state["fetch_errors"] = agent_state.fetch_errors

    # Set asset_price for the target asset class
    if primary_var in agent_state.current_values:
        state["asset_price"] = agent_state.current_values[primary_var].get("value")
    if "btc" in agent_state.current_values:
        state["btc_price"] = agent_state.current_values["btc"].get("value")

    print(f"[Data Grounding Agent] Variables: {len(agent_state.extracted_variables)}, "
          f"Values: {len(agent_state.current_values)}")

    debug_log_node("data_grounding_agent", "EXIT", (
        f"variables={len(agent_state.extracted_variables)}, "
        f"values={len(agent_state.current_values)}, "
        f"claims={len(agent_state.claim_validation_results)}, "
        f"exit_reason={loop_result['exit_reason']}"
    ))
    return state
