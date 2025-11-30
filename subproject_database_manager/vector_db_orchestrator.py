"""
Vector Database Orchestrator

Main entry point for embedding and upserting processed data to Pinecone.

Usage:
    python vector_db_orchestrator.py --input data/processed/processed_xxx.csv
"""

import argparse
from pathlib import Path

from embedding_generation import generate_embeddings_from_csv
from pinecone_uploader import upsert_embeddings, get_index_stats

# Default index name
DEFAULT_INDEX = "research-papers"


def main():
    parser = argparse.ArgumentParser(description="Vector DB workflow: embed and upsert to Pinecone")
    parser.add_argument("--input", type=str, required=True, help="Path to processed CSV file")
    parser.add_argument("--index", type=str, default=DEFAULT_INDEX, help="Pinecone index name")
    parser.add_argument("--namespace", type=str, default="", help="Pinecone namespace")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return

    print("=" * 60)
    print("Vector DB Orchestrator")
    print("=" * 60)

    # Step 1: Generate embeddings
    print("\nStep 1: Generating embeddings...")
    embeddings_data = generate_embeddings_from_csv(str(input_path))

    if not embeddings_data:
        print("No embeddings generated. Exiting.")
        return

    print(f"\nGenerated {len(embeddings_data)} embeddings")

    # Step 2: Upsert to Pinecone
    print(f"\nStep 2: Upserting to Pinecone index '{args.index}'...")
    upsert_embeddings(embeddings_data, args.index, args.namespace)

    # Step 3: Show index stats
    print(f"\nStep 3: Index stats...")
    get_index_stats(args.index)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
