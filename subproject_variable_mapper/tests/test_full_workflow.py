"""
Full Workflow Test for Variable Mapper

Runs the complete 4-step pipeline end-to-end using sample data.
"""

import sys
import json
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from variable_mapper_orchestrator import run_variable_mapper
from config import SAMPLE_INPUT_FILE


def test_full_workflow():
    """Run full 4-step workflow with sample input."""
    print("=" * 60)
    print("VARIABLE MAPPER - FULL WORKFLOW TEST")
    print("=" * 60)

    # Load sample input
    if not SAMPLE_INPUT_FILE.exists():
        print(f"ERROR: Sample input not found at {SAMPLE_INPUT_FILE}")
        return

    with open(SAMPLE_INPUT_FILE, "r", encoding="utf-8") as f:
        sample_text = f.read()

    print(f"\nInput file: {SAMPLE_INPUT_FILE}")
    print(f"Input size: {len(sample_text)} chars")
    print("-" * 60)

    # Run the full pipeline
    result = run_variable_mapper(sample_text)

    # Print summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    extracted = result.get('extracted_variables', [])
    normalized = result.get('normalized_variables', [])
    missing = result.get('missing_variables', [])
    unmapped = result.get('unmapped_variables', [])
    dependencies = result.get('chain_dependencies', [])

    print(f"\nStep 1 - Extracted Variables: {len(extracted)}")
    print(f"Step 2 - Normalized Variables: {len(normalized)}")
    print(f"Step 3 - Missing Variables: {len(missing)}")
    print(f"Step 3 - Chain Dependencies: {len(dependencies)}")
    print(f"Step 4 - Unmapped Variables: {len(unmapped)}")

    # Show sample of each step's output
    print("\n" + "-" * 60)
    print("SAMPLE OUTPUTS (first 3 of each)")
    print("-" * 60)

    print("\nExtracted Variables:")
    for var in extracted[:3]:
        print(f"  - {var.get('name')}: {var.get('context', '')[:50]}...")

    print("\nNormalized Variables:")
    for var in normalized[:3]:
        raw = var.get('raw_name', '')
        norm = var.get('normalized_name', 'UNKNOWN')
        match_type = var.get('match_type', '')
        print(f"  - {raw} -> {norm} ({match_type})")

    print("\nMissing Variables (from chain analysis):")
    for var in missing[:5]:
        print(f"  - {var}")

    print("\nUnmapped Variables (no Data ID):")
    for var in unmapped[:5]:
        print(f"  - {var}")

    # Write final output to file
    output_file = Path(__file__).parent / "workflow_output.json"
    final_output = result.get('final_output', {})
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2, default=str)
    print(f"\nFinal output saved to: {output_file}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_full_workflow()
