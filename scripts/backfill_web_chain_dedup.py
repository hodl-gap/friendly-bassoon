"""
Backfill: Deduplicate existing web chain vectors in Pinecone.

One-time script. Fetches all web_chain vectors with embeddings,
clusters by cosine similarity (0.85), deletes absorbed duplicates,
and updates representatives with validation_count metadata.

No re-embedding or LLM calls — pure read → cluster → write back.

Usage:
    python scripts/backfill_web_chain_dedup.py              # dry run (default)
    python scripts/backfill_web_chain_dedup.py --execute     # actually modify Pinecone
"""

import os
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from pinecone import Pinecone
from web_chain_persistence import _cluster_vectors


WEB_CHAINS_ONLY_FILTER = {"category": {"$eq": "web_chain"}}


def fetch_all_web_chains(index) -> list:
    """Fetch all web chain vectors with embeddings and metadata."""
    results = index.query(
        vector=[0.0] * 3072,
        top_k=10000,
        filter=WEB_CHAINS_ONLY_FILTER,
        include_metadata=True,
        include_values=True,
    )
    vectors = []
    for m in results.matches:
        vectors.append({
            "id": m.id,
            "values": m.values,
            "metadata": dict(m.metadata),
        })
    return vectors


def main():
    parser = argparse.ArgumentParser(description="Deduplicate web chain vectors in Pinecone")
    parser.add_argument("--execute", action="store_true", help="Actually modify Pinecone (default: dry run)")
    parser.add_argument("--threshold", type=float, default=0.85, help="Cosine similarity threshold (default: 0.85)")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"{'=' * 60}")
    print(f"Web Chain Dedup Backfill — {mode}")
    print(f"Threshold: {args.threshold}")
    print(f"{'=' * 60}\n")

    # Connect
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "research-papers"))

    # Step 1: Fetch
    print("Step 1: Fetching all web chain vectors...")
    vectors = fetch_all_web_chains(index)
    print(f"  Fetched: {len(vectors)} vectors\n")

    if len(vectors) == 0:
        print("No web chain vectors found. Nothing to do.")
        return

    all_ids = {v["id"] for v in vectors}

    # Step 2: Cluster
    print("Step 2: Clustering...")
    representatives = _cluster_vectors(vectors, threshold=args.threshold)
    rep_ids = {v["id"] for v in representatives}
    ids_to_delete = all_ids - rep_ids

    print(f"  Representatives: {len(representatives)}")
    print(f"  To delete: {len(ids_to_delete)}")

    # Representatives with updated validation_count
    reps_to_upsert = [v for v in representatives if v["metadata"].get("validation_count", 1) > 1]
    print(f"  To upsert (metadata update): {len(reps_to_upsert)}\n")

    # Show clusters
    multi = sorted(
        [v for v in representatives if v["metadata"].get("validation_count", 1) > 1],
        key=lambda v: v["metadata"]["validation_count"],
        reverse=True,
    )
    if multi:
        print("Clusters with validation_count > 1:")
        for i, v in enumerate(multi, 1):
            vc = v["metadata"]["validation_count"]
            wh = v["metadata"].get("what_happened", "N/A")[:80]
            print(f"  {i:2d}. [vc={vc}] {wh}")
        print()

    if not ids_to_delete and not reps_to_upsert:
        print("Nothing to change. Index is already clean.")
        return

    if not args.execute:
        print(f"DRY RUN complete. Re-run with --execute to apply changes.")
        print(f"  Would delete {len(ids_to_delete)} vectors")
        print(f"  Would upsert {len(reps_to_upsert)} metadata updates")
        return

    # Step 3: Delete absorbed vectors
    if ids_to_delete:
        print(f"Step 3: Deleting {len(ids_to_delete)} absorbed vectors...")
        delete_list = list(ids_to_delete)
        batch_size = 100
        for i in range(0, len(delete_list), batch_size):
            batch = delete_list[i:i + batch_size]
            index.delete(ids=batch)
            print(f"  Deleted batch {i // batch_size + 1}: {len(batch)} vectors")

    # Step 4: Upsert representatives with updated metadata
    if reps_to_upsert:
        print(f"Step 4: Upserting {len(reps_to_upsert)} representatives with validation_count...")
        batch_size = 100
        for i in range(0, len(reps_to_upsert), batch_size):
            batch = reps_to_upsert[i:i + batch_size]
            index.upsert(vectors=[
                {"id": v["id"], "values": v["values"], "metadata": v["metadata"]}
                for v in batch
            ])
            print(f"  Upserted batch {i // batch_size + 1}: {len(batch)} vectors")

    # Verify
    print(f"\nStep 5: Verifying...")
    post_vectors = fetch_all_web_chains(index)
    print(f"  Before: {len(vectors)}")
    print(f"  After:  {len(post_vectors)}")
    print(f"  Removed: {len(vectors) - len(post_vectors)}")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
