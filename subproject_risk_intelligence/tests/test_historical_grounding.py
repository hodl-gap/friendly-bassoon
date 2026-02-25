"""
Tests for historical grounding (Gap 2).

Tests extract_analogs_from_context, validate_analog_mechanism,
detect_historical_analogs integration, and mechanism_match filtering.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# Test data
# ============================================================================

def _mock_anthropic_tool_response(tool_name, tool_input):
    """Create a mock Anthropic API response with a tool_use block."""
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = tool_name
    mock_block.input = tool_input

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 500
    mock_response.usage.output_tokens = 200

    return mock_response


# ============================================================================
# Tests
# ============================================================================

def test_extract_analogs_from_context_basic():
    """Test extract_analogs_from_context extracts events from synthesis + chains."""
    from subproject_risk_intelligence.historical_event_detector import extract_analogs_from_context

    synthesis = (
        "The BOJ rate hike in August 2024 triggered a massive yen carry trade unwind. "
        "BTC dropped 20% and VIX spiked to 65. This is similar to the 2022 Fed tightening "
        "cycle where aggressive rate hikes drained risk appetite and BTC fell from 69k to 16k."
    )

    logic_chains = [
        {
            "chain_text": "BOJ hikes rates -> carry unwind -> BTC selloff",
            "source": "GS Research",
            "source_type": "database",
        },
        {
            "chain_text": "Fed tightening -> dollar strengthens -> EM outflows -> risk off",
            "source": "Web: Reuters analysis",
            "source_type": "web",
        },
    ]

    # Mock Haiku to return 2 analogs extracted from the text
    mock_response = _mock_anthropic_tool_response(
        "extract_context_analogs",
        {
            "analogs": [
                {
                    "event_description": "August 2024 yen carry trade unwind",
                    "year": 2024,
                    "relevance_score": 0.85,
                    "date_search_query": "August 2024 yen carry trade crash exact dates",
                    "key_mechanism": "BOJ rate hike triggered carry trade unwind",
                },
                {
                    "event_description": "2022 Fed tightening cycle",
                    "year": 2022,
                    "relevance_score": 0.70,
                    "date_search_query": "2022 Fed tightening cycle dates market impact",
                    "key_mechanism": "Aggressive rate hikes drained risk appetite",
                },
            ]
        },
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.historical_event_detector.anthropic.Anthropic", return_value=mock_client):
        analogs = extract_analogs_from_context(synthesis, logic_chains, max_results=5)

    print(f"\n=== EXTRACT ANALOGS FROM CONTEXT TEST ===")
    print(f"Found {len(analogs)} analogs")

    assert len(analogs) == 2, f"Expected 2 analogs, got {len(analogs)}"

    # Check first analog
    a1 = analogs[0]
    print(f"  A1: {a1['event_description']} (source: {a1['source']})")
    assert a1["event_description"] == "August 2024 yen carry trade unwind"
    assert a1["source"] == "retrieved_context"
    assert a1["year"] == 2024
    assert a1["key_mechanism"] == "BOJ rate hike triggered carry trade unwind"
    assert a1["relevance_score"] == 0.85

    # Check second analog
    a2 = analogs[1]
    assert a2["event_description"] == "2022 Fed tightening cycle"
    assert a2["source"] == "retrieved_context"
    assert a2["year"] == 2022

    print("PASSED")


def test_extract_analogs_from_context_includes_web_chains():
    """Test that web chains are included in the context sent to LLM."""
    from subproject_risk_intelligence.historical_event_detector import extract_analogs_from_context

    synthesis = "Some synthesis text"
    logic_chains = [
        {
            "chain_text": "DB chain about carry trade",
            "source": "Morgan Stanley",
            "source_type": "database",
        },
        {
            "chain_text": "Web chain: In 2015 China devaluation, BTC dropped 30%",
            "source": "Web: Bloomberg",
            "source_type": "web",
        },
    ]

    mock_response = _mock_anthropic_tool_response(
        "extract_context_analogs",
        {
            "analogs": [
                {
                    "event_description": "2015 China yuan devaluation",
                    "year": 2015,
                    "relevance_score": 0.65,
                    "date_search_query": "2015 China yuan devaluation dates",
                    "key_mechanism": "China devalued yuan causing global risk-off",
                },
            ]
        },
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.historical_event_detector.anthropic.Anthropic", return_value=mock_client):
        analogs = extract_analogs_from_context(synthesis, logic_chains, max_results=5)

    print(f"\n=== WEB CHAINS INCLUDED TEST ===")

    # Verify the prompt sent to LLM includes web chain content
    call_args = mock_client.messages.create.call_args
    prompt_content = call_args[1]["messages"][0]["content"]
    assert "[web]" in prompt_content, "Web chain source_type should be visible in prompt"
    assert "[database]" in prompt_content, "DB chain source_type should be visible in prompt"

    assert len(analogs) == 1
    assert analogs[0]["source"] == "retrieved_context"

    print("PASSED")


def test_extract_analogs_from_context_empty():
    """Test extract_analogs_from_context with empty synthesis and no chains."""
    from subproject_risk_intelligence.historical_event_detector import extract_analogs_from_context

    analogs = extract_analogs_from_context("", [], max_results=5)

    print(f"\n=== EMPTY CONTEXT TEST ===")
    assert len(analogs) == 0

    print("PASSED")


def test_extract_analogs_from_context_api_error():
    """Test extract_analogs_from_context gracefully handles API errors."""
    from subproject_risk_intelligence.historical_event_detector import extract_analogs_from_context

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("subproject_risk_intelligence.historical_event_detector.anthropic.Anthropic", return_value=mock_client):
        analogs = extract_analogs_from_context("Some synthesis", [{"chain_text": "a -> b"}], max_results=5)

    print(f"\n=== API ERROR HANDLING TEST ===")
    assert len(analogs) == 0

    print("PASSED")


def test_validate_analog_mechanism_high_match():
    """Test validate_analog_mechanism: mechanism played out -> high mechanism_match."""
    from subproject_risk_intelligence.historical_aggregator import validate_analog_mechanism

    analog = {
        "event_description": "August 2024 yen carry trade unwind",
        "key_mechanism": "BOJ rate hike triggered carry trade unwind causing risk asset selloff",
    }

    market_data = {
        "instruments": {
            "USDJPY": {"metrics": {"peak_to_trough_pct": -8.5}},
            "BTC-USD": {"metrics": {"peak_to_trough_pct": -20.3}},
            "VIX": {"metrics": {"peak_to_trough_pct": 180.0}},
        }
    }

    mock_response = _mock_anthropic_tool_response(
        "validate_mechanism",
        {"mechanism_match": 0.9, "validation_note": "Market data strongly confirms carry unwind: USDJPY fell, BTC dropped, VIX spiked"},
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.historical_aggregator.anthropic.Anthropic", return_value=mock_client):
        result = validate_analog_mechanism(analog, market_data)

    print(f"\n=== VALIDATE MECHANISM (HIGH MATCH) TEST ===")
    print(f"  mechanism_match: {result['mechanism_match']}")
    print(f"  validation_note: {result['validation_note']}")

    assert result["mechanism_match"] == 0.9
    assert "carry unwind" in result["validation_note"].lower()

    print("PASSED")


def test_validate_analog_mechanism_low_match():
    """Test validate_analog_mechanism: mechanism didn't play out -> low mechanism_match."""
    from subproject_risk_intelligence.historical_aggregator import validate_analog_mechanism

    analog = {
        "event_description": "Some unrelated event",
        "key_mechanism": "Rate cuts cause bond rally and equity selloff",
    }

    market_data = {
        "instruments": {
            "SPY": {"metrics": {"peak_to_trough_pct": 5.2}},  # Equity went UP
            "TNX": {"metrics": {"peak_to_trough_pct": 2.1}},  # Yields went UP (no bond rally)
        }
    }

    mock_response = _mock_anthropic_tool_response(
        "validate_mechanism",
        {"mechanism_match": 0.15, "validation_note": "Data contradicts mechanism: equities rose and yields rose"},
    )

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("subproject_risk_intelligence.historical_aggregator.anthropic.Anthropic", return_value=mock_client):
        result = validate_analog_mechanism(analog, market_data)

    print(f"\n=== VALIDATE MECHANISM (LOW MATCH) TEST ===")
    print(f"  mechanism_match: {result['mechanism_match']}")

    assert result["mechanism_match"] == 0.15
    assert result["mechanism_match"] < 0.3  # Below threshold

    print("PASSED")


