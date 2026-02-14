"""
Web Chain Persistence

After each query, store verified web chains permanently in Pinecone
so subsequent queries benefit from previously discovered knowledge.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


def persist_web_chains(web_chains: List[Dict[str, Any]], query: str) -> int:
    """
    Persist verified web chains to Pinecone for future retrieval.

    Filters for chains with quote_verified=True AND confidence in ("high", "medium").
    Normalizes flat web chain schema to Pinecone metadata format.

    Args:
        web_chains: List of web chain dicts from gap filling
        query: Original query that triggered the chains

    Returns:
        Count of persisted chains
    """
    if not web_chains:
        return 0

    # Filter: only verified + high/medium confidence
    eligible = [
        c for c in web_chains
        if c.get("quote_verified", False)
        and c.get("confidence", "").lower() in ("high", "medium")
    ]

    if not eligible:
        print(f"[web_chain_persistence] No eligible chains (0/{len(web_chains)} passed filter)")
        return 0

    try:
        from pinecone import Pinecone
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from models import call_openai_embedding
    except ImportError as e:
        print(f"[web_chain_persistence] Import error: {e}")
        return 0

    # Connect to Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = os.getenv("PINECONE_INDEX_NAME", "research-papers")
    index = pc.Index(index_name)

    vectors = []
    for chain in eligible:
        cause = chain.get("cause", "")
        effect = chain.get("effect", "")
        mechanism = chain.get("mechanism", "")
        source_name = chain.get("source_name", "Web")
        polarity = chain.get("polarity", "unknown")
        evidence_quote = chain.get("evidence_quote", "")

        # Build chain text for embedding
        chain_text = f"{cause} -> {effect}: {mechanism}"

        # Generate ID
        id_input = f"{cause}{effect}{source_name}"
        chain_id = f"web_{hashlib.md5(id_input.encode()).hexdigest()[:16]}"

        # Normalize to canonical LogicChain format for extracted_data
        cause_normalized = cause.lower().replace(" ", "_").replace("-", "_")[:50]
        effect_normalized = effect.lower().replace(" ", "_").replace("-", "_")[:50]

        logic_chain_data = {
            "logic_chains": [{
                "steps": [{
                    "cause": cause,
                    "cause_normalized": cause_normalized,
                    "effect": effect,
                    "effect_normalized": effect_normalized,
                    "mechanism": mechanism,
                }],
                "chain_summary": f"{cause_normalized} -> {effect_normalized}",
                "source": source_name,
                "source_type": "web",
                "confidence_weight": 0.7,
            }],
            "source": source_name,
        }

        # Build metadata matching Pinecone schema used by database_manager
        metadata = {
            "source": source_name,
            "what_happened": f"{cause} -> {effect}",
            "interpretation": mechanism,
            "category": "web_chain",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "extracted_data": json.dumps(logic_chain_data),
            "query_origin": query[:200],
        }

        # Generate embedding
        try:
            embedding = call_openai_embedding(chain_text)
        except Exception as e:
            print(f"[web_chain_persistence] Embedding failed for {chain_id}: {e}")
            continue

        vectors.append({
            "id": chain_id,
            "values": embedding,
            "metadata": metadata,
        })

    if not vectors:
        return 0

    # Upsert to Pinecone
    try:
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            index.upsert(vectors=batch)
        print(f"[web_chain_persistence] Persisted {len(vectors)} web chains to Pinecone")
    except Exception as e:
        print(f"[web_chain_persistence] Upsert failed: {e}")
        return 0

    return len(vectors)
