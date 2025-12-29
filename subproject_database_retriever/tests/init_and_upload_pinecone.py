"""
Script to initialize (clear) Pinecone index and upload all processed CSVs.
"""

import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent / 'subproject_database_manager'))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / '.env')

from pinecone import Pinecone
from embedding_generation import generate_embeddings_from_csv
from pinecone_uploader import upsert_embeddings, get_index_stats

# Config
INDEX_NAME = "research-papers"
PROCESSED_FOLDER = Path(__file__).parent.parent.parent / 'subproject_database_manager' / 'data' / 'processed'


def clear_index(pc: Pinecone, index_name: str):
    """Delete all vectors from the index."""
    print(f"\n=== Clearing index '{index_name}' ===")

    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    print(f"Current vector count: {stats.total_vector_count}")

    if stats.total_vector_count > 0:
        # Delete all vectors by deleting all namespaces
        # For serverless, we need to delete by IDs or use delete_all
        print("Deleting all vectors...")
        index.delete(delete_all=True)
        print("All vectors deleted.")
    else:
        print("Index is already empty.")

    # Verify
    stats = index.describe_index_stats()
    print(f"Vector count after clearing: {stats.total_vector_count}")


def upload_all_processed_csvs(pc: Pinecone, index_name: str, processed_folder: Path):
    """Upload all processed CSVs to Pinecone."""
    print(f"\n=== Uploading CSVs from {processed_folder} ===")

    csv_files = list(processed_folder.glob("processed_*.csv"))
    print(f"Found {len(csv_files)} processed CSV files:")
    for f in csv_files:
        print(f"  - {f.name}")

    total_uploaded = 0

    for csv_file in csv_files:
        print(f"\n--- Processing: {csv_file.name} ---")

        # Generate embeddings
        embeddings_data = generate_embeddings_from_csv(str(csv_file))

        if not embeddings_data:
            print(f"No embeddings generated for {csv_file.name}, skipping.")
            continue

        # Upload to Pinecone
        result = upsert_embeddings(embeddings_data, index_name)
        total_uploaded += result.get("upserted_count", 0)

    print(f"\n=== Upload Complete ===")
    print(f"Total vectors uploaded: {total_uploaded}")

    # Final stats
    get_index_stats(index_name)


def main():
    print("=== Pinecone Index Initialization and Upload ===")

    # Initialize Pinecone
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

    # List available indexes
    print("\nAvailable indexes:")
    indexes = pc.list_indexes()
    for idx in indexes:
        print(f"  - {idx.name}")

    # Clear the index
    clear_index(pc, INDEX_NAME)

    # Upload all processed CSVs
    upload_all_processed_csvs(pc, INDEX_NAME, PROCESSED_FOLDER)


if __name__ == "__main__":
    main()
