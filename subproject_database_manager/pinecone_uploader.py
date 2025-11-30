"""
Pinecone Uploader Module

Upserts embedding records to Pinecone vector database.
Input: List of dicts with {id, embedding, metadata}
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone

# Load .env from parent directory
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Initialize Pinecone client
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))


def list_indexes():
    """List all available Pinecone indexes."""
    indexes = pc.list_indexes()
    print("Available indexes:")
    for idx in indexes:
        print(f"  - {idx.name} (dimension: {idx.dimension}, metric: {idx.metric})")
    return indexes


def upsert_embeddings(embeddings_data: list[dict], index_name: str, namespace: str = "") -> dict:
    """
    Upsert embedding records to Pinecone.

    Args:
        embeddings_data: List of dicts with {id, embedding, metadata}
        index_name: Name of Pinecone index
        namespace: Optional namespace for organization

    Returns:
        Upsert response from Pinecone
    """
    index = pc.Index(index_name)

    # Prepare vectors for upsert
    vectors = []
    for record in embeddings_data:
        vectors.append({
            "id": record["id"],
            "values": record["embedding"],
            "metadata": record["metadata"]
        })

    # Upsert in batches of 100 (Pinecone recommendation)
    batch_size = 100
    total_upserted = 0

    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        response = index.upsert(vectors=batch, namespace=namespace)
        total_upserted += response.upserted_count
        print(f"  Upserted batch {i // batch_size + 1}: {response.upserted_count} vectors")

    print(f"Total upserted: {total_upserted} vectors")
    return {"upserted_count": total_upserted}


def get_index_stats(index_name: str) -> dict:
    """Get statistics for a Pinecone index."""
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    print(f"Index stats for '{index_name}':")
    print(f"  Total vectors: {stats.total_vector_count}")
    print(f"  Namespaces: {list(stats.namespaces.keys())}")
    return stats


if __name__ == "__main__":
    # Quick test - list indexes
    print("Testing Pinecone connection...")
    list_indexes()
