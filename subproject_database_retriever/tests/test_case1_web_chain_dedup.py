"""
Test Case 1 web chain dedup: query Pinecone for saved web chains,
show raw vs deduped counts.
"""

import sys
import os
import json
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / '.env')

from vector_search import search_single_query, search_saved_web_chains, _dedup_web_chain_results, WEB_CHAINS_ONLY_FILTER


QUERY = "What caused the SaaS meltdown in Feb 2026?"


def main():
    print(f"{'=' * 70}")
    print(f"CASE 1 WEB CHAIN DEDUP TEST")
    print(f"Query: {QUERY}")
    print(f"{'=' * 70}\n")

    # Step 1: Raw (no dedup) — call search_single_query directly
    print("─── RAW (no dedup) ───")
    raw_chunks = search_single_query(
        QUERY, top_k=8, threshold=0.35,
        filter=WEB_CHAINS_ONLY_FILTER
    )
    print(f"\nRaw web chain results: {len(raw_chunks)}")
    for i, chunk in enumerate(raw_chunks, 1):
        meta = chunk.get("metadata", {})
        what = meta.get("what_happened", "N/A")
        source = meta.get("source", "N/A")
        vc = meta.get("validation_count", 1)
        print(f"  {i}. [{chunk['score']:.3f}] {what}  (source={source}, vc={vc})")

    # Step 2: Deduped — call search_saved_web_chains (which now deduplicates)
    print(f"\n─── DEDUPED (Jaccard 0.60) ───")
    deduped_chunks = search_saved_web_chains(QUERY, top_k=8, threshold=0.35)
    print(f"\nDeduped web chain results: {len(deduped_chunks)}")
    for i, chunk in enumerate(deduped_chunks, 1):
        meta = chunk.get("metadata", {})
        what = meta.get("what_happened", "N/A")
        source = meta.get("source", "N/A")
        vc = meta.get("validation_count", 1)
        sc = meta.get("similar_count", 1)
        print(f"  {i}. [{chunk['score']:.3f}] {what}  (source={source}, validation_count={vc}, similar_count={sc})")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(raw_chunks)} raw → {len(deduped_chunks)} deduped")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
