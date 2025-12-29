"""
Test script to retrieve top 3 results for specific queries.
"""

import sys
import os
import json
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / '.env')

from pinecone import Pinecone
from models import call_openai_embedding

# Config
INDEX_NAME = "research-papers"
TOP_K = 3


def search_and_print(query: str, top_k: int = TOP_K):
    """Search Pinecone and print full results."""
    print(f"\n{'='*80}")
    print(f"QUERY: {query}")
    print(f"{'='*80}\n")

    # Initialize Pinecone
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
    index = pc.Index(INDEX_NAME)

    # Generate embedding
    print("Generating embedding...")
    embedding = call_openai_embedding(query)

    # Search
    print(f"Searching for top {top_k} results...\n")
    results = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True
    )

    # Print results
    for i, match in enumerate(results.matches):
        print(f"\n{'-'*80}")
        print(f"RESULT #{i+1}")
        print(f"Score: {match.score:.4f}")
        print(f"ID: {match.id}")
        print(f"{'-'*80}")

        metadata = match.metadata

        print(f"\n[Date]: {metadata.get('date', 'N/A')}")
        print(f"[Channel]: {metadata.get('tg_channel', 'N/A')}")
        print(f"[Category]: {metadata.get('category', 'N/A')}")

        print(f"\n[Raw Text]:")
        print(metadata.get('raw_text', 'N/A'))

        print(f"\n[Extracted Data]:")
        extracted = metadata.get('extracted_data', '{}')
        try:
            extracted_json = json.loads(extracted)
            print(json.dumps(extracted_json, indent=2, ensure_ascii=False))
        except:
            print(extracted)

    print(f"\n{'='*80}\n")


def main():
    # Query 1: Japan earthquake and FX rate impact
    search_and_print("japan earthquake and its impact on fx rate")

    # Query 2: Equity and liquidity expansion relationship
    search_and_print("relationship between equity and liquidity expansion")


if __name__ == "__main__":
    main()
