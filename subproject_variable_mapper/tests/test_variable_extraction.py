"""
Test Variable Extraction Module

Tests variable extraction on sample retriever output.
"""

import sys
from pathlib import Path

# Add parent directory for imports
sys.path.append(str(Path(__file__).parent.parent))

from variable_extraction import extract_variables
from states import VariableMapperState
from config import SAMPLE_INPUT_FILE


def test_extraction_from_sample():
    """Test extraction on the sample query_result.md file."""
    print(f"Loading sample from: {SAMPLE_INPUT_FILE}")

    with open(SAMPLE_INPUT_FILE, "r", encoding="utf-8") as f:
        sample_text = f.read()

    print(f"Sample loaded: {len(sample_text)} chars")
    print("-" * 50)

    # Create test state
    test_state = VariableMapperState(synthesis=sample_text)

    # Run extraction
    result = extract_variables(test_state)

    # Print results
    variables = result.get("extracted_variables", [])
    print(f"\n{'=' * 50}")
    print(f"EXTRACTION RESULTS: {len(variables)} variables found")
    print("=" * 50)

    for i, var in enumerate(variables, 1):
        print(f"\n[{i}] {var.get('name')}")
        if var.get('threshold'):
            cond = var.get('threshold_condition', '')
            unit = var.get('threshold_unit', '')
            print(f"    Threshold: {cond} {var.get('threshold')} {unit}")
        print(f"    Context: {var.get('context', 'N/A')[:80]}...")

    # Summary
    print(f"\n{'=' * 50}")
    print("SUMMARY")
    print("=" * 50)
    print(f"Total variables extracted: {len(variables)}")

    # Group by whether they have thresholds
    with_threshold = [v for v in variables if v.get('threshold')]
    print(f"Variables with thresholds: {len(with_threshold)}")
    print(f"Variables without thresholds: {len(variables) - len(with_threshold)}")

    return variables


if __name__ == "__main__":
    test_extraction_from_sample()
