"""
Processing State Tracker

SQLite-based tracker for message processing state.
Enables deduplication across runs and resume capability for mid-run failures.

Usage:
    from processing_tracker import get_processed_msg_ids, mark_extracted, mark_uploaded

    # Check which messages are already processed
    processed = get_processed_msg_ids("channel_name")

    # After LLM extraction completes
    mark_extracted("channel_name", 12345)

    # After Pinecone upload completes
    mark_uploaded("channel_name", 12345)
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

# Database location
DB_PATH = Path(__file__).parent / "data" / "processing_state.db"


@contextmanager
def get_connection():
    """Get SQLite connection with context manager."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database schema if not exists."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_state (
                tg_channel TEXT NOT NULL,
                telegram_msg_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                extracted_at TEXT,
                uploaded_at TEXT,
                PRIMARY KEY (tg_channel, telegram_msg_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_status
            ON message_state(tg_channel, status)
        """)
        conn.commit()


def get_processed_msg_ids(tg_channel: str) -> set[int]:
    """
    Get set of telegram_msg_ids already processed for a channel.

    Args:
        tg_channel: Channel name

    Returns:
        Set of telegram message IDs that have been extracted or uploaded
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT telegram_msg_id FROM message_state WHERE tg_channel = ?",
            (tg_channel,)
        )
        return {row[0] for row in cursor.fetchall()}


def mark_extracted(tg_channel: str, telegram_msg_id: int):
    """
    Mark message as extraction completed.

    Args:
        tg_channel: Channel name
        telegram_msg_id: Telegram's message ID
    """
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO message_state (tg_channel, telegram_msg_id, status, extracted_at)
            VALUES (?, ?, 'extracted', ?)
            ON CONFLICT(tg_channel, telegram_msg_id) DO UPDATE SET
                status = CASE WHEN status = 'uploaded' THEN 'uploaded' ELSE 'extracted' END,
                extracted_at = COALESCE(extracted_at, ?)
        """, (tg_channel, telegram_msg_id, now, now))
        conn.commit()


def mark_uploaded(tg_channel: str, telegram_msg_id: int):
    """
    Mark message as uploaded to Pinecone.

    Args:
        tg_channel: Channel name
        telegram_msg_id: Telegram's message ID
    """
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO message_state (tg_channel, telegram_msg_id, status, uploaded_at)
            VALUES (?, ?, 'uploaded', ?)
            ON CONFLICT(tg_channel, telegram_msg_id) DO UPDATE SET
                status = 'uploaded',
                uploaded_at = ?
        """, (tg_channel, telegram_msg_id, now, now))
        conn.commit()


def get_pending_uploads(tg_channel: str = None) -> list[dict]:
    """
    Get messages extracted but not yet uploaded (for resume).

    Args:
        tg_channel: Optional channel filter. If None, returns all channels.

    Returns:
        List of dicts with tg_channel and telegram_msg_id
    """
    init_db()
    with get_connection() as conn:
        if tg_channel:
            cursor = conn.execute("""
                SELECT tg_channel, telegram_msg_id FROM message_state
                WHERE tg_channel = ? AND status = 'extracted'
            """, (tg_channel,))
        else:
            cursor = conn.execute("""
                SELECT tg_channel, telegram_msg_id FROM message_state
                WHERE status = 'extracted'
            """)
        return [{"tg_channel": row[0], "telegram_msg_id": row[1]} for row in cursor.fetchall()]


def sync_with_pinecone():
    """
    Sync tracker with Pinecone on startup.

    Query Pinecone for records with telegram_msg_id metadata
    and ensure local tracker reflects uploaded status.
    """
    try:
        from pinecone import Pinecone
        from dotenv import load_dotenv
        load_dotenv('../.env')

        api_key = os.getenv('PINECONE_API_KEY')
        index_name = os.getenv('PINECONE_INDEX_NAME', 'research-papers')

        if not api_key:
            print("  Pinecone API key not found, skipping sync")
            return

        pc = Pinecone(api_key=api_key)
        index = pc.Index(index_name)

        # Get index stats to check if any vectors exist
        stats = index.describe_index_stats()
        total_vectors = stats.get('total_vector_count', 0)

        if total_vectors == 0:
            print("  Pinecone index is empty, nothing to sync")
            return

        print(f"  Pinecone has {total_vectors} vectors, syncing...")

        # Query vectors to get metadata (limited approach - full sync would need list())
        # For now, just mark this as a placeholder for future enhancement
        # Full sync would require iterating through all vectors which is expensive
        print("  Note: Full Pinecone sync not implemented (would be expensive)")
        print("  Local tracker will be source of truth for new runs")

    except ImportError:
        print("  Pinecone not installed, skipping sync")
    except Exception as e:
        print(f"  Pinecone sync error: {e}")


def get_stats() -> dict:
    """Get statistics about tracked messages."""
    init_db()
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                tg_channel,
                status,
                COUNT(*) as count
            FROM message_state
            GROUP BY tg_channel, status
        """)

        stats = {}
        for row in cursor.fetchall():
            channel = row[0]
            if channel not in stats:
                stats[channel] = {"extracted": 0, "uploaded": 0}
            stats[channel][row[1]] = row[2]

        return stats


if __name__ == "__main__":
    # Quick test
    print("Processing Tracker Test")
    print("=" * 40)

    init_db()

    # Test marking
    test_channel = "__test_channel__"
    test_msg_id = 99999

    print(f"Marking message {test_msg_id} as extracted...")
    mark_extracted(test_channel, test_msg_id)

    processed = get_processed_msg_ids(test_channel)
    print(f"Processed IDs for {test_channel}: {processed}")

    print(f"Marking message {test_msg_id} as uploaded...")
    mark_uploaded(test_channel, test_msg_id)

    stats = get_stats()
    print(f"Stats: {stats}")

    # Cleanup test data
    with get_connection() as conn:
        conn.execute("DELETE FROM message_state WHERE tg_channel = ?", (test_channel,))
        conn.commit()

    print("\nTest complete (test data cleaned up)")
