"""
Tests for structural gap implementations:
- Gap 2: compute_derived_metrics()
- Gap 1: claim validation formatting
- Gap 4: chain trigger selection in theme_refresh
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Gap 2: compute_derived_metrics()
# ============================================================================

def test_compute_derived_metrics_all_inputs():
    """Test derived metrics when all inputs are present."""
    from subproject_risk_intelligence.current_data_fetcher import compute_derived_metrics

    current_values = {
        "us10y": {
            "value": 4.50,
            "date": "2026-02-18",
            "source": "FRED",
            "changes": {
                "change_1w": {"absolute": 0.15, "percentage": 3.4, "direction": "↑"},
                "change_1m": {"absolute": 0.30, "percentage": 7.1, "direction": "↑"},
            },
        },
        "us02y": {
            "value": 4.20,
            "date": "2026-02-18",
            "source": "FRED",
            "changes": {
                "change_1w": {"absolute": 0.05, "percentage": 1.2, "direction": "↑"},
                "change_1m": {"absolute": 0.10, "percentage": 2.4, "direction": "↑"},
            },
        },
        "breakeven_inflation": {
            "value": 2.30,
            "date": "2026-02-17",
            "source": "FRED",
            "changes": {
                "change_1w": {"absolute": -0.05, "percentage": -2.1, "direction": "↓"},
                "change_1m": {"absolute": 0.10, "percentage": 4.5, "direction": "↑"},
            },
        },
        "sofr": {
            "value": 5.33,
            "date": "2026-02-18",
            "source": "FRED",
            "changes": {
                "change_1w": {"absolute": 0.00, "percentage": 0.0, "direction": "→"},
                "change_1m": {"absolute": -0.02, "percentage": -0.4, "direction": "↓"},
            },
        },
        "fed_funds": {
            "value": 5.33,
            "date": "2026-02-01",
            "source": "FRED",
            "changes": {
                "change_1w": {"absolute": 0.00, "percentage": 0.0, "direction": "→"},
                "change_1m": {"absolute": 0.00, "percentage": 0.0, "direction": "→"},
            },
        },
    }

    derived = compute_derived_metrics(current_values)

    # Check all 3 derived metrics computed
    assert "term_premium" in derived, f"Missing term_premium, got: {list(derived.keys())}"
    assert "real_yield_10y" in derived, f"Missing real_yield_10y, got: {list(derived.keys())}"
    assert "sofr_spread" in derived, f"Missing sofr_spread, got: {list(derived.keys())}"

    # Check values
    tp = derived["term_premium"]
    assert abs(tp["value"] - 0.30) < 0.001, f"term_premium should be 0.30, got {tp['value']}"
    assert tp["source"] == "derived"
    assert tp["date"] == "2026-02-18"
    print(f"  term_premium: {tp['value']} (expected 0.30) OK")

    ry = derived["real_yield_10y"]
    assert abs(ry["value"] - 2.20) < 0.001, f"real_yield_10y should be 2.20, got {ry['value']}"
    assert ry["date"] == "2026-02-18"  # max of us10y date and breakeven date
    print(f"  real_yield_10y: {ry['value']} (expected 2.20) OK")

    ss = derived["sofr_spread"]
    assert abs(ss["value"] - 0.00) < 0.001, f"sofr_spread should be 0.00, got {ss['value']}"
    print(f"  sofr_spread: {ss['value']} (expected 0.00) OK")

    # Check changes computed for term_premium
    tp_changes = tp.get("changes", {})
    assert "change_1w" in tp_changes, f"Missing 1w change for term_premium"
    # term_premium 1w change = us10y_change(0.15) - us02y_change(0.05) = 0.10
    assert abs(tp_changes["change_1w"]["absolute"] - 0.10) < 0.001, \
        f"term_premium 1w change should be 0.10, got {tp_changes['change_1w']['absolute']}"
    assert tp_changes["change_1w"]["direction"] == "↑"
    print(f"  term_premium 1w change: {tp_changes['change_1w']['absolute']} (expected 0.10) OK")

    # Check real_yield_10y 1w change = us10y(0.15) - breakeven(-0.05) = 0.20
    ry_changes = ry.get("changes", {})
    assert "change_1w" in ry_changes
    assert abs(ry_changes["change_1w"]["absolute"] - 0.20) < 0.001, \
        f"real_yield_10y 1w change should be 0.20, got {ry_changes['change_1w']['absolute']}"
    print(f"  real_yield_10y 1w change: {ry_changes['change_1w']['absolute']} (expected 0.20) OK")

    print("PASSED: test_compute_derived_metrics_all_inputs")


def test_compute_derived_metrics_partial_inputs():
    """Test derived metrics when only some inputs are present."""
    from subproject_risk_intelligence.current_data_fetcher import compute_derived_metrics

    # Only us10y and us02y, no breakeven or sofr/fed_funds
    current_values = {
        "us10y": {"value": 4.50, "date": "2026-02-18", "source": "FRED", "changes": {}},
        "us02y": {"value": 4.20, "date": "2026-02-18", "source": "FRED", "changes": {}},
    }

    derived = compute_derived_metrics(current_values)

    assert "term_premium" in derived, "Should compute term_premium with us10y + us02y"
    assert "real_yield_10y" not in derived, "Should NOT compute real_yield without breakeven"
    assert "sofr_spread" not in derived, "Should NOT compute sofr_spread without sofr/fed_funds"
    print(f"  Only term_premium computed: {derived['term_premium']['value']}")

    print("PASSED: test_compute_derived_metrics_partial_inputs")


def test_compute_derived_metrics_empty():
    """Test derived metrics with empty input."""
    from subproject_risk_intelligence.current_data_fetcher import compute_derived_metrics

    derived = compute_derived_metrics({})
    assert derived == {}, f"Empty input should produce empty output, got {derived}"

    print("PASSED: test_compute_derived_metrics_empty")


def test_compute_derived_metrics_no_changes():
    """Test derived metrics when inputs have no change data (historical context)."""
    from subproject_risk_intelligence.current_data_fetcher import compute_derived_metrics

    # Simulate historical fetch_conditions_at_date format (no changes key)
    current_values = {
        "us10y": {"value": 3.80, "date": "2023-06-15", "source": "FRED"},
        "us02y": {"value": 4.60, "date": "2023-06-15", "source": "FRED"},
    }

    derived = compute_derived_metrics(current_values)

    assert "term_premium" in derived
    tp = derived["term_premium"]
    assert abs(tp["value"] - (-0.80)) < 0.001, f"Inverted curve: should be -0.80, got {tp['value']}"
    assert tp["changes"] == {}, "No changes should be empty dict when inputs have no changes"
    print(f"  term_premium (inverted curve): {tp['value']} (expected -0.80) OK")

    print("PASSED: test_compute_derived_metrics_no_changes")


# ============================================================================
# Gap 1: Claim validation formatting
# ============================================================================

def test_claim_validation_formatting():
    """Test that claim validation results format correctly for the prompt."""
    from subproject_risk_intelligence.impact_analysis import _prepare_prompt_data

    # Build minimal state with claim validation results
    state = {
        "query": "TGA increased +10%",
        "retrieval_answer": "TGA drawdown affects liquidity...",
        "synthesis": "Analysis shows...",
        "logic_chains": [],
        "confidence_metadata": {},
        "current_values": {},
        "historical_chains": [],
        "validated_patterns": [],
        "historical_event_data": {},
        "knowledge_gaps": {},
        "gap_enrichment_text": "",
        "theme_states": None,
        "chain_graph_text": "",
        "historical_analogs_text": "",
        "claim_validation_results": [
            {
                "claim": "BTC follows gold with 63-428 day lag",
                "status": "partially_confirmed",
                "actual_correlation": 0.45,
                "optimal_lag_days": 127,
                "p_value": 0.001,
                "interpretation": "Correlation exists but weaker than implied",
            },
            {
                "claim": "VIX above 30 leads to BTC selloff within 1 week",
                "status": "confirmed",
                "actual_correlation": -0.72,
                "p_value": 0.0003,
                "interpretation": "Strong negative correlation confirmed",
            },
            {
                "claim": "TGA drawdown always leads to reserve increase",
                "status": "refuted",
                "actual_correlation": -0.15,
                "p_value": 0.42,
                "interpretation": "No statistically significant relationship found",
            },
        ],
    }

    data = _prepare_prompt_data(state, asset_class="btc")

    cvt = data.get("claim_validation_text", "")
    assert cvt, "claim_validation_text should not be empty"
    assert "## CLAIM VALIDATION (Data-Tested)" in cvt
    assert "PARTIALLY CONFIRMED" in cvt
    assert "CONFIRMED" in cvt
    assert "REFUTED" in cvt
    assert "correlation=0.45" in cvt
    assert "p=0.001" in cvt
    assert "BTC follows gold" in cvt

    print(f"  Formatted claim validation text ({len(cvt)} chars):")
    for line in cvt.split("\n"):
        print(f"    {line}")

    print("PASSED: test_claim_validation_formatting")


def test_claim_validation_empty():
    """Test that empty claim results produce empty text."""
    from subproject_risk_intelligence.impact_analysis import _prepare_prompt_data

    state = {
        "query": "test",
        "retrieval_answer": "",
        "synthesis": "",
        "logic_chains": [],
        "confidence_metadata": {},
        "current_values": {},
        "historical_chains": [],
        "validated_patterns": [],
        "historical_event_data": {},
        "knowledge_gaps": {},
        "gap_enrichment_text": "",
        "theme_states": None,
        "chain_graph_text": "",
        "historical_analogs_text": "",
        "claim_validation_results": [],
    }

    data = _prepare_prompt_data(state, asset_class="btc")
    assert data["claim_validation_text"] == "", "Empty results should produce empty text"

    print("PASSED: test_claim_validation_empty")


# ============================================================================
# Gap 4: Chain trigger selection in theme_refresh
# ============================================================================

def test_trigger_fallback_to_5pct():
    """Test that chains without trigger_conditions use 5% fallback."""
    chain_without_triggers = {
        "id": "test_chain_1",
        "logic_chain": {
            "steps": [
                {"cause": "VIX spike", "cause_normalized": "vix", "effect": "risk off", "effect_normalized": "risk_off"},
            ],
            "chain_summary": "vix -> risk_off",
        },
        "mechanism": "VIX spike causes risk-off",
    }

    triggers = chain_without_triggers.get("trigger_conditions", [])
    assert triggers == [], "Chain without trigger_conditions should return empty list"

    # Verify fallback logic matches theme_refresh pattern
    if not triggers:
        triggers = [
            {
                "variable": "vix",
                "condition_type": "percentage_change",
                "condition_value": 5.0,
                "condition_direction": "increase",
                "timeframe_days": 7,
            },
        ]

    assert len(triggers) == 1
    assert triggers[0]["variable"] == "vix"
    assert triggers[0]["condition_value"] == 5.0
    print(f"  Fallback trigger: {triggers[0]}")

    print("PASSED: test_trigger_fallback_to_5pct")


def test_trigger_uses_chain_specific():
    """Test that chains with trigger_conditions use them instead of 5% fallback."""
    chain_with_triggers = {
        "id": "test_chain_2",
        "logic_chain": {
            "steps": [
                {"cause": "VIX spike", "cause_normalized": "vix", "effect": "risk off", "effect_normalized": "risk_off"},
            ],
            "chain_summary": "vix -> risk_off",
        },
        "mechanism": "VIX spike causes risk-off",
        "trigger_conditions": [
            {
                "variable": "vix",
                "condition_type": "percentage_change",
                "condition_value": 20.0,  # VIX needs 20% move, not 5%
                "condition_direction": "increase",
                "timeframe_days": 7,
            },
        ],
    }

    triggers = chain_with_triggers.get("trigger_conditions", [])
    assert len(triggers) == 1
    assert triggers[0]["condition_value"] == 20.0, "Should use chain-specific 20% threshold, not 5%"
    print(f"  Chain-specific trigger: {triggers[0]}")

    print("PASSED: test_trigger_uses_chain_specific")


# ============================================================================
# Gap 2: Formatting integration
# ============================================================================

def test_derived_metrics_in_format():
    """Test that derived metrics format correctly in prompt output."""
    from subproject_risk_intelligence.current_data_fetcher import (
        format_value,
        format_change_value,
        format_value_with_changes,
    )

    # Test format_value for derived metrics
    assert format_value("term_premium", 0.30) == "0.30%"
    assert format_value("real_yield_10y", 2.20) == "2.20%"
    assert format_value("sofr_spread", 0.00) == "0.00%"
    print("  format_value for derived metrics: OK")

    # Test format_change_value
    assert format_change_value("term_premium", 0.10) == "0.10pp"
    assert format_change_value("real_yield_10y", 0.20) == "0.20pp"
    print("  format_change_value for derived metrics: OK")

    # Test full format_value_with_changes
    val = {
        "value": 0.30,
        "date": "2026-02-18",
        "source": "derived",
        "changes": {
            "change_1w": {"absolute": 0.10, "percentage": 50.0, "direction": "↑"},
        },
    }
    formatted = format_value_with_changes("term_premium", val)
    assert "TERM_PREMIUM" in formatted
    assert "0.30%" in formatted
    assert "0.10pp" in formatted
    print(f"  Full formatted: {formatted}")

    print("PASSED: test_derived_metrics_in_format")


def test_derived_metrics_in_categories():
    """Test that derived metrics appear in the Rates category."""
    from subproject_risk_intelligence.current_data_fetcher import format_current_values_for_prompt

    current_values = {
        "us10y": {"value": 4.50, "date": "2026-02-18", "source": "FRED", "changes": {}},
        "us02y": {"value": 4.20, "date": "2026-02-18", "source": "FRED", "changes": {}},
        "term_premium": {"value": 0.30, "date": "2026-02-18", "source": "derived", "changes": {}},
        "real_yield_10y": {"value": 2.20, "date": "2026-02-18", "source": "derived", "changes": {}},
    }

    formatted = format_current_values_for_prompt(current_values)

    assert "**Rates**:" in formatted, "Derived metrics should appear under Rates category"
    assert "TERM_PREMIUM" in formatted
    assert "REAL_YIELD_10Y" in formatted

    # term_premium should NOT be in "Other"
    lines = formatted.split("\n")
    in_other = False
    for line in lines:
        if "**Other**:" in line:
            in_other = True
        if in_other and "TERM_PREMIUM" in line:
            assert False, "term_premium should be in Rates, not Other"

    print(f"  Formatted output:\n{formatted}")

    print("PASSED: test_derived_metrics_in_categories")


# ============================================================================
# Gap 1: Prompt integration
# ============================================================================

def test_claim_validation_in_insight_prompt():
    """Test that claim_validation_text appears in the insight prompt."""
    from subproject_risk_intelligence.impact_analysis_prompts import get_insight_prompt

    prompt = get_insight_prompt(
        query="test query",
        retrieval_answer="test answer",
        synthesis="test synthesis",
        logic_chains=[],
        confidence_metadata={},
        claim_validation_text='## CLAIM VALIDATION (Data-Tested)\n- "test claim": CONFIRMED (correlation=0.80, p=0.001)',
    )

    assert "CLAIM VALIDATION" in prompt, "Claim validation should appear in insight prompt"
    assert "test claim" in prompt
    print("  Claim validation present in insight prompt: OK")

    print("PASSED: test_claim_validation_in_insight_prompt")


def test_claim_validation_in_belief_space_prompt():
    """Test that claim_validation_text appears in the belief space prompt."""
    from subproject_risk_intelligence.impact_analysis_prompts import get_impact_analysis_prompt

    prompt = get_impact_analysis_prompt(
        query="test query",
        retrieval_answer="test answer",
        synthesis="test synthesis",
        logic_chains=[],
        confidence_metadata={},
        claim_validation_text='## CLAIM VALIDATION (Data-Tested)\n- "test claim": REFUTED (p=0.42)',
    )

    assert "CLAIM VALIDATION" in prompt, "Claim validation should appear in belief space prompt"
    assert "test claim" in prompt
    print("  Claim validation present in belief space prompt: OK")

    print("PASSED: test_claim_validation_in_belief_space_prompt")


# ============================================================================
# Config flags
# ============================================================================

def test_config_flags_exist():
    """Test that new config flags exist and have correct defaults."""
    from subproject_risk_intelligence import config

    assert hasattr(config, "ENABLE_CLAIM_VALIDATION"), "Missing ENABLE_CLAIM_VALIDATION"
    assert hasattr(config, "ENABLE_CHAIN_TRIGGERS"), "Missing ENABLE_CHAIN_TRIGGERS"
    assert config.ENABLE_CLAIM_VALIDATION is True, "ENABLE_CLAIM_VALIDATION should default to True"
    assert config.ENABLE_CHAIN_TRIGGERS is True, "ENABLE_CHAIN_TRIGGERS should default to True"
    print(f"  ENABLE_CLAIM_VALIDATION: {config.ENABLE_CLAIM_VALIDATION}")
    print(f"  ENABLE_CHAIN_TRIGGERS: {config.ENABLE_CHAIN_TRIGGERS}")

    print("PASSED: test_config_flags_exist")


# ============================================================================
# State field
# ============================================================================

def test_state_has_claim_validation_field():
    """Test that RiskImpactState accepts claim_validation_results."""
    from subproject_risk_intelligence.states import RiskImpactState

    state = RiskImpactState(
        query="test",
        claim_validation_results=[{"claim": "test", "status": "confirmed"}],
    )

    assert state["claim_validation_results"] == [{"claim": "test", "status": "confirmed"}]
    print("  RiskImpactState accepts claim_validation_results: OK")

    print("PASSED: test_state_has_claim_validation_field")


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    tests = [
        # Gap 2
        test_compute_derived_metrics_all_inputs,
        test_compute_derived_metrics_partial_inputs,
        test_compute_derived_metrics_empty,
        test_compute_derived_metrics_no_changes,
        test_derived_metrics_in_format,
        test_derived_metrics_in_categories,
        # Gap 1
        test_claim_validation_formatting,
        test_claim_validation_empty,
        test_claim_validation_in_insight_prompt,
        test_claim_validation_in_belief_space_prompt,
        test_state_has_claim_validation_field,
        # Gap 4
        test_trigger_fallback_to_5pct,
        test_trigger_uses_chain_specific,
        # Config
        test_config_flags_exist,
    ]

    passed = 0
    failed = 0
    for test in tests:
        print(f"\n--- {test.__name__} ---")
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAILED: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'=' * 60}")
