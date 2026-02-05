"""
Tests for Data Adapters

Tests the FRED, Yahoo, and CoinGecko adapters.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters import FREDAdapter, YahooAdapter, CoinGeckoAdapter


def test_fred_adapter_common_series():
    """Test that FRED adapter has common series mappings."""
    from adapters.fred_adapter import COMMON_FRED_SERIES

    assert "fed_funds_rate" in COMMON_FRED_SERIES
    assert "us_10y_yield" in COMMON_FRED_SERIES
    assert "us_cpi" in COMMON_FRED_SERIES
    print("[PASS] FRED common series mappings exist")


def test_yahoo_adapter_common_tickers():
    """Test that Yahoo adapter has common ticker mappings."""
    from adapters.yahoo_adapter import COMMON_YAHOO_TICKERS

    assert "spy" in COMMON_YAHOO_TICKERS
    assert "gold" in COMMON_YAHOO_TICKERS
    assert "btc" in COMMON_YAHOO_TICKERS
    print("[PASS] Yahoo common ticker mappings exist")


def test_coingecko_adapter_common_coins():
    """Test that CoinGecko adapter has common coin mappings."""
    from adapters.coingecko_adapter import COMMON_COINGECKO_COINS

    assert "btc" in COMMON_COINGECKO_COINS
    assert "eth" in COMMON_COINGECKO_COINS
    print("[PASS] CoinGecko common coin mappings exist")


def test_fred_adapter_validate_series():
    """Test FRED series validation (no API call)."""
    adapter = FREDAdapter()

    # Known valid series (structure check only)
    assert adapter.source_name == "FRED"
    print("[PASS] FRED adapter instantiates correctly")


def test_yahoo_adapter_validate_series():
    """Test Yahoo adapter validation."""
    adapter = YahooAdapter()

    assert adapter.source_name == "Yahoo"
    print("[PASS] Yahoo adapter instantiates correctly")


def test_coingecko_adapter_validate_series():
    """Test CoinGecko adapter validation."""
    adapter = CoinGeckoAdapter()

    assert adapter.source_name == "CoinGecko"
    print("[PASS] CoinGecko adapter instantiates correctly")


def test_yahoo_fetch_mock():
    """Test Yahoo fetch with mock data structure."""
    adapter = YahooAdapter()

    # Test that fetch returns expected structure (without actual API call)
    # This validates the interface, not the data
    end = datetime.now()
    start = end - timedelta(days=30)

    # The actual fetch would require yfinance, so we test structure
    assert hasattr(adapter, 'fetch')
    assert hasattr(adapter, 'validate_series')
    print("[PASS] Yahoo adapter has required methods")


def run_all_tests():
    """Run all adapter tests."""
    print("=" * 50)
    print("Running Adapter Tests")
    print("=" * 50)

    tests = [
        test_fred_adapter_common_series,
        test_yahoo_adapter_common_tickers,
        test_coingecko_adapter_common_coins,
        test_fred_adapter_validate_series,
        test_yahoo_adapter_validate_series,
        test_coingecko_adapter_validate_series,
        test_yahoo_fetch_mock,
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
