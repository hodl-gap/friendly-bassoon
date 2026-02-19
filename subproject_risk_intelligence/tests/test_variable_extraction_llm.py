"""
Tests for LLM-powered variable extraction (Gap 4).

Tests extract_variables_llm, fallback behavior, priority variables,
and suggested_new field.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# Test data
# ============================================================================

def _make_state():
    """Create a mock state with query, synthesis, and logic chains."""
    return {
        "query": "How does Fed tightening affect BTC and carry trades?",
        "asset_class": "btc",
        "synthesis": "The Federal Reserve is tightening monetary policy by raising rates and reducing its balance sheet. "
                     "This drains bank reserves and increases funding costs. Higher rates strengthen the dollar (DXY rises), "
                     "which pressures carry trades, particularly USDJPY. Bitcoin historically correlates with liquidity conditions.",
        "logic_chains": [
            {
                "chain_text": "Fed hikes rates -> bank reserves fall -> funding stress increases -> risk assets sell off",
                "source": "GS Research"
            },
            {
                "steps": [
                    {"cause": "Fed balance sheet reduction", "effect": "TGA increases"},
                    {"cause": "TGA increases", "effect": "Bank reserves drain"},
                    {"cause": "Bank reserves drain", "effect": "BTC selloff"},
                ],
                "source": "BofA Macro"
            },
        ],
    }


def _mock_anthropic_response(variables, suggested_new=None):
    """Create a mock Anthropic API response with tool_use."""
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_variables"
    mock_block.input = {
        "variables": variables,
        "suggested_new": suggested_new or [],
    }

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 500
    mock_response.usage.output_tokens = 100

    return mock_response


# ============================================================================
# Tests
# ============================================================================

def test_extract_variables_llm_basic():
    """Test extract_variables_llm with mock LLM response returning variables."""
    from subproject_risk_intelligence.variable_extraction import extract_variables_llm

    state = _make_state()

    mock_response = _mock_anthropic_response(
        variables=["fed_funds", "bank_reserves", "fed_balance_sheet", "btc", "dxy", "usdjpy", "tga"],
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result = extract_variables_llm(state)

    print(f"\n=== LLM VARIABLE EXTRACTION BASIC TEST ===")
    print(f"Extracted: {sorted(result)}")

    assert isinstance(result, set)
    assert "fed_funds" in result
    assert "bank_reserves" in result
    assert "btc" in result
    assert "dxy" in result
    assert "usdjpy" in result
    assert "tga" in result
    assert "fed_balance_sheet" in result
    assert len(result) == 7

    print("PASSED")


def test_extract_variables_llm_implied():
    """Test that logically implied variables are included (e.g., Fed tightening -> fed_balance_sheet, bank_reserves)."""
    from subproject_risk_intelligence.variable_extraction import extract_variables_llm

    state = {
        "query": "What happens when the Fed tightens?",
        "synthesis": "The Federal Reserve is tightening. This reduces liquidity.",
        "logic_chains": [
            {"chain_text": "Fed tightens -> liquidity falls -> BTC drops"}
        ],
    }

    # LLM should infer implied variables beyond what keyword matching would find
    mock_response = _mock_anthropic_response(
        variables=["fed_balance_sheet", "bank_reserves", "rrp", "btc", "sofr", "fed_funds"],
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result = extract_variables_llm(state)

    print(f"\n=== LLM IMPLIED VARIABLES TEST ===")
    print(f"Extracted: {sorted(result)}")

    # These are logically implied but not in the text as keywords:
    assert "fed_balance_sheet" in result
    assert "bank_reserves" in result
    assert "rrp" in result
    assert "sofr" in result

    print("PASSED")


def test_extract_variables_llm_fallback():
    """Test fallback: when LLM call fails, extract_variables_llm returns None."""
    from subproject_risk_intelligence.variable_extraction import extract_variables_llm

    state = _make_state()

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result = extract_variables_llm(state)

    print(f"\n=== LLM FALLBACK TEST ===")
    print(f"Result on failure: {result}")

    assert result is None, "Should return None on API failure"

    print("PASSED")


def test_extract_variables_dispatch_llm():
    """Test that extract_variables uses LLM to supplement keyword extraction."""
    from subproject_risk_intelligence.variable_extraction import extract_variables

    state = _make_state()

    # LLM returns fed_funds (not findable by keywords) plus some overlap
    mock_response = _mock_anthropic_response(
        variables=["fed_funds", "bank_reserves", "btc", "dxy"],
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.config.USE_LLM_VARIABLE_EXTRACTION", True), \
         patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result_state = extract_variables(state)

    print(f"\n=== DISPATCH TO LLM TEST ===")
    extracted = result_state.get("extracted_variables", [])
    var_names = {v["normalized"] for v in extracted}
    print(f"Extracted variables: {sorted(var_names)}")

    # LLM-only variable should be present (not findable by keywords alone)
    assert "fed_funds" in var_names

    # Keyword-extracted variables should also be present (not replaced by LLM)
    assert "usdjpy" in var_names   # From synthesis keyword, NOT in LLM response
    assert "tga" in var_names      # From chain step text, NOT in LLM response

    # Variables found by both should be present
    assert "bank_reserves" in var_names
    assert "btc" in var_names
    assert "dxy" in var_names

    print("PASSED")


def test_llm_supplements_not_replaces():
    """Test that LLM extraction adds to keyword results, never replaces them."""
    from subproject_risk_intelligence.variable_extraction import extract_variables

    state = {
        "query": "How does Fed affect BTC?",
        "asset_class": "btc",
        "synthesis": "DXY is rising. VIX is elevated. USDJPY weakening.",
        "logic_chains": [
            {
                "steps": [
                    {"cause": "TGA drawdown", "effect": "Bank reserves increase",
                     "cause_normalized": "tga", "effect_normalized": "bank_reserves"},
                ],
                "source": "GS"
            }
        ],
    }

    # LLM returns only sofr and rrp (implied variables not in text)
    mock_response = _mock_anthropic_response(
        variables=["sofr", "rrp"],
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.config.USE_LLM_VARIABLE_EXTRACTION", True), \
         patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result_state = extract_variables(state)

    extracted = result_state.get("extracted_variables", [])
    var_names = {v["normalized"] for v in extracted}
    print(f"\n=== LLM SUPPLEMENTS NOT REPLACES TEST ===")
    print(f"Extracted variables: {sorted(var_names)}")

    # Keyword-extracted variables must still be present
    assert "dxy" in var_names       # From synthesis
    assert "vix" in var_names       # From synthesis
    assert "usdjpy" in var_names    # From synthesis
    assert "tga" in var_names       # From chain cause_normalized
    assert "bank_reserves" in var_names  # From chain effect_normalized

    # LLM-implied variables also present
    assert "sofr" in var_names
    assert "rrp" in var_names

    print("PASSED")


def test_extract_variables_dispatch_keyword_fallback():
    """Test that extract_variables falls back to keywords when LLM is disabled."""
    from subproject_risk_intelligence.variable_extraction import extract_variables

    state = _make_state()

    with patch("subproject_risk_intelligence.config.USE_LLM_VARIABLE_EXTRACTION", False):
        result_state = extract_variables(state)

    print(f"\n=== KEYWORD FALLBACK TEST ===")
    extracted = result_state.get("extracted_variables", [])
    var_names = {v["normalized"] for v in extracted}
    print(f"Extracted variables: {sorted(var_names)}")

    # Should have found variables from keyword patterns in synthesis text
    assert "btc" in var_names  # "Bitcoin" and "BTC" in synthesis
    assert "dxy" in var_names  # "DXY" in synthesis
    assert "usdjpy" in var_names  # "USDJPY" in synthesis

    print("PASSED")


def test_extract_variables_llm_with_suggested_new():
    """Test that unknown/novel variables are returned in suggested_new field."""
    from subproject_risk_intelligence.variable_extraction import extract_variables_llm

    state = _make_state()

    mock_response = _mock_anthropic_response(
        variables=["fed_funds", "btc"],
        suggested_new=["carry_trade_exposure", "jgb_yield_spread"],
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result = extract_variables_llm(state)

    print(f"\n=== SUGGESTED NEW VARIABLES TEST ===")
    print(f"Extracted: {sorted(result)}")
    print(f"Suggested new: {state.get('suggested_new_variables')}")

    assert "fed_funds" in result
    assert "btc" in result
    assert state.get("suggested_new_variables") == ["carry_trade_exposure", "jgb_yield_spread"]

    print("PASSED")


def test_priority_variables_always_included():
    """Test that get_priority_variables() are always included regardless of extraction method."""
    from subproject_risk_intelligence.variable_extraction import extract_variables

    state = {
        "query": "Something unrelated",
        "asset_class": "btc",
        "synthesis": "",
        "logic_chains": [],
    }

    # LLM returns empty set
    mock_response = _mock_anthropic_response(variables=[])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.config.USE_LLM_VARIABLE_EXTRACTION", True), \
         patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result_state = extract_variables(state)

    print(f"\n=== PRIORITY VARIABLES ALWAYS INCLUDED TEST ===")
    extracted = result_state.get("extracted_variables", [])
    var_names = {v["normalized"] for v in extracted}
    print(f"Variables (even with empty LLM result): {sorted(var_names)}")

    # Priority variables for BTC should always be present
    assert "btc" in var_names

    print("PASSED")


def test_extract_variables_llm_no_tool_use_block():
    """Test that extract_variables_llm returns None when LLM returns no tool_use block."""
    from subproject_risk_intelligence.variable_extraction import extract_variables_llm

    state = _make_state()

    # Response with text block instead of tool_use
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Some text response"

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 500
    mock_response.usage.output_tokens = 100

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.variable_extraction.anthropic.Anthropic", return_value=mock_client):
        result = extract_variables_llm(state)

    print(f"\n=== NO TOOL_USE BLOCK TEST ===")
    print(f"Result: {result}")

    assert result is None, "Should return None when no tool_use block present"

    print("PASSED")


if __name__ == "__main__":
    test_extract_variables_llm_basic()
    test_extract_variables_llm_implied()
    test_extract_variables_llm_fallback()
    test_extract_variables_dispatch_llm()
    test_llm_supplements_not_replaces()
    test_extract_variables_dispatch_keyword_fallback()
    test_extract_variables_llm_with_suggested_new()
    test_priority_variables_always_included()
    test_extract_variables_llm_no_tool_use_block()

    print("\n" + "=" * 60)
    print("ALL VARIABLE EXTRACTION LLM TESTS PASSED")
    print("=" * 60)
