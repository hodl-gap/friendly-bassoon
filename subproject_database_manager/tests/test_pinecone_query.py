"""
Test script for querying Pinecone and saving results to CSV.
"""

import os
import sys
import csv
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from pinecone import Pinecone
from models import call_openai_embedding

# Load .env from project root
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

# Initialize Pinecone
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
INDEX_NAME = "research-papers"


def query_pinecone(query_text: str, top_k: int = 10) -> list[dict]:
    """
    Query Pinecone index with text query.

    Args:
        query_text: Natural language query
        top_k: Number of results to return

    Returns:
        List of results with score, metadata, extracted_data, and raw_text
    """
    # Generate embedding for query
    print(f"Generating embedding for query: '{query_text}'")
    query_embedding = call_openai_embedding(query_text)

    # Query Pinecone
    index = pc.Index(INDEX_NAME)
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True
    )

    # Parse results
    parsed_results = []
    for match in results.matches:
        result = {
            "rank": len(parsed_results) + 1,
            "score": match.score,
            "id": match.id,
            "date": match.metadata.get("date", ""),
            "tg_channel": match.metadata.get("tg_channel", ""),
            "category": match.metadata.get("category", ""),
            "entry_type": match.metadata.get("entry_type", ""),
            "raw_text": match.metadata.get("raw_text", ""),
            "extracted_data": match.metadata.get("extracted_data", "")
        }
        parsed_results.append(result)

    return parsed_results


def save_results_to_csv(results: list[dict], output_path: str):
    """Save query results to CSV file."""
    if not results:
        print("No results to save")
        return

    fieldnames = ["rank", "score", "id", "date", "tg_channel", "category", "entry_type", "raw_text", "extracted_data"]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved {len(results)} results to {output_path}")


if __name__ == "__main__":
    # Test query
    query = "rate cut and equity price"
    top_k = 10

    print(f"\n{'='*60}")
    print(f"Query: '{query}'")
    print(f"Top K: {top_k}")
    print(f"{'='*60}\n")

    # Run query
    results = query_pinecone(query, top_k=top_k)

    # Print results
    print(f"\nFound {len(results)} results:\n")
    for r in results:
        print(f"[{r['rank']}] Score: {r['score']:.4f}")
        print(f"    Channel: {r['tg_channel']} | Date: {r['date']}")
        print(f"    Category: {r['category']} | Type: {r['entry_type']}")
        print(f"    Raw text (first 200 chars): {r['raw_text'][:200]}...")
        print()

    # Save to CSV
    output_path = Path(__file__).parent / "pinecone_query_results.csv"
    save_results_to_csv(results, str(output_path))
