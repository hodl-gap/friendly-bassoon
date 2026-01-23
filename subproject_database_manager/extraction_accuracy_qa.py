"""
Extraction Accuracy QA Module

Samples extractions and verifies that extracted values are CORRECT.
Tracks error rates to monitor extraction quality over time.
"""

import csv
import json
import random
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

sys.path.append(str(Path(__file__).parent.parent))
from models import call_claude_haiku
from extraction_accuracy_qa_prompts import get_accuracy_verification_prompt


# Configuration
SAMPLE_RATE = 0.10  # 10% sampling
MIN_SAMPLES = 3
MAX_SAMPLES = 30


def sample_extractions_for_accuracy_qa(
    input_csv: str,
    sample_rate: float = SAMPLE_RATE,
    categories: List[str] = None
) -> List[Dict]:
    """
    Sample extractions from processed CSV for accuracy verification.

    Args:
        input_csv: Path to processed CSV file
        sample_rate: Fraction of entries to sample (default 10%)
        categories: Categories to include (default: data_opinion, interview_meeting)

    Returns:
        List of sampled rows with extracted_data parsed
    """
    if categories is None:
        categories = ['data_opinion', 'interview_meeting']

    validatable_rows = []

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only include specified categories
            if row.get('category') not in categories:
                continue

            # Only include rows with extracted data
            if not row.get('extracted_data'):
                continue

            try:
                extracted = json.loads(row['extracted_data'])
                # Only include if has something to verify
                has_metrics = bool(extracted.get('liquidity_metrics'))
                has_chains = bool(extracted.get('logic_chains'))
                if has_metrics or has_chains:
                    row['_parsed_extracted'] = extracted
                    validatable_rows.append(row)
            except json.JSONDecodeError:
                continue

    # Calculate sample size
    sample_size = max(MIN_SAMPLES, min(MAX_SAMPLES, int(len(validatable_rows) * sample_rate)))
    sample_size = min(sample_size, len(validatable_rows))

    # Random sample
    if len(validatable_rows) <= sample_size:
        return validatable_rows
    return random.sample(validatable_rows, sample_size)


def verify_single_extraction(raw_text: str, extracted_data: dict) -> Dict:
    """
    Verify a single extraction against source text using LLM.

    Returns:
        Verification result dict with error details
    """
    prompt = get_accuracy_verification_prompt(raw_text, extracted_data)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.1, max_tokens=2000)

        # Parse JSON response
        # Find JSON in response (handle markdown code blocks)
        json_str = response
        if '```json' in response:
            json_str = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            json_str = response.split('```')[1].split('```')[0]

        result = json.loads(json_str.strip())
        return result

    except json.JSONDecodeError as e:
        return {
            "verification_results": [],
            "summary": {
                "total_fields_checked": 0,
                "correct": 0,
                "errors": 0,
                "error_rate": 0.0,
                "error_types": [],
                "parse_error": str(e)
            },
            "raw_response": response
        }
    except Exception as e:
        return {
            "verification_results": [],
            "summary": {
                "total_fields_checked": 0,
                "correct": 0,
                "errors": 0,
                "error_rate": 0.0,
                "error_types": [],
                "api_error": str(e)
            }
        }


