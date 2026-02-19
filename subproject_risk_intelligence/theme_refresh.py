"""
Theme Refresh Module

Refreshes themes by:
1. Optionally running retrieval to discover new chains
2. Checking which chains are currently active based on market data
3. Generating per-theme assessments
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))

from shared.theme_config import get_all_themes, get_theme
from shared.theme_index import ThemeIndex
from . import config
from .pattern_validator import fetch_historical_for_pattern, evaluate_pattern
from .relationship_store import load_relationships


def refresh_theme(
    theme_name: str,
    skip_retrieval: bool = False,
    asset_class: str = "btc",
) -> Dict[str, Any]:
    """
    Refresh a single theme: fetch current data, check active chains, generate assessment.

    Args:
        theme_name: Theme to refresh (e.g., "liquidity")
        skip_retrieval: If True, skip retrieval step (use existing chains only)
        asset_class: Asset class for chain storage/loading (default: "btc")

    Returns:
        Dict with theme_name, active_chains, triggered_patterns, assessment
    """
    theme_def = get_theme(theme_name)
    theme_index_path = config.DATA_DIR / "theme_index.json"
    index = ThemeIndex.load(theme_index_path)

    print(f"\n[Theme Refresh] Refreshing theme: {theme_name}")

    # Step 1: Optionally run retrieval to discover new chains
    if not skip_retrieval:
        try:
            from retrieval_orchestrator import run_retrieval
            query = theme_def["query_template"]
            print(f"[Theme Refresh] Running retrieval: {query[:60]}...")
            result = run_retrieval(query, skip_gap_filling=True)

            # Extract and store any new chains discovered
            from .relationship_store import store_chains
            from .states import RiskImpactState
            state = RiskImpactState(
                query=query,
                retrieval_answer=result.get("answer", ""),
                confidence={"score": 0.5},
            )
            store_chains(state, asset_class=asset_class)
            # Reload index after potential new chains
            index = ThemeIndex.load(theme_index_path)
        except Exception as e:
            print(f"[Theme Refresh] Retrieval failed: {e}")

    # Step 2: Load chains for this theme
    db = load_relationships(asset_class=asset_class)
    all_chains = db.get("relationships", [])
    theme_chains = index.get_theme_chains(theme_name, all_chains)
    print(f"[Theme Refresh] {theme_name}: {len(theme_chains)} chains in theme")

    # Step 3: Check which chains are currently active
    active_chains = []
    triggered_patterns = []
    anchor_vars = theme_def["anchor_variables"]

    for chain in theme_chains:
        steps = chain.get("logic_chain", {}).get("steps", [])
        if not steps:
            continue

        # Check if the chain's cause variable has moved significantly
        cause_var = steps[0].get("cause_normalized", "")
        if not cause_var or cause_var not in anchor_vars:
            # Also check if cause_var is any anchor variable
            chain_vars = set()
            for step in steps:
                chain_vars.add(step.get("cause_normalized", ""))
                chain_vars.add(step.get("effect_normalized", ""))
            overlapping_anchors = chain_vars & set(anchor_vars)
            if overlapping_anchors:
                cause_var = list(overlapping_anchors)[0]
            else:
                continue

        # Use chain-specific triggers if available, else fall back to 5% heuristic
        triggers = chain.get("trigger_conditions", [])
        if not triggers:
            triggers = [
                {
                    "variable": cause_var,
                    "condition_type": "percentage_change",
                    "condition_value": 5.0,
                    "condition_direction": "increase",
                    "timeframe_days": 7,
                },
            ]

        # Evaluate each trigger pattern
        chain_triggered = False
        trigger_explanation = ""
        trigger_variable = cause_var
        try:
            for pattern in triggers:
                pattern_var = pattern.get("variable", cause_var)
                timeframe = pattern.get("timeframe_days", 7)
                data = fetch_historical_for_pattern(pattern_var, timeframe_days=timeframe)
                if data is None:
                    continue

                result = evaluate_pattern(pattern, data)

                # Check both directions if not triggered
                if not result.get("triggered"):
                    pattern_down = dict(pattern)
                    if pattern.get("condition_direction") == "increase":
                        pattern_down["condition_direction"] = "decrease"
                    elif pattern.get("condition_direction") == "decrease":
                        pattern_down["condition_direction"] = "increase"
                    else:
                        continue
                    result = evaluate_pattern(pattern_down, data)

                if result.get("triggered"):
                    chain_triggered = True
                    trigger_explanation = result.get("explanation", "")
                    trigger_variable = pattern_var
                    break

            if chain_triggered:
                active_chains.append(chain)
                triggered_patterns.append({
                    "variable": trigger_variable,
                    "chain_id": chain.get("id"),
                    "chain_summary": chain.get("logic_chain", {}).get("chain_summary", ""),
                    "explanation": trigger_explanation,
                })
        except Exception as e:
            # Data fetch failed for this variable, skip
            continue

    # Step 4: Generate assessment (template-based, no LLM)
    active_ids = [c.get("id") for c in active_chains if c.get("id")]
    if active_chains:
        triggered_vars = list(set(p["variable"] for p in triggered_patterns))
        assessment = f"{len(active_chains)} active chains. Triggered variables: {', '.join(triggered_vars)}"
    else:
        assessment = "No chains currently triggered"

    # Update theme index
    index.set_active_chains(theme_name, active_ids)
    index.set_assessment(theme_name, assessment)
    index.save(theme_index_path)

    print(f"[Theme Refresh] {theme_name}: {len(active_chains)} active chains, assessment: {assessment}")

    return {
        "theme_name": theme_name,
        "total_chains": len(theme_chains),
        "active_chains": active_chains,
        "triggered_patterns": triggered_patterns,
        "assessment": assessment,
    }


def refresh_all_themes(skip_retrieval: bool = False, asset_class: str = "btc") -> Dict[str, Dict[str, Any]]:
    """
    Refresh all themes.

    Args:
        skip_retrieval: If True, skip retrieval for all themes
        asset_class: Asset class for chain storage/loading (default: "btc")

    Returns:
        Dict mapping theme_name -> refresh result
    """
    # Check prediction outcomes (Gap 5)
    evaluated = []
    try:
        from . import config
        if config.ENABLE_PREDICTION_TRACKING:
            from .prediction_tracker import check_outcomes
            evaluated = check_outcomes(asset_class)
            if evaluated:
                print(f"[Prediction Tracker] Evaluated {len(evaluated)} predictions")
    except Exception as e:
        print(f"[Prediction Tracker] Outcome check error: {e}")

    results = {}
    for theme_name in get_all_themes():
        try:
            results[theme_name] = refresh_theme(theme_name, skip_retrieval=skip_retrieval, asset_class=asset_class)
        except Exception as e:
            print(f"[Theme Refresh] Error refreshing {theme_name}: {e}")
            results[theme_name] = {
                "theme_name": theme_name,
                "error": str(e),
                "active_chains": [],
                "triggered_patterns": [],
                "assessment": f"Error: {e}",
            }
    return results


def generate_briefing(theme_states: Dict[str, Dict[str, Any]]) -> str:
    """
    Generate a morning briefing summary from theme states.

    Template-based formatting, no LLM call.

    Args:
        theme_states: Dict from refresh_all_themes()

    Returns:
        Formatted briefing string
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Daily Regime Briefing — {now}",
        "",
    ]

    total_active = 0
    for theme_name, state in theme_states.items():
        active_count = len(state.get("active_chains", []))
        total_active += active_count
        total_chains = state.get("total_chains", 0)
        assessment = state.get("assessment", "N/A")

        status_marker = "!!!" if active_count > 0 else "   "
        lines.append(f"{status_marker} **{theme_name.upper()}**: {assessment}")
        lines.append(f"    Chains: {active_count} active / {total_chains} total")

        for pattern in state.get("triggered_patterns", []):
            lines.append(f"    - {pattern['variable']}: {pattern.get('explanation', '')}")
            lines.append(f"      Chain: {pattern.get('chain_summary', '')}")

        lines.append("")

    lines.insert(1, f"Active chains across all themes: {total_active}")
    lines.insert(2, "")

    # Prediction scorecard (Gap 5)
    try:
        from . import config
        if config.ENABLE_PREDICTION_TRACKING:
            import json as _json
            ledger_path = config.PREDICTION_LEDGER_PATH
            if ledger_path.exists():
                with open(ledger_path) as f:
                    ledger = _json.load(f)
                recent_evaluated = [p for p in ledger.get("predictions", []) if p.get("status") != "pending"]
                if recent_evaluated:
                    confirmed = sum(1 for p in recent_evaluated if p.get("outcome", {}).get("score") == "confirmed")
                    total_eval = len(recent_evaluated)
                    lines.append("")
                    lines.append(f"## PREDICTION SCORECARD")
                    lines.append(f"Evaluated: {total_eval} predictions, {confirmed} confirmed ({confirmed/total_eval*100:.0f}% hit rate)")
    except Exception:
        pass

    return "\n".join(lines)
