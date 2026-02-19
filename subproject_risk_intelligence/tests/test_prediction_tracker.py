"""
Tests for prediction_tracker.py (Gap 5: Prediction Tracking).

Tests extract_predictions, log_predictions, check_outcomes,
get_chain_hit_rates, format_hit_rates_for_prompt, and ledger round-trip.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# Test data
# ============================================================================

def _make_state_with_tracks():
    """Create a mock RiskImpactState with insight_output tracks and source chains."""
    return {
        "query": "How does BOJ rate hike affect BTC?",
        "asset_class": "btc",
        "logic_chains": [
            {
                "relationship_id": "chain_boj_1",
                "steps": [
                    {"cause": "BOJ hike", "effect": "carry unwind",
                     "cause_normalized": "boj_hike", "effect_normalized": "carry_unwind"},
                    {"cause": "carry unwind", "effect": "BTC selloff",
                     "cause_normalized": "carry_unwind", "effect_normalized": "btc_selloff"},
                ],
            },
            {
                "relationship_id": "chain_risk_1",
                "chain_text": "risk_off -> btc_down -> further_selling",
            },
        ],
        "insight_output": {
            "tracks": [
                {
                    "title": "BOJ Tightening Track",
                    "confidence": 0.72,
                    "causal_mechanism": "boj_hike -> carry_unwind -> btc_selloff",
                    "time_horizon": "1-3 months",
                    "monitoring_variables": [
                        {"variable": "usdjpy", "condition": "< 145"}
                    ],
                    "asset_implications": [
                        {
                            "direction": "bearish",
                            "magnitude_range": "-20% to -30%",
                        }
                    ],
                },
                {
                    "title": "Carry Trade Unwind Track",
                    "confidence": 0.55,
                    "causal_mechanism": "carry_unwind -> risk_off -> btc_down",
                    "time_horizon": "2-4 weeks",
                    "monitoring_variables": [],
                    "asset_implications": [
                        {
                            "direction": "bearish",
                            "magnitude_range": "-10% to -15%",
                        }
                    ],
                },
                {
                    "title": "Empty Track",
                    "confidence": 0.3,
                    "causal_mechanism": "",
                    "time_horizon": "",
                    "monitoring_variables": [],
                    "asset_implications": [],  # No implications -> should be skipped
                },
            ]
        },
    }


# ============================================================================
# Tests
# ============================================================================

def test_extract_predictions():
    """Test extract_predictions with mock InsightTrack data."""
    from subproject_risk_intelligence.prediction_tracker import extract_predictions

    state = _make_state_with_tracks()
    predictions = extract_predictions(state, "btc")

    print(f"\n=== EXTRACT PREDICTIONS TEST ===")
    print(f"Extracted {len(predictions)} predictions")

    # Should produce 2 predictions (Empty Track has no implications -> skipped)
    assert len(predictions) == 2, f"Expected 2 predictions, got {len(predictions)}"

    # Check first prediction structure
    p1 = predictions[0]
    print(f"  P1 title: {p1['track_title']}")
    print(f"  P1 direction: {p1['direction']}")
    print(f"  P1 magnitude: [{p1['magnitude_min']}, {p1['magnitude_max']}]")
    print(f"  P1 time_horizon_days: {p1['time_horizon_days']}")

    assert p1["track_title"] == "BOJ Tightening Track"
    assert p1["direction"] == "bearish"
    assert p1["magnitude_min"] == -30.0
    assert p1["magnitude_max"] == -20.0
    assert p1["time_horizon_days"] == 60  # 1-3 months -> mid=2 -> 60 days
    assert p1["confidence"] == 0.72
    assert p1["status"] == "pending"
    assert p1["outcome"] is None
    assert p1["asset_class"] == "btc"
    assert len(p1["prediction_id"]) == 32  # MD5 hex digest

    # Check chain linkage — mechanism "boj_hike -> carry_unwind -> btc_selloff"
    # should match chain_boj_1 (has boj_hike, carry_unwind, btc_selloff)
    assert "chain_boj_1" in p1["related_chain_ids"], \
        f"Expected chain_boj_1 in related_chain_ids, got {p1['related_chain_ids']}"

    # Check second prediction
    p2 = predictions[1]
    assert p2["track_title"] == "Carry Trade Unwind Track"
    assert p2["magnitude_min"] == -15.0
    assert p2["magnitude_max"] == -10.0
    assert p2["time_horizon_days"] == 21  # 2-4 weeks -> mid=3 -> 21 days

    # Mechanism "carry_unwind -> risk_off -> btc_down"
    # should match chain_risk_1 (has risk_off, btc_down)
    assert "chain_risk_1" in p2["related_chain_ids"], \
        f"Expected chain_risk_1 in related_chain_ids, got {p2['related_chain_ids']}"

    print("PASSED")


def test_log_predictions_creates_file():
    """Test log_predictions creates ledger file and appends predictions."""
    from subproject_risk_intelligence.prediction_tracker import (
        extract_predictions, log_predictions,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"

        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path):
            state = _make_state_with_tracks()
            predictions = extract_predictions(state, "btc")

            # First log
            log_predictions(predictions)

            assert ledger_path.exists(), "Ledger file should be created"

            with open(ledger_path) as f:
                ledger = json.load(f)

            assert len(ledger["predictions"]) == 2
            assert ledger["metadata"]["total_predictions"] == 2

            # Second log (appends)
            log_predictions(predictions)

            with open(ledger_path) as f:
                ledger = json.load(f)

            assert len(ledger["predictions"]) == 4
            assert ledger["metadata"]["total_predictions"] == 4

    print("\n=== LOG PREDICTIONS TEST ===")
    print("PASSED")


def test_check_outcomes_confirmed():
    """Test check_outcomes: prediction bearish -25% actual -> confirmed."""
    from subproject_risk_intelligence.prediction_tracker import check_outcomes

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"
        past_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        check_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        ledger = {
            "metadata": {"created_at": past_date, "last_checked": None, "total_predictions": 1},
            "predictions": [
                {
                    "prediction_id": "test_confirmed",
                    "created_at": past_date,
                    "asset_class": "btc",
                    "direction": "bearish",
                    "magnitude_min": -30.0,
                    "magnitude_max": -20.0,
                    "time_horizon_days": 90,
                    "check_date": check_date,
                    "status": "pending",
                    "outcome": None,
                    "related_chain_ids": ["chain_1"],
                }
            ],
        }

        with open(ledger_path, "w") as f:
            json.dump(ledger, f)

        # Mock _fetch_actual_performance to return -25%
        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path), \
             patch("subproject_risk_intelligence.prediction_tracker._fetch_actual_performance", return_value=-25.0):
            evaluated = check_outcomes("btc")

        print(f"\n=== CHECK OUTCOMES (CONFIRMED) TEST ===")
        print(f"Evaluated {len(evaluated)} predictions")

        assert len(evaluated) == 1
        outcome = evaluated[0]["outcome"]
        print(f"  Score: {outcome['score']}")
        print(f"  Actual change: {outcome['actual_change_pct']}%")
        print(f"  Direction correct: {outcome['direction_correct']}")
        print(f"  Magnitude in range: {outcome['magnitude_in_range']}")

        assert outcome["score"] == "confirmed"
        assert outcome["direction_correct"] is True
        assert outcome["magnitude_in_range"] is True
        assert outcome["actual_change_pct"] == -25.0

        print("PASSED")


def test_check_outcomes_partial():
    """Test check_outcomes: direction correct but magnitude off -> partial."""
    from subproject_risk_intelligence.prediction_tracker import check_outcomes

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"
        past_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        check_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        ledger = {
            "metadata": {"created_at": past_date, "last_checked": None, "total_predictions": 1},
            "predictions": [
                {
                    "prediction_id": "test_partial",
                    "created_at": past_date,
                    "asset_class": "btc",
                    "direction": "bearish",
                    "magnitude_min": -30.0,
                    "magnitude_max": -20.0,
                    "time_horizon_days": 90,
                    "check_date": check_date,
                    "status": "pending",
                    "outcome": None,
                    "related_chain_ids": ["chain_1"],
                }
            ],
        }

        with open(ledger_path, "w") as f:
            json.dump(ledger, f)

        # Mock: -5% change (bearish direction correct, but magnitude too small)
        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path), \
             patch("subproject_risk_intelligence.prediction_tracker._fetch_actual_performance", return_value=-5.0):
            evaluated = check_outcomes("btc")

        print(f"\n=== CHECK OUTCOMES (PARTIAL) TEST ===")
        assert len(evaluated) == 1
        outcome = evaluated[0]["outcome"]
        print(f"  Score: {outcome['score']}")
        assert outcome["score"] == "partial"
        assert outcome["direction_correct"] is True
        assert outcome["magnitude_in_range"] is False

        print("PASSED")


def test_check_outcomes_refuted():
    """Test check_outcomes: bearish prediction but actual +10% -> refuted."""
    from subproject_risk_intelligence.prediction_tracker import check_outcomes

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"
        past_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        check_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        ledger = {
            "metadata": {"created_at": past_date, "last_checked": None, "total_predictions": 1},
            "predictions": [
                {
                    "prediction_id": "test_refuted",
                    "created_at": past_date,
                    "asset_class": "btc",
                    "direction": "bearish",
                    "magnitude_min": -30.0,
                    "magnitude_max": -20.0,
                    "time_horizon_days": 90,
                    "check_date": check_date,
                    "status": "pending",
                    "outcome": None,
                    "related_chain_ids": ["chain_2"],
                }
            ],
        }

        with open(ledger_path, "w") as f:
            json.dump(ledger, f)

        # Mock: +10% change (wrong direction)
        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path), \
             patch("subproject_risk_intelligence.prediction_tracker._fetch_actual_performance", return_value=10.0):
            evaluated = check_outcomes("btc")

        print(f"\n=== CHECK OUTCOMES (REFUTED) TEST ===")
        assert len(evaluated) == 1
        outcome = evaluated[0]["outcome"]
        print(f"  Score: {outcome['score']}")
        assert outcome["score"] == "refuted"
        assert outcome["direction_correct"] is False

        print("PASSED")


def test_check_outcomes_future_pending():
    """Test that predictions with future check_date are skipped (still pending)."""
    from subproject_risk_intelligence.prediction_tracker import check_outcomes

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        ledger = {
            "metadata": {"created_at": "2026-01-01", "last_checked": None, "total_predictions": 1},
            "predictions": [
                {
                    "prediction_id": "test_future",
                    "created_at": "2026-01-01",
                    "asset_class": "btc",
                    "direction": "bearish",
                    "magnitude_min": -30.0,
                    "magnitude_max": -20.0,
                    "time_horizon_days": 90,
                    "check_date": future_date,
                    "status": "pending",
                    "outcome": None,
                    "related_chain_ids": [],
                }
            ],
        }

        with open(ledger_path, "w") as f:
            json.dump(ledger, f)

        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path):
            evaluated = check_outcomes("btc")

        print(f"\n=== CHECK OUTCOMES (FUTURE/PENDING) TEST ===")
        assert len(evaluated) == 0, "Future predictions should be skipped"

        # Verify the prediction is still pending
        with open(ledger_path) as f:
            ledger = json.load(f)
        assert ledger["predictions"][0]["status"] == "pending"

        print("PASSED")


def test_get_chain_hit_rates():
    """Test get_chain_hit_rates computes correct ratios."""
    from subproject_risk_intelligence.prediction_tracker import get_chain_hit_rates

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"

        ledger = {
            "metadata": {"created_at": "2026-01-01", "last_checked": "2026-02-15", "total_predictions": 4},
            "predictions": [
                {
                    "prediction_id": "p1",
                    "status": "evaluated",
                    "related_chain_ids": ["chain_A"],
                    "outcome": {"score": "confirmed"},
                },
                {
                    "prediction_id": "p2",
                    "status": "evaluated",
                    "related_chain_ids": ["chain_A"],
                    "outcome": {"score": "confirmed"},
                },
                {
                    "prediction_id": "p3",
                    "status": "evaluated",
                    "related_chain_ids": ["chain_A", "chain_B"],
                    "outcome": {"score": "refuted"},
                },
                {
                    "prediction_id": "p4",
                    "status": "evaluated",
                    "related_chain_ids": ["chain_B"],
                    "outcome": {"score": "partial"},
                },
                {
                    "prediction_id": "p5",
                    "status": "pending",  # Should be ignored
                    "related_chain_ids": ["chain_A"],
                    "outcome": None,
                },
            ],
        }

        with open(ledger_path, "w") as f:
            json.dump(ledger, f)

        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path):
            hit_rates = get_chain_hit_rates(["chain_A", "chain_B", "chain_C"])

        print(f"\n=== GET CHAIN HIT RATES TEST ===")
        print(f"Chain A: {hit_rates.get('chain_A')}")
        print(f"Chain B: {hit_rates.get('chain_B')}")

        # chain_A: 3 evaluated (p1=confirmed, p2=confirmed, p3=refuted)
        assert hit_rates["chain_A"]["total"] == 3
        assert hit_rates["chain_A"]["confirmed"] == 2
        assert hit_rates["chain_A"]["refuted"] == 1
        assert abs(hit_rates["chain_A"]["hit_rate"] - 2/3) < 0.01

        # chain_B: 2 evaluated (p3=refuted, p4=partial)
        assert hit_rates["chain_B"]["total"] == 2
        assert hit_rates["chain_B"]["confirmed"] == 0
        assert hit_rates["chain_B"]["partial"] == 1
        assert hit_rates["chain_B"]["refuted"] == 1
        assert hit_rates["chain_B"]["hit_rate"] == 0.0

        # chain_C: not in ledger -> not in results
        assert "chain_C" not in hit_rates

        print("PASSED")


def test_format_hit_rates_for_prompt():
    """Test format_hit_rates_for_prompt produces readable output."""
    from subproject_risk_intelligence.prediction_tracker import format_hit_rates_for_prompt

    hit_rates = {
        "chain_A": {"hit_rate": 0.667, "total": 3, "confirmed": 2, "partial": 0, "refuted": 1},
        "chain_B": {"hit_rate": 0.0, "total": 2, "confirmed": 0, "partial": 1, "refuted": 1},
    }

    result = format_hit_rates_for_prompt(hit_rates)

    print(f"\n=== FORMAT HIT RATES TEST ===")
    print(result)

    assert "## CHAIN PREDICTION SCORECARD" in result
    assert "chain_A" in result
    assert "chain_B" in result
    assert "2/3" in result
    assert "67%" in result

    # Empty input returns empty string
    assert format_hit_rates_for_prompt({}) == ""

    print("PASSED")


def test_ledger_round_trip():
    """Test ledger file round-trip: write -> read -> verify structure."""
    from subproject_risk_intelligence.prediction_tracker import (
        extract_predictions, log_predictions, get_chain_hit_rates,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.json"

        with patch("subproject_risk_intelligence.config.PREDICTION_LEDGER_PATH", ledger_path):
            state = _make_state_with_tracks()
            predictions = extract_predictions(state, "btc")
            log_predictions(predictions)

            # Read back
            with open(ledger_path) as f:
                ledger = json.load(f)

            # Verify structure
            assert "metadata" in ledger
            assert "predictions" in ledger
            assert ledger["metadata"]["total_predictions"] == len(predictions)
            assert ledger["metadata"]["created_at"] is not None

            for p in ledger["predictions"]:
                assert "prediction_id" in p
                assert "created_at" in p
                assert "query" in p
                assert "asset_class" in p
                assert "track_title" in p
                assert "direction" in p
                assert "magnitude_min" in p
                assert "magnitude_max" in p
                assert "time_horizon_days" in p
                assert "check_date" in p
                assert "confidence" in p
                assert "status" in p
                assert p["status"] == "pending"
                assert p["outcome"] is None

    print(f"\n=== LEDGER ROUND-TRIP TEST ===")
    print("PASSED")


def test_link_prediction_to_chains():
    """Test _link_prediction_to_chains matches mechanism tokens to chain variables."""
    from subproject_risk_intelligence.prediction_tracker import _link_prediction_to_chains

    chains = [
        {
            "relationship_id": "chain_A",
            "steps": [
                {"cause_normalized": "boj_hike", "effect_normalized": "carry_unwind"},
                {"cause_normalized": "carry_unwind", "effect_normalized": "btc_selloff"},
            ],
        },
        {
            "relationship_id": "chain_B",
            "chain_text": "dxy_rise -> gold_drop -> mining_stress",
        },
        {
            "relationship_id": "chain_C",
            "steps": [
                {"cause_normalized": "fed_cut", "effect_normalized": "liquidity_rise"},
            ],
        },
    ]

    print(f"\n=== LINK PREDICTION TO CHAINS TEST ===")

    # Mechanism with 3 matching tokens -> should match chain_A
    result = _link_prediction_to_chains("boj_hike -> carry_unwind -> btc_selloff", chains)
    assert "chain_A" in result, f"Expected chain_A, got {result}"
    assert "chain_B" not in result
    assert "chain_C" not in result

    # Mechanism matching chain_text arrow notation -> should match chain_B
    result = _link_prediction_to_chains("dxy_rise -> gold_drop", chains)
    assert "chain_B" in result, f"Expected chain_B, got {result}"

    # Mechanism with only 1 overlapping token -> should NOT match (needs >= 2)
    result = _link_prediction_to_chains("carry_unwind -> something_else", chains)
    assert "chain_A" not in result, "Only 1 overlapping token, should not match"

    # Empty mechanism -> empty result
    result = _link_prediction_to_chains("", chains)
    assert result == []

    # No chains -> empty result
    result = _link_prediction_to_chains("boj_hike -> carry_unwind", [])
    assert result == []

    print("PASSED")


def test_parse_magnitude_range():
    """Test _parse_magnitude_range with various formats."""
    from subproject_risk_intelligence.prediction_tracker import _parse_magnitude_range

    print(f"\n=== PARSE MAGNITUDE RANGE TEST ===")

    # Standard range
    assert _parse_magnitude_range("-20% to -30%") == (-30.0, -20.0)
    assert _parse_magnitude_range("5% to 10%") == (5.0, 10.0)
    assert _parse_magnitude_range("+3% to +8%") == (3.0, 8.0)

    # Empty / None
    assert _parse_magnitude_range("") == (None, None)
    assert _parse_magnitude_range(None) == (None, None)

    print("PASSED")


def test_parse_time_horizon():
    """Test _parse_time_horizon with various formats."""
    from subproject_risk_intelligence.prediction_tracker import _parse_time_horizon

    print(f"\n=== PARSE TIME HORIZON TEST ===")

    assert _parse_time_horizon("1-3 months") == 60
    assert _parse_time_horizon("2-4 weeks") == 21
    assert _parse_time_horizon("1 week") == 7
    assert _parse_time_horizon("6 months") == 180
    assert _parse_time_horizon("") == 30  # default
    assert _parse_time_horizon(None) == 30  # default

    print("PASSED")


if __name__ == "__main__":
    test_extract_predictions()
    test_log_predictions_creates_file()
    test_check_outcomes_confirmed()
    test_check_outcomes_partial()
    test_check_outcomes_refuted()
    test_check_outcomes_future_pending()
    test_get_chain_hit_rates()
    test_format_hit_rates_for_prompt()
    test_ledger_round_trip()
    test_link_prediction_to_chains()
    test_parse_magnitude_range()
    test_parse_time_horizon()

    print("\n" + "=" * 60)
    print("ALL PREDICTION TRACKER TESTS PASSED")
    print("=" * 60)
