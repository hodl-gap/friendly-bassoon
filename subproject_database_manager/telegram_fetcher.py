"""
Standalone Telegram Message Fetcher

Fetches messages and images from specified Telegram channels within a date range
and exports them in ChatExport_YYYY-MM-DD format (compatible with extract_telegram_data.py)

Usage:
    python telegram_fetcher.py --channels "Channel1,Channel2" --start-date 2025-11-20 --end-date 2025-11-23
    python telegram_fetcher.py --list-channels  # List all available channels
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import argparse

from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto
from dotenv import load_dotenv

# Load environment variables from parent directory
sys.path.append('../')
load_dotenv('../.env')

# Telegram API credentials from .env
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE = os.getenv('TELEGRAM_PHONE_NUMBER')
SESSION_NAME = '../telegram_session'  # Session file in parent directory


async def get_all_channels(client):
    """
    Get list of all channels the user has access to

    Returns:
        list: List of dicts with channel info (id, title, username)
    """
    print("\n=== Fetching all channels ===")

    dialogs = await client.get_dialogs()
    channels = []

    for dialog in dialogs:
        if dialog.is_channel:
            channel_info = {
                'id': dialog.id,
                'title': dialog.title,
                'username': dialog.entity.username if hasattr(dialog.entity, 'username') else None
            }
            channels.append(channel_info)
            print(f"  - {dialog.title} (ID: {dialog.id})")

    print(f"\nFound {len(channels)} channels")
    return channels


async def fetch_messages_by_date_range(client, channel_identifier, start_date, end_date, limit=None):
    """
    Fetch messages from a channel within a date range

    Args:
        client: Telethon client
        channel_identifier: Channel username, title, or ID
        start_date: datetime object for start date (naive)
        end_date: datetime object for end date (naive)
        limit: Maximum number of messages to fetch (None = all)

    Returns:
        list: List of message objects
    """
    print(f"\n=== Fetching messages from '{channel_identifier}' ===")
    print(f"Date range: {start_date.date()} to {end_date.date()}")

    # Make dates timezone-aware (UTC)
    from datetime import timezone
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        # Set to end of day (23:59:59)
        end_date = end_date.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    # Get the channel entity
    try:
        channel = await client.get_entity(channel_identifier)
    except Exception as e:
        print(f"Error: Could not find channel '{channel_identifier}': {e}")
        return []

    messages = []

    # Telethon's offset_date works backwards from the given date
    # We want messages between start_date and end_date
    # So we fetch from end_date + 1 day, going backwards
    offset_date = end_date + timedelta(days=1)

    async for message in client.iter_messages(
        channel,
        offset_date=offset_date,
        reverse=False  # Get newest first
    ):
        # Stop if we've gone past the start_date
        if message.date < start_date:
            break

        # Only include messages within range
        if start_date <= message.date <= end_date:
            messages.append(message)

        # Apply limit if specified
        if limit and len(messages) >= limit:
            break

    print(f"Fetched {len(messages)} messages")
    return messages


async def download_message_images(client, messages, output_dir):
    """
    Download images from messages

    Args:
        client: Telethon client
        messages: List of message objects
        output_dir: Directory to save images (e.g., "photos/")

    Returns:
        dict: Mapping of message_id -> relative image path
    """
    print(f"\n=== Downloading images to {output_dir} ===")

    # Create photos directory
    photos_dir = Path(output_dir)
    photos_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}
    downloaded = 0

    for msg in messages:
        if msg.photo:
            # Create filename: photo_<msg_id>@<date>_<time>.jpg
            date_str = msg.date.strftime("%d-%m-%Y_%H-%M-%S")
            filename = f"photo_{msg.id}@{date_str}.jpg"
            filepath = photos_dir / filename

            # Download the photo
            try:
                await client.download_media(msg.photo, file=str(filepath))
                # Store relative path (relative to export folder)
                image_paths[msg.id] = f"photos/{filename}"
                downloaded += 1
                print(f"  Downloaded: {filename}")
            except Exception as e:
                print(f"  Error downloading photo from message {msg.id}: {e}")

    print(f"Downloaded {downloaded} images")
    return image_paths


def convert_to_chatexport_format(channel, messages, image_paths):
    """
    Convert Telethon messages to ChatExport JSON format

    Args:
        channel: Channel entity
        messages: List of message objects
        image_paths: Dict mapping message_id -> image path

    Returns:
        dict: ChatExport-compatible JSON structure
    """
    print("\n=== Converting to ChatExport format ===")

    export_data = {
        "name": channel.title,
        "type": "public_channel" if hasattr(channel, 'broadcast') and channel.broadcast else "private_channel",
        "id": channel.id,
        "messages": []
    }

    for msg in messages:
        # Build text entities
        text_entities = []
        if msg.text:
            # Simple plain text entity (can be enhanced to parse formatting)
            text_entities.append({
                "type": "plain",
                "text": msg.text
            })

        message_dict = {
            "id": msg.id,
            "type": "message",
            "date": msg.date.isoformat(),
            "date_unixtime": str(int(msg.date.timestamp())),
            "from": channel.title,
            "from_id": f"channel{channel.id}",
            "text": msg.text or "",
            "text_entities": text_entities
        }

        # Add photo info if exists
        if msg.id in image_paths:
            message_dict["photo"] = image_paths[msg.id]
            # Note: We don't have photo_file_size, width, height from Telethon easily
            # These can be added if needed

        # Add reply_to if exists
        if msg.reply_to and msg.reply_to.reply_to_msg_id:
            message_dict["reply_to_message_id"] = msg.reply_to.reply_to_msg_id

        export_data["messages"].append(message_dict)

    print(f"Converted {len(export_data['messages'])} messages")
    return export_data


async def fetch_and_export(channel_names, start_date, end_date, output_base_dir="telegram_messages"):
    """
    Main function to fetch messages and export in ChatExport format

    Args:
        channel_names: List of channel names/IDs to fetch from
        start_date: datetime object for start date
        end_date: datetime object for end date
        output_base_dir: Base directory for exports (default: "telegram_messages")

    Returns:
        list: List of export folder paths created in this run
    """
    # Initialize Telegram client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    await client.start(phone=PHONE)
    print("✅ Connected to Telegram")

    # Create base output directory
    base_path = Path(output_base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    # Track folders created in this run
    created_folders = []

    # Process each channel
    for channel_name in channel_names:
        print(f"\n{'='*60}")
        print(f"Processing channel: {channel_name}")
        print(f"{'='*60}")

        # Fetch messages
        messages = await fetch_messages_by_date_range(
            client,
            channel_name,
            start_date,
            end_date
        )

        if not messages:
            print(f"⚠️  No messages found for {channel_name}")
            continue

        # Get channel entity for metadata
        channel = await client.get_entity(channel_name)

        # Create channel-specific export folder
        # Format: ChatExport_<channel_name>_<end_date>
        safe_channel_name = "".join(c for c in channel.title if c.isalnum() or c in (' ', '-', '_')).strip()
        export_folder_name = f"ChatExport_{safe_channel_name}_{end_date.strftime('%Y-%m-%d')}"
        export_path = base_path / export_folder_name
        export_path.mkdir(parents=True, exist_ok=True)

        # Download images
        photos_path = export_path / "photos"
        image_paths = await download_message_images(client, messages, photos_path)

        # Convert to ChatExport format
        export_data = convert_to_chatexport_format(channel, messages, image_paths)

        # Save JSON file
        json_path = export_path / "result.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=1)

        print(f"\n✅ Export complete!")
        print(f"   Location: {export_path}")
        print(f"   Messages: {len(messages)}")
        print(f"   Images: {len(image_paths)}")
        print(f"   JSON: {json_path}")

        # Track this folder
        created_folders.append(str(export_path))

    await client.disconnect()
    print("\n✅ All channels processed successfully")

    return created_folders


async def list_channels_only():
    """List all available channels and exit"""
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(phone=PHONE)

    channels = await get_all_channels(client)

    print("\n" + "="*60)
    print("Available Channels:")
    print("="*60)
    for ch in channels:
        username_str = f" (@{ch['username']})" if ch['username'] else ""
        print(f"  📢 {ch['title']}{username_str}")
        print(f"     ID: {ch['id']}")
        print()

    await client.disconnect()


def parse_date(date_str):
    """Parse date string in YYYY-MM-DD format"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(
        description='Fetch Telegram messages and images from specified channels',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available channels
  python telegram_fetcher.py --list-channels

  # Fetch from one channel
  python telegram_fetcher.py --channels "Channel Name" --start-date 2025-11-20 --end-date 2025-11-23

  # Fetch from multiple channels
  python telegram_fetcher.py --channels "Channel1,Channel2,Channel3" --start-date 2025-11-01 --end-date 2025-11-30

  # Custom output directory
  python telegram_fetcher.py --channels "MyChannel" --start-date 2025-11-20 --end-date 2025-11-23 --output my_exports
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
        help='Comma-separated list of channel names or IDs to fetch from'
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
        '--output',
        type=str,
        default='telegram_messages',
        help='Output directory for exports (default: telegram_messages)'
    )

    args = parser.parse_args()

    # Validate environment variables
    if not API_ID or not API_HASH or not PHONE:
        print("❌ Error: Missing Telegram API credentials in .env file")
        print("Required variables: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE_NUMBER")
        sys.exit(1)

    # Handle list-channels mode
    if args.list_channels:
        asyncio.run(list_channels_only())
        return

    # Validate required arguments for fetch mode
    if not args.channels or not args.start_date or not args.end_date:
        parser.error("--channels, --start-date, and --end-date are required (or use --list-channels)")

    # Parse channel list
    channel_list = [ch.strip() for ch in args.channels.split(',')]

    # Validate date range
    if args.start_date > args.end_date:
        parser.error("start-date must be before or equal to end-date")

    # Run the fetcher
    print("\n" + "="*60)
    print("Telegram Message Fetcher")
    print("="*60)
    print(f"Channels: {', '.join(channel_list)}")
    print(f"Date range: {args.start_date.date()} to {args.end_date.date()}")
    print(f"Output directory: {args.output}")
    print("="*60 + "\n")

    asyncio.run(fetch_and_export(
        channel_list,
        args.start_date,
        args.end_date,
        args.output
    ))


if __name__ == "__main__":
    main()
