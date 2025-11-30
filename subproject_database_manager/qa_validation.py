"""
QA Validation Module

Validates structured extractions for:
1. Retrievability - Multiple semantic entry points
2. Completeness - If-then logic, thresholds, conditions
3. Answerability - Specific, quantitative information

This module processes structured outputs and provides detailed quality feedback
without automatically fixing issues (user manages changes manually).
"""

import sys
import csv
import json
import os
from pathlib import Path

# Add parent directory to path for models import
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from models import call_gpt41
from qa_validation_prompts import get_qa_validation_prompt


def validate_extraction(extracted_data, raw_text, category, message_date=None, image_data=None, log_file=None):
    """
    Validate a single extraction against QA criteria

    Args:
        extracted_data: JSON string or dict of extracted structured data
        raw_text: Original message text
        category: Message category (data_opinion/interview_meeting)
        message_date: Message timestamp (optional)
        image_data: Optional image structured data (not used yet)
        log_file: Optional file handle to write detailed logs

    Returns:
        dict: QA validation result with verdict, scores, and feedback
    """

    # Skip if no extracted data
    if not extracted_data or extracted_data == '':
        return {
            'qa_verdict': 'SKIP',
            'qa_confidence': 0.0,
            'qa_retrievability_score': 0.0,
            'qa_completeness_score': 0.0,
            'qa_answerability_score': 0.0,
            'qa_chain_of_thought': 'No extracted data to validate',
            'qa_missing_pieces': '',
            'qa_broken_paths': '',
            'qa_suggested_fixes': ''
        }

    # Convert to dict if JSON string
    if isinstance(extracted_data, str):
        try:
            extracted_dict = json.loads(extracted_data)
        except json.JSONDecodeError:
            return {
                'qa_verdict': 'ERROR',
                'qa_confidence': 0.0,
                'qa_retrievability_score': 0.0,
                'qa_completeness_score': 0.0,
                'qa_answerability_score': 0.0,
                'qa_chain_of_thought': 'Failed to parse extracted data JSON',
                'qa_missing_pieces': '',
                'qa_broken_paths': '',
                'qa_suggested_fixes': ''
            }
    else:
        extracted_dict = extracted_data

    # Get QA validation prompt
    prompt = get_qa_validation_prompt(extracted_dict, raw_text, category)
    messages = [{"role": "user", "content": prompt}]

    # Call GPT-4.1 for validation
    response = call_gpt41(messages, temperature=0.3, max_tokens=2000)

    # Print raw LLM response (as per project guidelines)
    print(f"\n=== RAW QA VALIDATION RESPONSE ===")
    print(response)
    print(f"=== END ===\n")

    # Log to file if provided
    if log_file:
        log_file.write("="*80 + "\n")
        log_file.write("QA VALIDATION ENTRY\n")
        log_file.write("="*80 + "\n\n")
        log_file.write("CATEGORY: " + category + "\n")
        if message_date:
            log_file.write("DATE: " + str(message_date) + "\n")
        log_file.write("\n" + "-"*80 + "\n")
        log_file.write("RAW TEXT:\n")
        log_file.write("-"*80 + "\n")
        log_file.write(raw_text + "\n\n")
        log_file.write("-"*80 + "\n")
        log_file.write("EXTRACTED DATA:\n")
        log_file.write("-"*80 + "\n")
        log_file.write(json.dumps(extracted_dict, indent=2, ensure_ascii=False) + "\n\n")
        log_file.write("-"*80 + "\n")
        log_file.write("RAW QA RESPONSE:\n")
        log_file.write("-"*80 + "\n")
        log_file.write(response + "\n\n")
        log_file.write("\n\n")

    # Parse response
    try:
        response_text = response.strip()
        if response_text.startswith("```"):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        qa_result = json.loads(response_text)

        # Extract scores
        dim_scores = qa_result.get('dimension_scores', {})
        retrievability = dim_scores.get('retrievability', {})
        completeness = dim_scores.get('completeness', {})
        answerability = dim_scores.get('answerability', {})

        # Flatten to CSV-friendly format
        return {
            'qa_verdict': qa_result.get('overall_verdict', 'UNKNOWN'),
            'qa_confidence': qa_result.get('confidence_score', 0.0),
            'qa_retrievability_score': retrievability.get('score', 0.0),
            'qa_completeness_score': completeness.get('score', 0.0),
            'qa_answerability_score': answerability.get('score', 0.0),
            'qa_chain_of_thought': qa_result.get('chain_of_thought', ''),
            'qa_missing_pieces': json.dumps(completeness.get('missing_pieces', []), ensure_ascii=False),
            'qa_broken_paths': json.dumps(retrievability.get('broken_paths', []), ensure_ascii=False),
            'qa_suggested_fixes': json.dumps(qa_result.get('suggested_fixes', []), ensure_ascii=False)
        }

    except json.JSONDecodeError as e:
        print(f"Error parsing QA response: {e}")
        return {
            'qa_verdict': 'ERROR',
            'qa_confidence': 0.0,
            'qa_retrievability_score': 0.0,
            'qa_completeness_score': 0.0,
            'qa_answerability_score': 0.0,
            'qa_chain_of_thought': f'Failed to parse QA response: {str(e)}',
            'qa_missing_pieces': '',
            'qa_broken_paths': '',
            'qa_suggested_fixes': ''
        }


