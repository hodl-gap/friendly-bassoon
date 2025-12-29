"""
Message Pipeline Module

Handles the complete processing pipeline for a single Telegram channel export.
Extracts path logic and file handling from orchestrator.

Used by telegram_workflow_orchestrator.py for Step 2 processing.
"""

from pathlib import Path
from extract_telegram_data import extract_telegram_messages
from process_messages_v3 import process_all_messages_v3
from qa_validation import sample_qa_validation


def process_single_channel(
    export_folder: str,
    max_messages: int = None,
    output_dir: str = "data/processed",
    batch_size: int = 3
) -> str:
    """
    Process a single channel's export folder through the full pipeline.

    Args:
        export_folder: Path to ChatExport_* folder containing result.json
        max_messages: Limit messages to process (None = all)
        output_dir: Directory for processed output
        batch_size: Batch size for V3 processor

    Returns:
        Path to output CSV file, or None if processing failed
    """
    export_path = Path(export_folder)
    json_file = export_path / "result.json"

    if not json_file.exists():
        print(f"⚠️  Skipping {export_folder}: result.json not found")
        return None

    # Extract channel name from folder
    channel_name = _extract_channel_name(export_path.name)

    print(f"📄 JSON: {json_file}")

    # Step 1: JSON → CSV
    intermediate_csv = _convert_json_to_csv(json_file, export_path.parent, channel_name, max_messages)

    # Step 2: Process with V3
    output_csv = _run_v3_processor(intermediate_csv, channel_name, export_path, output_dir, batch_size)

    # Step 3: QA Validation
    _run_qa_validation(output_csv)

    return str(output_csv)


def _extract_channel_name(folder_name: str) -> str:
    """Extract clean channel name from ChatExport folder name."""
    return folder_name.replace("ChatExport_", "").replace(" ", "_")


def _convert_json_to_csv(json_file, raw_dir, channel_name, max_messages):
    """Convert JSON export to intermediate CSV."""
    print(f"🔄 Converting JSON to CSV...")
    df = extract_telegram_messages(str(json_file))

    if max_messages:
        df = df.head(max_messages)
        print(f"   Limiting to {max_messages} messages")

    intermediate_csv = raw_dir / f"{channel_name}_messages.csv"
    df.to_csv(intermediate_csv, index=False)
    print(f"   ✅ CSV created: {intermediate_csv}")
    return intermediate_csv


def _run_v3_processor(intermediate_csv, channel_name, export_path, output_dir, batch_size):
    """Run V3 processor on intermediate CSV."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_csv = output_path / f"processed_{channel_name}.csv"

    print(f"🔄 Processing with V3 processor...")
    print(f"   Input: {intermediate_csv}")
    print(f"   Output: {output_csv}")

    process_all_messages_v3(
        input_csv=str(intermediate_csv),
        output_csv=str(output_csv),
        base_photo_path=str(export_path) + '/',
        batch_size=batch_size
    )
    return output_csv


def _run_qa_validation(output_csv):
    """Run QA sampling validation on processed output."""
    print(f"\n🔍 Running QA sampling validation...")
    sample_qa_validation(
        input_csv=str(output_csv),
        validate_categories=['data_opinion', 'interview_meeting'],
        sample_min=3,
        sample_max=20,
        sample_pct=0.05
    )