def test_validate_analog_mechanism_no_mechanism():
    """Test validate_analog_mechanism with empty mechanism string."""
    from subproject_risk_intelligence.historical_aggregator import validate_analog_mechanism

    analog = {"event_description": "Some event", "key_mechanism": ""}
    market_data = {"instruments": {"BTC-USD": {"metrics": {"peak_to_trough_pct": -10.0}}}}

    result = validate_analog_mechanism(analog, market_data)

    print(f"\n=== VALIDATE MECHANISM (NO MECHANISM) TEST ===")
    assert result["mechanism_match"] == 0.5
    assert "No mechanism" in result["validation_note"]

    print("PASSED")


def test_validate_analog_mechanism_no_data():
    """Test validate_analog_mechanism with empty market data."""
    from subproject_risk_intelligence.historical_aggregator import validate_analog_mechanism

    analog = {"event_description": "Some event", "key_mechanism": "rate hike -> selloff"}
    market_data = {"instruments": {}}

    result = validate_analog_mechanism(analog, market_data)

    print(f"\n=== VALIDATE MECHANISM (NO DATA) TEST ===")
    assert result["mechanism_match"] == 0.5
    assert "Insufficient" in result["validation_note"]

    print("PASSED")


def test_detect_historical_analogs_from_context():
    """Test detect_historical_analogs: only returns context-grounded analogs."""
    from subproject_risk_intelligence.historical_event_detector import detect_historical_analogs

    context_analogs = [
        {
            "event_description": "August 2024 yen carry unwind",
            "year": 2024,
            "relevance_score": 0.75,
            "date_search_query": "August 2024 yen carry trade crash dates",
            "key_mechanism": "BOJ hike -> carry unwind",
            "source": "retrieved_context",
        },
        {
            "event_description": "2022 Fed tightening cycle",
            "year": 2022,
            "relevance_score": 0.60,
            "date_search_query": "2022 Fed tightening dates",
            "key_mechanism": "Rate hikes -> risk off",
            "source": "retrieved_context",
        },
    ]

    with patch("subproject_risk_intelligence.config.ENABLE_RESEARCH_ANALOG_SEARCH", True), \
         patch("subproject_risk_intelligence.historical_event_detector.extract_analogs_from_context", return_value=context_analogs):
        result = detect_historical_analogs(
            query="How does BOJ rate hike affect carry trades?",
            synthesis="BOJ is expected to hike rates...",
            logic_chains=[],
            max_analogs=5,
            relevance_threshold=0.5,
        )

    print(f"\n=== DETECT ANALOGS (CONTEXT ONLY) TEST ===")
    print(f"Total analogs: {len(result)}")
    for a in result:
        print(f"  {a['event_description']} (relevance: {a.get('relevance_score', 0):.2f}, source: {a.get('source', '?')})")

    assert len(result) == 2

    # Context analogs should have boosted relevance (+0.15) and appear first
    assert result[0]["source"] == "retrieved_context"
    assert result[0]["relevance_score"] == 0.90  # 0.75 + 0.15

    assert result[1]["source"] == "retrieved_context"
    assert result[1]["relevance_score"] == 0.75  # 0.60 + 0.15

    print("PASSED")


