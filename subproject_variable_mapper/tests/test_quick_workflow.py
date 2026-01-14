"""
Quick Workflow Test - Small Sample

Uses minimal sample to verify all 4 steps work without many LLM calls.
"""

import sys
import json
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from variable_mapper_orchestrator import run_variable_mapper


# Minimal sample input
QUICK_SAMPLE = """
**CHAIN:** Fed rate cuts → short rates down → curve steepening
**MECHANISM:** easing lowers short-term rates

**CHAIN:** TGA drawdown → liquidity surge → risk-on rally
**MECHANISM:** Treasury spending releases reserves

## Key Variables to Monitor
- TGA balance (threshold: <$500B)
- VIX levels (elevated = risk-off)
- Fed funds rate trajectory
"""


def test_quick_workflow():
    """Run workflow with minimal sample."""
    print("=" * 60)
    print("QUICK WORKFLOW TEST (Small Sample)")
    print("=" * 60)

    print(f"\nSample size: {len(QUICK_SAMPLE)} chars")
    print("-" * 60)

    # Run the pipeline
    result = run_variable_mapper(QUICK_SAMPLE)

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(f"\nStep 1 - Extracted: {len(result.get('extracted_variables', []))}")
    for v in result.get('extracted_variables', []):
        print(f"  - {v.get('name')}")

    print(f"\nStep 2 - Normalized: {len(result.get('normalized_variables', []))}")
    for v in result.get('normalized_variables', []):
        print(f"  - {v.get('raw_name')} -> {v.get('normalized_name')} ({v.get('match_type')})")

    print(f"\nStep 3 - Missing: {result.get('missing_variables', [])}")
    print(f"Step 3 - Chains parsed: {len(result.get('chain_dependencies', []))}")

    print(f"\nStep 4 - Unmapped: {result.get('unmapped_variables', [])}")

    # Final output
    print("\n" + "-" * 60)
    print("FINAL OUTPUT:")
    print("-" * 60)
    print(json.dumps(result.get('final_output', {}), indent=2, default=str))

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_quick_workflow()