def add_qa_to_csv(input_csv, output_csv, validate_categories=['data_opinion'], log_file_path=None):
    """
    Read processed CSV, validate extractions, add QA columns

    Args:
        input_csv: Path to processed CSV
        output_csv: Path to output CSV with QA columns
        validate_categories: List of categories to validate (default: ['data_opinion'])
        log_file_path: Optional path to save detailed QA logs (default: auto-generate)
    """

    # Auto-generate log file path if not provided
    if log_file_path is None:
        log_file_path = output_csv.replace('.csv', '_detailed_log.txt')

    print(f"="*80)
    print("QA VALIDATION - ADDING QUALITY CHECKS")
    print(f"="*80)
    print(f"Input: {input_csv}")
    print(f"Output: {output_csv}")
    print(f"Log file: {log_file_path}")
    print(f"Validating categories: {validate_categories}")
    print(f"="*80)

    # Read input CSV
    rows = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    print(f"\nLoaded {len(rows)} entries")

    # Add QA columns to fieldnames
    qa_fieldnames = list(fieldnames) + [
        'qa_verdict',
        'qa_confidence',
        'qa_retrievability_score',
        'qa_completeness_score',
        'qa_answerability_score',
        'qa_chain_of_thought',
        'qa_missing_pieces',
        'qa_broken_paths',
        'qa_suggested_fixes'
    ]

    # Process each row
    validated_count = 0
    skipped_count = 0

    # Open log file
    with open(log_file_path, 'w', encoding='utf-8') as log_file:
        log_file.write("QA VALIDATION DETAILED LOG\n")
        log_file.write("="*80 + "\n")
        log_file.write(f"Input CSV: {input_csv}\n")
        log_file.write(f"Output CSV: {output_csv}\n")
        log_file.write(f"Validated categories: {validate_categories}\n")
        log_file.write("="*80 + "\n\n\n")

        for i, row in enumerate(rows, 1):
            category = row.get('category', '')
            entry_type = row.get('entry_type', '')

            # Only validate specified categories and text entries (not image entries)
            if category in validate_categories and entry_type == 'text':
                print(f"\n[{i}/{len(rows)}] Validating {category} entry...")

                qa_result = validate_extraction(
                    extracted_data=row.get('extracted_data', ''),
                    raw_text=row.get('raw_text', ''),
                    category=category,
                    message_date=row.get('date', ''),
                    log_file=log_file
                )

                # Add QA results to row
                row.update(qa_result)
                validated_count += 1

                # Print summary
                print(f"  Verdict: {qa_result['qa_verdict']} (confidence: {qa_result['qa_confidence']:.2f})")
                print(f"  Scores: R={qa_result['qa_retrievability_score']:.2f}, "
                      f"C={qa_result['qa_completeness_score']:.2f}, "
                      f"A={qa_result['qa_answerability_score']:.2f}")
            else:
                # Skip validation, add empty QA fields
                row.update({
                    'qa_verdict': 'SKIP',
                    'qa_confidence': 0.0,
                    'qa_retrievability_score': 0.0,
                    'qa_completeness_score': 0.0,
                    'qa_answerability_score': 0.0,
                    'qa_chain_of_thought': f'Skipped (category: {category}, type: {entry_type})',
                    'qa_missing_pieces': '',
                    'qa_broken_paths': '',
                    'qa_suggested_fixes': ''
                })
                skipped_count += 1

    # Write output CSV
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=qa_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*80}")
    print("QA VALIDATION COMPLETE")
    print(f"{'='*80}")
    print(f"Total entries: {len(rows)}")
    print(f"Validated: {validated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"\nOutput saved to: {output_csv}")
    print(f"Detailed log saved to: {log_file_path}")

    # Summary statistics
    pass_count = sum(1 for r in rows if r.get('qa_verdict') == 'PASS')
    fail_count = sum(1 for r in rows if r.get('qa_verdict') == 'FAIL')

    if validated_count > 0:
        print(f"\nQA Results:")
        print(f"  PASS: {pass_count} ({pass_count/validated_count*100:.1f}%)")
        print(f"  FAIL: {fail_count} ({fail_count/validated_count*100:.1f}%)")

        # Average scores
        avg_retrievability = sum(float(r.get('qa_retrievability_score', 0))
                                 for r in rows if r.get('qa_verdict') in ['PASS', 'FAIL']) / validated_count
        avg_completeness = sum(float(r.get('qa_completeness_score', 0))
                              for r in rows if r.get('qa_verdict') in ['PASS', 'FAIL']) / validated_count
        avg_answerability = sum(float(r.get('qa_answerability_score', 0))
                               for r in rows if r.get('qa_verdict') in ['PASS', 'FAIL']) / validated_count

        print(f"\nAverage Dimension Scores:")
        print(f"  Retrievability: {avg_retrievability:.2f}")
        print(f"  Completeness: {avg_completeness:.2f}")
        print(f"  Answerability: {avg_answerability:.2f}")


def sample_qa_validation(input_csv, validate_categories=['data_opinion', 'interview_meeting'],
                         sample_min=3, sample_max=20, sample_pct=0.05):
    """
    Sample-based QA validation for integration into orchestrator.
    Validates a sample of extractions and logs results to separate folder.

    Args:
        input_csv: Path to processed CSV
        validate_categories: List of categories to validate
        sample_min: Minimum number of samples (default: 3)
        sample_max: Maximum number of samples (default: 20)
        sample_pct: Percentage of entries to sample (default: 5%)

    Returns:
        dict: Summary of QA results with verdicts and scores
    """
    import random
    from datetime import datetime

    # Create QA logs folder
    qa_log_dir = Path("data/qa_logs")
    qa_log_dir.mkdir(parents=True, exist_ok=True)

    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_name = Path(input_csv).stem
    log_file_path = qa_log_dir / f"qa_sample_{input_name}_{timestamp}.txt"

    print(f"\n{'='*60}")
    print("QA SAMPLING VALIDATION")
    print(f"{'='*60}")

    # Read input CSV
    rows = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Filter to validatable entries (specified categories + text entries)
    validatable = [r for r in rows if r.get('category') in validate_categories
                   and r.get('entry_type') == 'text'
                   and r.get('extracted_data')]

    if not validatable:
        print("  No validatable entries found. Skipping QA.")
        return {'status': 'skipped', 'reason': 'no_validatable_entries'}

    # Calculate sample size: 5% of entries, min 3, max 20
    sample_size = max(sample_min, min(sample_max, int(len(validatable) * sample_pct)))
    sample_size = min(sample_size, len(validatable))  # Can't sample more than available

    # Random sample
    sampled = random.sample(validatable, sample_size)

    print(f"  Total entries: {len(rows)}")
    print(f"  Validatable: {len(validatable)}")
    print(f"  Sampling: {sample_size} ({sample_size/len(validatable)*100:.1f}%)")
    print(f"  Log: {log_file_path}")
    print(f"{'='*60}")

    # Validate sampled entries
    results = []

    with open(log_file_path, 'w', encoding='utf-8') as log_file:
        log_file.write("QA SAMPLING VALIDATION LOG\n")
        log_file.write("="*80 + "\n")
        log_file.write(f"Input CSV: {input_csv}\n")
        log_file.write(f"Timestamp: {datetime.now().isoformat()}\n")
        log_file.write(f"Total entries: {len(rows)}\n")
        log_file.write(f"Validatable entries: {len(validatable)}\n")
        log_file.write(f"Sample size: {sample_size}\n")
        log_file.write(f"Categories: {validate_categories}\n")
        log_file.write("="*80 + "\n\n")

        for i, row in enumerate(sampled, 1):
            print(f"\n  [{i}/{sample_size}] Validating sample...")

            qa_result = validate_extraction(
                extracted_data=row.get('extracted_data', ''),
                raw_text=row.get('raw_text', ''),
                category=row.get('category', ''),
                message_date=row.get('date', ''),
                log_file=log_file
            )

            results.append(qa_result)

            print(f"    Verdict: {qa_result['qa_verdict']} (conf: {qa_result['qa_confidence']:.2f})")
            print(f"    R={qa_result['qa_retrievability_score']:.2f}, "
                  f"C={qa_result['qa_completeness_score']:.2f}, "
                  f"A={qa_result['qa_answerability_score']:.2f}")

        # Write summary to log
        log_file.write("\n\n" + "="*80 + "\n")
        log_file.write("SUMMARY\n")
        log_file.write("="*80 + "\n")

        pass_count = sum(1 for r in results if r['qa_verdict'] == 'PASS')
        fail_count = sum(1 for r in results if r['qa_verdict'] == 'FAIL')

        log_file.write(f"PASS: {pass_count}/{sample_size}\n")
        log_file.write(f"FAIL: {fail_count}/{sample_size}\n")

        if results:
            avg_r = sum(r['qa_retrievability_score'] for r in results) / len(results)
            avg_c = sum(r['qa_completeness_score'] for r in results) / len(results)
            avg_a = sum(r['qa_answerability_score'] for r in results) / len(results)
            avg_conf = sum(r['qa_confidence'] for r in results) / len(results)

            log_file.write(f"\nAverage Scores:\n")
            log_file.write(f"  Retrievability: {avg_r:.2f}\n")
            log_file.write(f"  Completeness: {avg_c:.2f}\n")
            log_file.write(f"  Answerability: {avg_a:.2f}\n")
            log_file.write(f"  Confidence: {avg_conf:.2f}\n")

    # Build summary
    summary = {
        'status': 'completed',
        'total_entries': len(rows),
        'validatable_entries': len(validatable),
        'sample_size': sample_size,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'pass_rate': pass_count / sample_size if sample_size > 0 else 0,
        'avg_retrievability': avg_r if results else 0,
        'avg_completeness': avg_c if results else 0,
        'avg_answerability': avg_a if results else 0,
        'avg_confidence': avg_conf if results else 0,
        'log_file': str(log_file_path)
    }

    # Print summary
    print(f"\n{'='*60}")
    print("QA SAMPLING COMPLETE")
    print(f"{'='*60}")
    print(f"  PASS: {pass_count}/{sample_size} ({summary['pass_rate']*100:.1f}%)")
    print(f"  Avg Scores: R={summary['avg_retrievability']:.2f}, "
          f"C={summary['avg_completeness']:.2f}, A={summary['avg_answerability']:.2f}")
    print(f"  Log: {log_file_path}")

    return summary


if __name__ == "__main__":
    # Test on existing processed file
    add_qa_to_csv(
        input_csv='data/processed/processed_루팡_2025-11-23.csv',
        output_csv='data/processed/qa_validated_루팡_2025-11-23.csv',
        validate_categories=['data_opinion']
    )