def test_detect_historical_analogs_context_disabled():
    """Test detect_historical_analogs returns empty when context extraction is disabled."""
    from subproject_risk_intelligence.historical_event_detector import detect_historical_analogs

    with patch("subproject_risk_intelligence.config.ENABLE_RESEARCH_ANALOG_SEARCH", False):
        result = detect_historical_analogs(
            query="What happened in crypto winter?",
            synthesis="Crypto markets...",
            logic_chains=[],
            max_analogs=5,
            relevance_threshold=0.5,
        )

    print(f"\n=== CONTEXT EXTRACTION DISABLED TEST ===")
    assert len(result) == 0

    print("PASSED")


def test_mechanism_match_filtering():
    """Test that analogs below MECHANISM_MATCH_THRESHOLD are filtered out in fetch_multiple_analogs."""
    from subproject_risk_intelligence.historical_aggregator import fetch_multiple_analogs

    analogs = [
        {
            "event_description": "Good analog",
            "date_search_query": "good analog dates",
            "relevance_score": 0.8,
            "key_mechanism": "carry unwind -> risk off",
        },
        {
            "event_description": "Bad analog",
            "date_search_query": "bad analog dates",
            "relevance_score": 0.7,
            "key_mechanism": "irrelevant mechanism",
        },
    ]

    with patch("subproject_risk_intelligence.config.ENABLE_MECHANISM_VALIDATION", True), \
         patch("subproject_risk_intelligence.config.MECHANISM_MATCH_THRESHOLD", 0.3), \
         patch("subproject_risk_intelligence.historical_aggregator.get_date_range", return_value={"start_date": "2024-08-01", "end_date": "2024-08-15", "peak_date": None}), \
         patch("subproject_risk_intelligence.historical_aggregator.identify_instruments", return_value=[]), \
         patch("subproject_risk_intelligence.historical_aggregator.fetch_historical_event_data", return_value={"instruments": {"BTC-USD": {"metrics": {"peak_to_trough_pct": -10.0}}}, "correlations": {}}), \
         patch("subproject_risk_intelligence.historical_aggregator.compare_to_current", return_value={}), \
         patch("subproject_risk_intelligence.historical_aggregator.validate_analog_mechanism") as mock_validate:

        def validate_side_effect(analog, market_data):
            if "Good" in analog["event_description"]:
                return {"mechanism_match": 0.85, "validation_note": "Strong match"}
            else:
                return {"mechanism_match": 0.1, "validation_note": "No match"}

        mock_validate.side_effect = validate_side_effect

        result = fetch_multiple_analogs(
            analogs=analogs,
            query="test query",
            synthesis="test synthesis",
            logic_chains=[],
            current_values={},
            asset_class="btc",
        )

    print(f"\n=== MECHANISM MATCH FILTERING TEST ===")
    print(f"Result count: {len(result)} (from {len(analogs)} input)")
    for a in result:
        print(f"  {a['event_description']}: mechanism_match={a.get('mechanism_match', 'N/A')}")

    # Only "Good analog" should survive (0.85 >= 0.3)
    assert len(result) == 1
    assert result[0]["event_description"] == "Good analog"
    assert result[0]["mechanism_match"] == 0.85

    print("PASSED")