def run_accuracy_qa(
    input_csv: str,
    output_dir: str = None,
    sample_rate: float = SAMPLE_RATE
) -> Tuple[Dict, str]:
    """
    Run accuracy QA on sampled extractions.

    Args:
        input_csv: Path to processed CSV
        output_dir: Directory for logs (default: data/qa_logs/)
        sample_rate: Sampling rate (default 10%)

    Returns:
        Tuple of (aggregate_stats, log_file_path)
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / "data" / "qa_logs"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate log filename
    input_name = Path(input_csv).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_dir / f"accuracy_qa_{input_name}_{timestamp}.json"

    print(f"\n{'='*60}")
    print(f"EXTRACTION ACCURACY QA")
    print(f"{'='*60}")
    print(f"Input: {input_csv}")
    print(f"Sample rate: {sample_rate*100:.0f}%")

    # Sample extractions
    samples = sample_extractions_for_accuracy_qa(input_csv, sample_rate)
    print(f"Sampled: {len(samples)} extractions for verification")

    if not samples:
        print("No samples to verify.")
        return {"error": "no_samples"}, str(log_file)

    # Run verification on each sample
    all_results = []
    total_fields = 0
    total_correct = 0
    total_errors = 0
    all_error_types = []

    for i, row in enumerate(samples, 1):
        print(f"\n[{i}/{len(samples)}] Verifying {row.get('opinion_id', 'unknown')}...")

        raw_text = row.get('raw_text', '')
        extracted = row.get('_parsed_extracted', {})

        result = verify_single_extraction(raw_text, extracted)

        # Record full result
        record = {
            "sample_num": i,
            "opinion_id": row.get('opinion_id'),
            "date": row.get('date'),
            "category": row.get('category'),
            "tg_channel": row.get('tg_channel'),
            "raw_text": raw_text[:500] + "..." if len(raw_text) > 500 else raw_text,
            "extracted_data": extracted,
            "verification": result
        }
        all_results.append(record)

        # Aggregate stats
        summary = result.get('summary', {})
        fields = summary.get('total_fields_checked', 0)
        correct = summary.get('correct', 0)
        errors = summary.get('errors', 0)

        total_fields += fields
        total_correct += correct
        total_errors += errors
        all_error_types.extend(summary.get('error_types', []))

        # Print sample result
        if errors > 0:
            print(f"   ❌ {errors} error(s): {summary.get('error_types', [])}")
        else:
            print(f"   ✅ All {fields} fields correct")

    # Calculate aggregate statistics
    overall_error_rate = total_errors / total_fields if total_fields > 0 else 0.0

    # Count error types
    error_type_counts = {}
    for et in all_error_types:
        error_type_counts[et] = error_type_counts.get(et, 0) + 1

    aggregate_stats = {
        "run_timestamp": timestamp,
        "input_file": str(input_csv),
        "sample_rate": sample_rate,
        "samples_verified": len(samples),
        "total_fields_checked": total_fields,
        "total_correct": total_correct,
        "total_errors": total_errors,
        "overall_error_rate": round(overall_error_rate, 4),
        "error_type_breakdown": error_type_counts,
        "threshold_recommendation": get_threshold_recommendation(overall_error_rate)
    }

    # Full log output
    full_log = {
        "aggregate_stats": aggregate_stats,
        "detailed_results": all_results
    }

    # Write JSON log
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(full_log, f, indent=2, ensure_ascii=False)

    # Write Markdown summary
    md_file = log_file.with_suffix('.md')
    _write_markdown_report(md_file, aggregate_stats, all_results)

    # Print summary
    print(f"\n{'='*60}")
    print(f"ACCURACY QA SUMMARY")
    print(f"{'='*60}")
    print(f"Samples verified: {len(samples)}")
    print(f"Total fields checked: {total_fields}")
    print(f"Correct: {total_correct}")
    print(f"Errors: {total_errors}")
    print(f"Overall error rate: {overall_error_rate*100:.1f}%")

    if error_type_counts:
        print(f"\nError breakdown:")
        for et, count in sorted(error_type_counts.items(), key=lambda x: -x[1]):
            print(f"  - {et}: {count}")

    print(f"\n{aggregate_stats['threshold_recommendation']}")
    print(f"\nFull log: {log_file}")

    return aggregate_stats, str(log_file)


def _write_markdown_report(md_file: Path, stats: Dict, results: List[Dict]):
    """Write a human-readable markdown report."""
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# Extraction Accuracy QA Report\n\n")
        f.write(f"**Generated:** {stats.get('run_timestamp', 'N/A')}\n\n")
        f.write(f"**Input:** `{stats.get('input_file', 'N/A')}`\n\n")

        # Summary
        f.write("## Summary\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Samples verified | {stats.get('samples_verified', 0)} |\n")
        f.write(f"| Total fields checked | {stats.get('total_fields_checked', 0)} |\n")
        f.write(f"| Correct | {stats.get('total_correct', 0)} |\n")
        f.write(f"| Errors | {stats.get('total_errors', 0)} |\n")
        f.write(f"| **Error rate** | **{stats.get('overall_error_rate', 0)*100:.1f}%** |\n\n")

        f.write(f"**Recommendation:** {stats.get('threshold_recommendation', 'N/A')}\n\n")

        # Error breakdown
        error_breakdown = stats.get('error_type_breakdown', {})
        if error_breakdown:
            f.write("## Error Breakdown\n\n")
            f.write("| Error Type | Count |\n")
            f.write("|------------|-------|\n")
            for et, count in sorted(error_breakdown.items(), key=lambda x: -x[1]):
                f.write(f"| {et} | {count} |\n")
            f.write("\n")

        # Detailed results
        f.write("## Detailed Results\n\n")
        for r in results:
            verdict = "✅" if r.get('verification', {}).get('summary', {}).get('errors', 0) == 0 else "❌"
            f.write(f"### {verdict} Sample {r.get('sample_num')}: {r.get('opinion_id', 'unknown')}\n\n")
            f.write(f"**Date:** {r.get('date', 'N/A')}\n\n")
            f.write(f"**Channel:** {r.get('tg_channel', 'N/A')}\n\n")
            f.write(f"**Raw text:** {r.get('raw_text', '')[:300]}...\n\n")

            verification = r.get('verification', {})
            summary = verification.get('summary', {})
            f.write(f"**Fields checked:** {summary.get('total_fields_checked', 0)} | ")
            f.write(f"**Correct:** {summary.get('correct', 0)} | ")
            f.write(f"**Errors:** {summary.get('errors', 0)}\n\n")

            # Show errors if any
            errors = [v for v in verification.get('verification_results', []) if not v.get('is_correct', True)]
            if errors:
                f.write("**Errors found:**\n\n")
                for e in errors:
                    f.write(f"- **{e.get('field')}**: extracted `{e.get('extracted_value')}` ")
                    f.write(f"but source says `{e.get('source_evidence', 'N/A')}` ")
                    f.write(f"({e.get('error_type', 'unknown')})")
                    if e.get('correction'):
                        f.write(f" → should be `{e.get('correction')}`")
                    f.write("\n")
                f.write("\n")

            f.write("---\n\n")

    print(f"Markdown report: {md_file}")


def get_threshold_recommendation(error_rate: float) -> str:
    """Get recommendation based on error rate."""
    if error_rate < 0.05:
        return "✅ EXCELLENT (<5% errors) - Current extraction quality is good."
    elif error_rate < 0.10:
        return "✅ ACCEPTABLE (5-10% errors) - Minor issues, monitor trends."
    elif error_rate < 0.20:
        return "⚠️ WARNING (10-20% errors) - Consider Option B (targeted verification)."
    else:
        return "❌ HIGH ERROR RATE (>20%) - Recommend Option A (full verification) or prompt tuning."


# Standalone execution
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run extraction accuracy QA")
    parser.add_argument("--input", "-i", required=True, help="Input processed CSV file")
    parser.add_argument("--sample-rate", "-s", type=float, default=0.10, help="Sample rate (default: 0.10)")
    parser.add_argument("--output-dir", "-o", help="Output directory for logs")

    args = parser.parse_args()

    stats, log_path = run_accuracy_qa(
        input_csv=args.input,
        sample_rate=args.sample_rate,
        output_dir=args.output_dir
    )
