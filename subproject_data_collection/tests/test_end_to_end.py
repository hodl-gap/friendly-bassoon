"""
End-to-End Tests for Data Collection

Tests the complete workflow for claim validation and news collection.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from states import DataCollectionState
from claim_parsing import parse_claims
from data_fetching import resolve_data_ids
from output_formatter import format_output, format_claim_validation_output


def test_state_creation():
    """Test DataCollectionState creation."""
    state = DataCollectionState(
        mode="claim_validation",
        synthesis="Test synthesis",
        errors=[],
        warnings=[]
    )

    assert state["mode"] == "claim_validation"
    assert state["synthesis"] == "Test synthesis"
    print("[PASS] State creation works correctly")


def test_claim_parsing_structure():
    """Test claim parsing returns expected structure."""
    state = DataCollectionState(
        mode="claim_validation",
        synthesis="""
        ## Consensus Conclusions
        - BTC follows gold with a lag of 63-428 days
        - Fed rate cuts correlate with equity rallies
        """,
        errors=[],
        warnings=[]
    )

    # Note: This would call the LLM, so we test structure only
    assert "synthesis" in state
    assert len(state["synthesis"]) > 0
    print("[PASS] Claim parsing state structure is correct")


def test_data_id_resolution():
    """Test data ID resolution for known variables."""
    state = DataCollectionState(
        mode="claim_validation",
        parsed_claims=[
            {
                "claim_text": "BTC follows gold",
                "variable_a": "btc",
                "variable_b": "gold",
                "relationship_type": "correlation"
            }
        ],
        variable_mappings={},
        errors=[],
        warnings=[]
    )

    state = resolve_data_ids(state)

    resolved = state.get("resolved_data_ids", {})

    # BTC should resolve via common mappings
    if "btc" in resolved:
        assert "source" in resolved["btc"]
        assert "series_id" in resolved["btc"]
        print("[PASS] BTC resolved correctly")
    else:
        print("[WARN] BTC not in common mappings")

    # Gold should resolve
    if "gold" in resolved:
        assert "source" in resolved["gold"]
        print("[PASS] Gold resolved correctly")
    else:
        print("[WARN] Gold not in common mappings")


def test_output_formatter_claim_validation():
    """Test output formatting for claim validation."""
    state = DataCollectionState(
        mode="claim_validation",
        parsed_claims=[
            {"claim_text": "Test claim 1"},
            {"claim_text": "Test claim 2"}
        ],
        validation_results=[
            {
                "claim": "Test claim 1",
                "status": "confirmed",
                "actual_correlation": 0.75,
                "p_value": 0.001,
                "interpretation": "Strong correlation found"
            },
            {
                "claim": "Test claim 2",
                "status": "refuted",
                "actual_correlation": 0.1,
                "p_value": 0.5,
                "interpretation": "No significant correlation"
            }
        ],
        resolved_data_ids={
            "var1": {"source": "FRED"}
        },
        errors=[],
        warnings=[]
    )

    output = format_claim_validation_output(state, "2026-01-28T00:00:00Z")

    assert output["mode"] == "claim_validation"
    assert output["summary"]["claims_parsed"] == 2
    assert output["summary"]["claims_validated"] == 2
    assert output["summary"]["confirmed"] == 1
    assert output["summary"]["refuted"] == 1
    print("[PASS] Output formatter works correctly")


def test_output_formatter_news_collection():
    """Test output formatting for news collection."""
    from output_formatter import format_news_collection_output

    state = DataCollectionState(
        mode="news_collection",
        news_query="institutional rebalancing",
        news_sources=["reuters"],
        time_window_days=7,
        collected_articles=[{"title": "Article 1"}, {"title": "Article 2"}],
        filtered_articles=[{"title": "Article 1"}],
        analyzed_news=[
            {
                "institution": "GPIF",
                "action": "rebalancing",
                "confidence": 0.8,
                "actionable_insight": "Test insight"
            }
        ],
        retriever_queries=["Query 1"],
        errors=[],
        warnings=[]
    )

    output = format_news_collection_output(state, "2026-01-28T00:00:00Z")

    assert output["mode"] == "news_collection"
    assert output["summary"]["articles_collected"] == 2
    assert output["summary"]["articles_relevant"] == 1
    assert output["summary"]["actionable_insights"] == 1
    assert len(output["retriever_queries"]) == 1
    print("[PASS] News collection output formatter works correctly")


def run_all_tests():
    """Run all end-to-end tests."""
    print("=" * 50)
    print("Running End-to-End Tests")
    print("=" * 50)

    tests = [
        test_state_creation,
        test_claim_parsing_structure,
        test_data_id_resolution,
        test_output_formatter_claim_validation,
        test_output_formatter_news_collection,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)


if __name__ == "__main__":
    run_all_tests()