def test_relevance_score_boost():
    """Test that context-extracted analogs get +0.15 relevance score boost."""
    from subproject_risk_intelligence.historical_event_detector import detect_historical_analogs

    context_analogs = [
        {
            "event_description": "Test event",
            "year": 2024,
            "relevance_score": 0.70,  # Should become 0.85 after boost
            "date_search_query": "test dates",
            "key_mechanism": "test mechanism",
            "source": "retrieved_context",
        },
    ]

    with patch("subproject_risk_intelligence.config.ENABLE_RESEARCH_ANALOG_SEARCH", True), \
         patch("subproject_risk_intelligence.historical_event_detector.extract_analogs_from_context", return_value=context_analogs):
        result = detect_historical_analogs(
            query="test",
            synthesis="test",
            logic_chains=[],
            max_analogs=5,
            relevance_threshold=0.5,
        )

    print(f"\n=== RELEVANCE SCORE BOOST TEST ===")
    assert len(result) == 1
    assert result[0]["relevance_score"] == 0.85  # 0.70 + 0.15

    print("PASSED")


def test_relevance_score_boost_capped_at_1():
    """Test that relevance score boost is capped at 1.0."""
    from subproject_risk_intelligence.historical_event_detector import detect_historical_analogs

    context_analogs = [
        {
            "event_description": "Very relevant event",
            "year": 2024,
            "relevance_score": 0.95,  # 0.95 + 0.15 = 1.10 -> capped at 1.0
            "date_search_query": "test dates",
            "key_mechanism": "test mechanism",
            "source": "retrieved_context",
        },
    ]

    with patch("subproject_risk_intelligence.config.ENABLE_RESEARCH_ANALOG_SEARCH", True), \
         patch("subproject_risk_intelligence.historical_event_detector.extract_analogs_from_context", return_value=context_analogs):
        result = detect_historical_analogs(
            query="test",
            synthesis="test",
            logic_chains=[],
            max_analogs=5,
            relevance_threshold=0.5,
        )

    print(f"\n=== RELEVANCE SCORE CAP TEST ===")
    assert len(result) == 1
    assert result[0]["relevance_score"] == 1.0  # Capped

    print("PASSED")


def test_extract_year():
    """Test _extract_year helper with various period strings."""
    from subproject_risk_intelligence.historical_event_detector import _extract_year

    print(f"\n=== EXTRACT YEAR TEST ===")

    assert _extract_year("August 2024") == 2024
    assert _extract_year("2022") == 2022
    assert _extract_year("March 2020 - April 2020") == 2020
    assert _extract_year("Q1 2018") == 2018
    assert _extract_year("") == 0
    assert _extract_year("no year here") == 0

    print("PASSED")


if __name__ == "__main__":
    test_extract_analogs_from_context_basic()
    test_extract_analogs_from_context_includes_web_chains()
    test_extract_analogs_from_context_empty()
    test_extract_analogs_from_context_api_error()
    test_validate_analog_mechanism_high_match()
    test_validate_analog_mechanism_low_match()
    test_validate_analog_mechanism_no_mechanism()
    test_validate_analog_mechanism_no_data()
    test_detect_historical_analogs_integration()
    test_detect_historical_analogs_context_disabled()
    test_mechanism_match_filtering()
    test_relevance_score_boost()
    test_relevance_score_boost_capped_at_1()
    test_extract_year()

    print("\n" + "=" * 60)
    print("ALL HISTORICAL GROUNDING TESTS PASSED")
    print("=" * 60)
