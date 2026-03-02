"""
Embedding Generation Module

Generates embeddings for processed CSV files using OpenAI embeddings API.
Input: Path to processed CSV file
Output: List of dicts with {id, embedding, metadata}
"""

import json
import sys
import pandas as pd
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from models import call_openai_embedding_batch
from chain_vocab import normalize_extracted_data


def build_embedding_text(extracted_data_str: str) -> str:
    """Compose a clean natural-language string for embedding from extracted_data JSON.

    Includes: what_happened, interpretation, chain narratives (cause -> effect: mechanism),
    and used_data. Excludes JSON syntax, field names, _normalized terms, dead fields.
    """
    try:
        d = json.loads(extracted_data_str) if extracted_data_str else {}
    except (json.JSONDecodeError, TypeError):
        return str(extracted_data_str) if extracted_data_str else ""

    parts = []

    if d.get("what_happened"):
        parts.append(d["what_happened"])
    if d.get("interpretation"):
        parts.append(d["interpretation"])

    # Chain narratives using natural-language fields (not _normalized)
    for chain in d.get("logic_chains", []):
        for step in chain.get("steps", []):
            cause = step.get("cause", "")
            effect = step.get("effect", "")
            mechanism = step.get("mechanism", "")
            if cause and effect:
                if mechanism:
                    parts.append(f"{cause} -> {effect}: {mechanism}")
                else:
                    parts.append(f"{cause} -> {effect}")

    if d.get("used_data"):
        ud = d["used_data"]
        if isinstance(ud, str):
            parts.append(ud)
        elif isinstance(ud, list):
            parts.append(", ".join(str(item) for item in ud))
        else:
            parts.append(str(ud))

    return ". ".join(parts) if parts else str(extracted_data_str)


def generate_embeddings_from_csv(csv_path: str) -> list[dict]:
    """
    Generate embeddings for all extracted_data entries in a processed CSV.

    Args:
        csv_path: Path to processed CSV file

    Returns:
        List of dicts:
        {
            "id": "{hash}_{row_num}",
            "embedding": [float, ...],
            "metadata": {
                "date": "...",
                "tg_channel": "...",
                "category": "...",
                "source": "...",           # Extracted to top level for direct access
                "what_happened": "...",    # Extracted to top level for direct access
                "interpretation": "...",   # Extracted to top level for direct access
                "extracted_data": "..."    # Full JSON for logic_chains access
            }
        }

    Note: raw_text removed from metadata to reduce bloat (~1KB savings per record).
          Key fields extracted to top level for efficient retriever access.
    """
    print(f"Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"Total rows: {len(df)}")

    # Filter rows with extracted_data
    df_with_data = df[df['extracted_data'].notna() & (df['extracted_data'] != '')]
    print(f"Rows with extracted_data: {len(df_with_data)}")

    if len(df_with_data) == 0:
        print("No rows with extracted_data found")
        return []

    # Prepare texts for embedding (clean natural-language string, not raw JSON)
    texts = [build_embedding_text(ed) for ed in df_with_data['extracted_data'].tolist()]

    # Generate embeddings in batch
    print(f"Generating embeddings for {len(texts)} entries...")
    embeddings = call_openai_embedding_batch(texts)
    print(f"Generated {len(embeddings)} embeddings (dimension: {len(embeddings[0])})")

    # Build result list
    results = []
    for idx, (_, row) in enumerate(df_with_data.iterrows()):
        # Create unique ID (must be ASCII)
        import hashlib  # noqa: E402 (legacy placement)
        raw_id = f"{row.get('tg_channel', '')}_{row.get('opinion_id', '')}_{idx}"
        unique_id = hashlib.md5(raw_id.encode()).hexdigest()[:16] + f"_{idx}"

        # Parse extracted_data to get key fields for direct access
        extracted_data_str = str(row.get('extracted_data', '{}'))
        try:
            extracted_dict = json.loads(extracted_data_str) if extracted_data_str else {}
        except json.JSONDecodeError:
            extracted_dict = {}

        # Normalize chain vocab in metadata (safety net for pre-normalization CSVs)
        if extracted_dict.get("logic_chains"):
            normalize_extracted_data(extracted_dict)
            extracted_data_str = json.dumps(extracted_dict, ensure_ascii=False)

        results.append({
            "id": unique_id,
            "embedding": embeddings[idx],
            "metadata": {
                # Deduplication key - Telegram message ID for tracking
                "telegram_msg_id": str(row.get('telegram_msg_id', '')),
                # Core fields for filtering
                "date": str(row.get('date', '')),
                "tg_channel": str(row.get('tg_channel', '')),
                "category": str(row.get('category', '')),
                # Key fields extracted to top level for efficient access (fixes vector_search.py bug)
                "source": extracted_dict.get('source', ''),
                "what_happened": extracted_dict.get('what_happened', ''),
                "interpretation": extracted_dict.get('interpretation', ''),
                # Full extracted_data for logic_chains access (required by answer_generation)
                "extracted_data": extracted_data_str
                # NOTE: raw_text removed - not used by retriever, saves ~1KB per record
            }
        })

    print(f"Prepared {len(results)} embedding records")
    return results


if __name__ == "__main__":
    # Quick test with existing processed CSV
    import argparse

    parser = argparse.ArgumentParser(description="Generate embeddings from processed CSV")
    parser.add_argument("--input", type=str, required=True, help="Path to processed CSV file")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows to embed (for testing)")
    args = parser.parse_args()

    results = generate_embeddings_from_csv(args.input)

    if results:
        print(f"\nSample result:")
        print(f"  ID: {results[0]['id']}")
        print(f"  Embedding dim: {len(results[0]['embedding'])}")
        print(f"  Embedding sample: {results[0]['embedding'][:5]}...")
        print(f"  Metadata keys: {list(results[0]['metadata'].keys())}")
