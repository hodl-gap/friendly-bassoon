"""
Test QA Validation

Test the QA validation system on sample data to verify it works correctly.
"""

import sys
sys.path.append('..')
from qa_validation import validate_extraction
import json


def test_data_opinion_extraction():
    """Test QA validation on a data_opinion extraction"""

    # Sample extracted data (realistic example)
    extracted_data = {
        "source": "Goldman Sachs Research",
        "data_source": "Federal Reserve Board",
        "asset_class": "Fixed Income",
        "used_data": "Fed balance sheet declined $95B in November, TGA balance increased to $750B",
        "what_happened": "Federal Reserve reduced its balance sheet by $95 billion in November, while Treasury General Account balance rose to $750 billion, the highest level since May 2023.",
        "interpretation": "Combined effect of QT and TGA drawdown represents significant liquidity drain from financial system. This tightening of monetary conditions could pressure credit markets and increase funding stress in money markets.",
        "tags": "direct_liquidity"
    }

    raw_text = """Fed Balance Sheet Update - November 2023

The Federal Reserve's balance sheet declined by $95 billion in November, continuing its quantitative tightening program. Meanwhile, the Treasury General Account (TGA) balance at the Fed increased to $750 billion, the highest level since May 2023.

Goldman Sachs notes that this combination represents a significant liquidity drain from the financial system. The dual effect of QT and TGA drawdown could pressure credit markets and increase funding stress in money markets, particularly as year-end approaches.

Key implications:
- Direct liquidity impact on system
- Potential pressure on repo rates
- Credit market stress indicators rising"""

    print("="*80)
    print("TEST: QA Validation on Data Opinion Extraction")
    print("="*80)

    result = validate_extraction(
        extracted_data=extracted_data,
        raw_text=raw_text,
        category='data_opinion'
    )

    print(f"\n{'='*80}")
    print("QA RESULT")
    print(f"{'='*80}")
    print(f"Verdict: {result['qa_verdict']}")
    print(f"Confidence: {result['qa_confidence']}")
    print(f"\nDimension Scores:")
    print(f"  Retrievability: {result['qa_retrievability_score']}")
    print(f"  Completeness: {result['qa_completeness_score']}")
    print(f"  Answerability: {result['qa_answerability_score']}")
    print(f"\nChain of Thought:")
    print(result['qa_chain_of_thought'])
    print(f"\nMissing Pieces:")
    print(result['qa_missing_pieces'])
    print(f"\nBroken Paths:")
    print(result['qa_broken_paths'])
    print(f"\nSuggested Fixes:")
    print(result['qa_suggested_fixes'])


def test_poor_extraction():
    """Test QA validation on a poor quality extraction (should FAIL)"""

    # Poor extraction - vague, no thresholds, minimal context
    extracted_data = {
        "source": "Some Research",
        "data_source": "Market data",
        "asset_class": "",
        "used_data": "Some numbers went up",
        "what_happened": "Things changed",
        "interpretation": "It's bad for markets",
        "tags": "irrelevant"
    }

    raw_text = """Market Analysis

According to recent data, we're seeing some concerning trends in the macro environment. Various indicators are showing deterioration, which could be negative for risk assets going forward. Investors should remain cautious."""

    print("\n\n" + "="*80)
    print("TEST: QA Validation on Poor Quality Extraction (should FAIL)")
    print("="*80)

    result = validate_extraction(
        extracted_data=extracted_data,
        raw_text=raw_text,
        category='data_opinion'
    )

    print(f"\n{'='*80}")
    print("QA RESULT")
    print(f"{'='*80}")
    print(f"Verdict: {result['qa_verdict']}")
    print(f"Confidence: {result['qa_confidence']}")
    print(f"\nDimension Scores:")
    print(f"  Retrievability: {result['qa_retrievability_score']}")
    print(f"  Completeness: {result['qa_completeness_score']}")
    print(f"  Answerability: {result['qa_answerability_score']}")
    print(f"\nSuggested Fixes:")
    print(result['qa_suggested_fixes'])


if __name__ == "__main__":
    print("Running QA Validation Tests...\n")

    # Test 1: Good extraction
    test_data_opinion_extraction()

    # Test 2: Poor extraction (should fail)
    test_poor_extraction()

    print("\n" + "="*80)
    print("TESTS COMPLETE")
    print("="*80)
