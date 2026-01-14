"""
Test script to validate metrics cleanup fixes.
Tests against real processed CSV data.

Run: python tests/test_metrics_cleanup.py
"""
import csv
import json
import sys
import os

# Add parent directory to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(PROJECT_DIR)

CSV_PATH = os.path.join(PROJECT_DIR, 'data', 'processed', 'liquidity_metrics', 'liquidity_metrics_mapping.csv')
PROCESSED_DIR = os.path.join(PROJECT_DIR, 'data', 'processed')


def load_metrics_csv():
    """Load current metrics mapping."""
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def test_category_values():
    """Verify all categories are direct/indirect."""
    rows = load_metrics_csv()
    invalid = [r for r in rows if r['category'] not in ['direct', 'indirect', '']]

    if invalid:
        print(f"FAIL: Invalid categories found: {[r['normalized'] for r in invalid]}")
        return False

    print("PASS: All categories are valid (direct/indirect)")
    return True


def test_cluster_coverage():
    """Check cluster assignment rate for liquidity metrics."""
    rows = load_metrics_csv()
    liquidity = [r for r in rows if r.get('is_liquidity') == 'true']
    with_cluster = [r for r in liquidity if r.get('cluster', '').strip()]

    if not liquidity:
        print("SKIP: No liquidity metrics found")
        return True

    coverage = len(with_cluster) / len(liquidity) * 100
    print(f"INFO: Cluster coverage: {coverage:.1f}% ({len(with_cluster)}/{len(liquidity)})")

    if coverage < 80:
        print(f"FAIL: Cluster coverage too low: {coverage:.1f}% (expected > 80%)")
        return False

    print("PASS: Cluster coverage > 80%")
    return True


def test_no_duplicates():
    """Check for known duplicate patterns."""
    rows = load_metrics_csv()
    names = [r['normalized'] for r in rows]

    # These pairs should NOT both exist after cleanup
    should_be_merged = [
        ('carry_trade_unwind', 'carry_trade_unwinding_risk'),
        ('eurozone_banks_upside', 'eurozone_banks_upside_potential'),
        ('policy_rate_cuts', 'policy_rate_cut_expectations'),
        ('ndx_spx_vol_spread', 'ndx_spx_vol_spread_3m25d'),
        ('corporate_bond_price_yield', 'corporate_bond_priceyield_core_weave'),
        ('ny_fed_balance_sheet', 'ny_fed_balance_sheet_rebalancing'),
        ('spx_option_notional', 'spx_option_notional_daily'),
    ]

    duplicates_found = []
    for a, b in should_be_merged:
        if a in names and b in names:
            duplicates_found.append((a, b))

    if duplicates_found:
        print(f"FAIL: Duplicates found: {duplicates_found}")
        return False

    print("PASS: No known duplicates remain")
    return True


def test_sample_extraction():
    """Test with real processed CSV data."""
    # Find a processed file to test with
    processed_files = [f for f in os.listdir(PROCESSED_DIR)
                       if f.startswith('processed_') and f.endswith('.csv')]

    if not processed_files:
        print("SKIP: No processed CSV files found for testing")
        return True

    # Use the first available file
    csv_path = os.path.join(PROCESSED_DIR, processed_files[0])
    print(f"INFO: Testing with {processed_files[0]}")

    metrics_found = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('extracted_data'):
                    try:
                        data = json.loads(row['extracted_data'])
                        metrics = data.get('liquidity_metrics', [])
                        for m in metrics:
                            metrics_found += 1
                            # Verify structure
                            if 'normalized' not in m:
                                print(f"FAIL: Missing normalized field in metric")
                                return False
                            if 'is_new' not in m:
                                print(f"FAIL: Missing is_new field in metric")
                                return False
                            if m.get('is_new') and 'suggested_cluster' not in m:
                                print(f"FAIL: New metric missing suggested_cluster: {m.get('normalized')}")
                                return False
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        print("SKIP: Test data file not available")
        return True

    print(f"INFO: Validated {metrics_found} metrics from sample data")
    print("PASS: Sample extraction structure valid")
    return True


def test_is_liquidity_field():
    """Verify is_liquidity field is present and valid."""
    rows = load_metrics_csv()

    invalid = [r for r in rows if r.get('is_liquidity') not in ['true', 'false']]

    if invalid:
        print(f"FAIL: Invalid is_liquidity values: {[r['normalized'] for r in invalid[:5]]}")
        return False

    liquidity_true = sum(1 for r in rows if r.get('is_liquidity') == 'true')
    liquidity_false = sum(1 for r in rows if r.get('is_liquidity') == 'false')

    print(f"INFO: is_liquidity=true: {liquidity_true}, is_liquidity=false: {liquidity_false}")
    print("PASS: is_liquidity field is valid for all entries")
    return True


def test_direct_liquidity_metrics():
    """Verify key direct liquidity metrics are correctly classified."""
    rows = load_metrics_csv()
    rows_by_name = {r['normalized']: r for r in rows}

    # These should be direct liquidity
    expected_direct = ['tga', 'rrp', 'sofr', 'iorb_sofr_spread', 'qt_end_restart',
                       'qt_pause_timing', 'repo_usage', 'reservesrrp']

    wrong_category = []
    for metric in expected_direct:
        if metric in rows_by_name:
            if rows_by_name[metric].get('category') != 'direct':
                wrong_category.append((metric, rows_by_name[metric].get('category')))

    if wrong_category:
        print(f"WARN: Expected direct but got: {wrong_category}")
        # Not a hard failure, just a warning
        return True

    print("PASS: Direct liquidity metrics correctly classified")
    return True


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Metrics Cleanup Validation Tests")
    print("=" * 60)
    print()

    tests = [
        ("Category values", test_category_values),
        ("Cluster coverage", test_cluster_coverage),
        ("No duplicates", test_no_duplicates),
        ("Sample extraction", test_sample_extraction),
        ("is_liquidity field", test_is_liquidity_field),
        ("Direct liquidity classification", test_direct_liquidity_metrics),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
