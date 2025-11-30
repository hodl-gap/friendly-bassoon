"""
QA Post-Processor

Standalone script to add QA validation to processed Telegram message CSVs.
Runs as a separate step after process_messages_v3.py completes.

Usage:
    python qa_post_processor.py --input data/processed/processed_루팡_2025-11-23.csv --output data/processed/qa_validated_루팡_2025-11-23.csv

    python qa_post_processor.py --input data/processed/processed_루팡_2025-11-23.csv  # auto-generates output filename

    python qa_post_processor.py --input data/processed/processed_루팡_2025-11-23.csv --categories data_opinion,interview_meeting
"""

import argparse
from pathlib import Path
from qa_validation import add_qa_to_csv


def main():
    parser = argparse.ArgumentParser(
        description='Add QA validation to processed Telegram message CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Specify output file
  python qa_post_processor.py \\
    --input data/processed/processed_루팡_2025-11-23.csv \\
    --output data/processed/qa_validated_루팡_2025-11-23.csv

  # Auto-generate output filename
  python qa_post_processor.py \\
    --input data/processed/processed_루팡_2025-11-23.csv

  # Validate specific categories
  python qa_post_processor.py \\
    --input data/processed/processed_루팡_2025-11-23.csv \\
    --categories data_opinion,interview_meeting
        """
    )

    parser.add_argument(
        '--input',
        required=True,
        help='Path to processed CSV file'
    )

    parser.add_argument(
        '--output',
        help='Path to output QA-validated CSV (default: auto-generate from input filename)'
    )

    parser.add_argument(
        '--categories',
        default='data_opinion',
        help='Comma-separated list of categories to validate (default: data_opinion)'
    )

    args = parser.parse_args()

    # Auto-generate output filename if not provided
    if not args.output:
        input_path = Path(args.input)
        output_filename = f"qa_validated_{input_path.name}"
        args.output = str(input_path.parent / output_filename)

    # Parse categories
    validate_categories = [c.strip() for c in args.categories.split(',')]

    # Run QA validation
    add_qa_to_csv(
        input_csv=args.input,
        output_csv=args.output,
        validate_categories=validate_categories
    )

    print(f"\n✓ QA validation complete!")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
