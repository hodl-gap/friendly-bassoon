"""
Telegram Workflow Orchestrator

Main orchestrator for the Telegram message processing workflow:
1. Fetch messages from Telegram channels (via telegram_fetcher.py)
2. Process messages with V3 processor (via process_messages_v3.py)

All data is stored in data/ folder.

Usage:
    python telegram_workflow_orchestrator.py \
        --channels "Channel1,Channel2" \
        --start-date 2025-11-20 \
        --end-date 2025-11-23 \
        --process  # Optional: auto-process after fetching
"""

import os
import sys
import asyncio
import argparse
import time
from datetime import datetime
from pathlib import Path

# Import telegram fetcher functions
from telegram_fetcher import fetch_and_export, list_channels_only

# Import V3 processor
from process_messages_v3 import process_all_messages_v3

# Import JSON to CSV extractor
from extract_telegram_data import extract_telegram_messages

# Import QA validation
from qa_validation import sample_qa_validation


def parse_date(date_str):
    """Parse date string in YYYY-MM-DD format"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


async def fetch_telegram_messages(channel_names, start_date, end_date):
    """
    Fetch messages from Telegram channels

    Args:
        channel_names: List of channel names/IDs
        start_date: datetime object
        end_date: datetime object

    Returns:
        list: List of export folder paths created (only from this run)
    """
    print("\n" + "="*60)
    print("STEP 1: Fetching Telegram Messages")
    print("="*60)

    step_start = time.time()

    # Fetch and export to data/raw/ folder
    output_dir = "data/raw"
    created_folders = await fetch_and_export(channel_names, start_date, end_date, output_dir)

    step_elapsed = time.time() - step_start
    print(f"\n⏱️  Step 1 completed in {step_elapsed:.1f}s")

    # Return the folders created by this run (returned from fetch_and_export)
    # This fixes the bug where ALL ChatExport_ folders were being processed
    return created_folders if created_folders else []


def process_telegram_messages(export_folders, max_messages=None):
    """
    Process fetched Telegram messages using V3 processor

    Args:
        export_folders: List of export folder paths
        max_messages: Maximum number of messages to process (None = all)

    Returns:
        list: List of output CSV paths
    """
    print("\n" + "="*60)
    print("STEP 2: Processing Messages with V3 Processor")
    print("="*60)

    output_files = []

    for export_folder in export_folders:
        export_path = Path(export_folder)
        json_file = export_path / "result.json"

        if not json_file.exists():
            print(f"⚠️  Skipping {export_folder}: result.json not found")
            continue

        # Create intermediate CSV path in data/raw/
        channel_name = export_path.name.replace("ChatExport_", "").replace(" ", "_")
        intermediate_csv = export_path.parent / f"{channel_name}_messages.csv"

        print(f"\n📂 Processing: {export_folder}")
        print(f"📄 JSON: {json_file}")

        # Step 2a: Convert JSON to CSV
        print(f"🔄 Converting JSON to CSV...")
        df = extract_telegram_messages(str(json_file))

        # Limit messages if specified
        if max_messages:
            df = df.head(max_messages)
            print(f"   Limiting to {max_messages} messages")

        df.to_csv(intermediate_csv, index=False)
        print(f"   ✅ CSV created: {intermediate_csv}")

        # Step 2b: Process with V3 processor
        output_dir = Path("data/processed")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_csv = output_dir / f"processed_{channel_name}.csv"

        print(f"🔄 Processing with V3 processor...")
        print(f"   Input: {intermediate_csv}")
        print(f"   Output: {output_csv}")

        # Process messages (base_photo_path will auto-detect from CSV location)
        # Using batch_size=3 to handle long messages better with the extended schema
        process_all_messages_v3(
            input_csv=str(intermediate_csv),
            output_csv=str(output_csv),
            base_photo_path=str(export_path) + '/',
            batch_size=3
        )

        output_files.append(str(output_csv))

        # Step 2c: QA Sampling Validation
        print(f"\n🔍 Running QA sampling validation...")
        qa_summary = sample_qa_validation(
            input_csv=str(output_csv),
            validate_categories=['data_opinion', 'interview_meeting'],
            sample_min=3,
            sample_max=20,
            sample_pct=0.05
        )

    return output_files


async def run_workflow(channel_names, start_date, end_date, auto_process=True, max_messages=None):
    """
    Run the complete workflow: fetch + process

    Args:
        channel_names: List of channel names/IDs
        start_date: datetime object
        end_date: datetime object
        auto_process: Whether to automatically process after fetching
        max_messages: Maximum number of messages to process (None = all)
    """
    print("\n" + "="*80)
    print("TELEGRAM WORKFLOW ORCHESTRATOR")
    print("="*80)
    print(f"Channels: {', '.join(channel_names)}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Auto-process: {auto_process}")
    print("="*80)

    # Step 1: Fetch messages
    export_folders = await fetch_telegram_messages(channel_names, start_date, end_date)

    if not export_folders:
        print("\n⚠️  No messages fetched. Workflow complete.")
        return

    print(f"\n✅ Fetched messages to {len(export_folders)} folder(s)")

    # Step 2: Process messages (if auto_process enabled)
    if auto_process:
        output_files = process_telegram_messages(export_folders, max_messages)

        print("\n" + "="*80)
        print("WORKFLOW COMPLETE")
        print("="*80)
        print(f"✅ Processed {len(output_files)} channel(s)")
        print(f"\nOutput files:")
        for output_file in output_files:
            print(f"  📄 {output_file}")
    else:
        print("\n✅ Messages fetched. Run with --process to process them.")


def main():
    parser = argparse.ArgumentParser(
        description='Orchestrator for Telegram message fetching and processing workflow',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available channels
  python telegram_workflow_orchestrator.py --list-channels

  # Fetch and process messages (default)
  python telegram_workflow_orchestrator.py \
    --channels "루팡" \
    --start-date 2025-11-21 \
    --end-date 2025-11-23

  # Fetch only (no processing)
  python telegram_workflow_orchestrator.py \
    --channels "Channel1,Channel2" \
    --start-date 2025-11-20 \
    --end-date 2025-11-23 \
    --no-process

  # Process with message limit
  python telegram_workflow_orchestrator.py \
    --channels "루팡" \
    --start-date 2025-11-21 \
    --end-date 2025-11-23 \
    --max-messages 10
        """
    )

    parser.add_argument(
        '--list-channels',
        action='store_true',
        help='List all available channels and exit'
    )

    parser.add_argument(
        '--channels',
        type=str,
        help='Comma-separated list of channel names or IDs'
    )

    parser.add_argument(
        '--start-date',
        type=parse_date,
        help='Start date in YYYY-MM-DD format'
    )

    parser.add_argument(
        '--end-date',
        type=parse_date,
        help='End date in YYYY-MM-DD format'
    )

    parser.add_argument(
        '--process',
        dest='auto_process',
        action='store_true',
        default=True,
        help='Automatically process messages after fetching (default: True)'
    )

    parser.add_argument(
        '--no-process',
        dest='auto_process',
        action='store_false',
        help='Only fetch messages, do not process'
    )

    parser.add_argument(
        '--max-messages',
        type=int,
        default=None,
        help='Maximum number of messages to process (default: all)'
    )

    args = parser.parse_args()

    # Handle list-channels mode
    if args.list_channels:
        asyncio.run(list_channels_only())
        return

    # Validate required arguments
    if not args.channels or not args.start_date or not args.end_date:
        parser.error("--channels, --start-date, and --end-date are required (or use --list-channels)")

    # Parse channel list
    channel_list = [ch.strip() for ch in args.channels.split(',')]

    # Validate date range
    if args.start_date > args.end_date:
        parser.error("start-date must be before or equal to end-date")

    # Run the workflow
    asyncio.run(run_workflow(
        channel_list,
        args.start_date,
        args.end_date,
        args.auto_process,
        args.max_messages
    ))


if __name__ == "__main__":
    main()
