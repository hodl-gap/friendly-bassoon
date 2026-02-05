"""
Tests for Validation Logic

Tests the statistical validation functions.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from validation_logic import (
    validate_single_claim,
    validate_correlation,
    validate_threshold,
    SCIPY_AVAILABLE
)


def test_validate_missing_data():
    """Test validation with missing data returns inconclusive."""
    claim = {
        "claim_text": "BTC follows gold",
        "variable_a": "btc",
        "variable_b": "gold",
        "relationship_type": "correlation"
    }

    fetched_data = {}  # Empty data

    result = validate_single_claim(claim, fetched_data)

    assert result["status"] == "inconclusive"
    assert "No data available" in result["reason"]
    print("[PASS] Missing data returns inconclusive")


def test_validate_threshold_breach():
    """Test threshold validation with breaches."""
    claim = {
        "claim_text": "Fed funds rate falls below 2%",
        "variable_a": "fed_funds",
        "relationship_type": "threshold",
        "parameters": {
            "threshold": {
                "value": 2.0,
                "condition": "less_than"
            }
        }
    }

    data = {
        "data": [
            ("2024-01-01", 5.25),
            ("2024-02-01", 5.00),
            ("2024-03-01", 1.50),  # Breach
            ("2024-04-01", 0.25),  # Breach
        ]
    }

    result = validate_threshold(claim, data)

    assert result["status"] == "confirmed"
    assert result["breach_count"] == 2
    print("[PASS] Threshold breach detected correctly")


def test_validate_threshold_no_breach():
    """Test threshold validation without breaches."""
    claim = {
        "claim_text": "Fed funds rate falls below 0%",
        "variable_a": "fed_funds",
        "relationship_type": "threshold",
        "parameters": {
            "threshold": {
                "value": 0.0,
                "condition": "less_than"
            }
        }
    }

    data = {
        "data": [
            ("2024-01-01", 5.25),
            ("2024-02-01", 5.00),
            ("2024-03-01", 1.50),
            ("2024-04-01", 0.25),
        ]
    }

    result = validate_threshold(claim, data)

    assert result["status"] == "refuted"
    assert result["breach_count"] == 0
    print("[PASS] No threshold breach detected correctly")


def test_scipy_import():
    """Test scipy availability check."""
    # Just verify the check works
    assert isinstance(SCIPY_AVAILABLE, bool)
    print(f"[PASS] scipy available: {SCIPY_AVAILABLE}")


def test_correlation_without_scipy():
    """Test correlation validation handles missing scipy."""
    if SCIPY_AVAILABLE:
        print("[SKIP] scipy is available, skipping missing scipy test")
        return

    claim = {
        "claim_text": "BTC correlates with gold",
        "variable_a": "btc",
        "variable_b": "gold",
        "relationship_type": "correlation"
    }

    data_a = {"data": [("2024-01-01", 100), ("2024-02-01", 110)]}
    data_b = {"data": [("2024-01-01", 1800), ("2024-02-01", 1850)]}

    result = validate_correlation(claim, data_a, data_b)

    assert result["status"] == "inconclusive"
    assert "scipy not available" in result["reason"]
    print("[PASS] Missing scipy handled correctly")


def run_all_tests():
    """Run all validation tests."""
    print("=" * 50)
    print("Running Validation Tests")
    print("=" * 50)

    tests = [
        test_validate_missing_data,
        test_validate_threshold_breach,
        test_validate_threshold_no_breach,
        test_scipy_import,
        test_correlation_without_scipy,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            if "SKIP" in str(e):
                skipped += 1
            else:
                print(f"[ERROR] {test.__name__}: {e}")
                failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 50)


if __name__ == "__main__":
    run_all_tests()
