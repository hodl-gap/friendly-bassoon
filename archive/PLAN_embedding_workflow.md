# Embedding Workflow Implementation Plan

## Overview

Create a new vector embedding workflow that:
1. Reads processed CSV files (structured outputs)
2. Embeds the `extracted_data` JSON using OpenAI embeddings
3. Prepares for Pinecone upsert (placeholder node)

## Implementation Steps

### Step 1: Add OpenAI Embedding Function to models.py

Add `call_openai_embedding()` function to `/mnt/c/Users/xmega/PycharmProjects/project_macro_analyst/models.py`:

```python
def call_openai_embedding(text: str, model: str = "text-embedding-3-large") -> List[float]:
    """
    Generate embedding vector for text using OpenAI embeddings API.

    Args:
        text: Text to embed
        model: Embedding model ("text-embedding-3-large" or "text-embedding-3-small")

    Returns:
        List of floats (embedding vector)

    Pricing: $0.13/1M tokens (large), $0.02/1M tokens (small)
    Dimensions: 3072 (large) or 1536 (small)
    """
    response = openai_client.embeddings.create(
        model=model,
        input=text
    )
    return response.data[0].embedding
```

Also add batch version for efficiency:
```python
def call_openai_embedding_batch(texts: List[str], model: str = "text-embedding-3-large") -> List[List[float]]:
    """Batch embed multiple texts in single API call (max 2048 texts)"""
    response = openai_client.embeddings.create(
        model=model,
        input=texts
    )
    return [item.embedding for item in response.data]
```

### Step 2: Create embedding_generation.py

Location: `/mnt/c/Users/xmega/PycharmProjects/project_macro_analyst/subproject_database_manager/embedding_generation.py`

Function module that:
- Input: Path to processed CSV file
- Reads CSV, extracts `extracted_data` column
- Calls `call_openai_embedding_batch()` from models.py
- Output: List of dicts with `{id, embedding, metadata}`

```python
import sys
sys.path.append('../')
from models import call_openai_embedding_batch

def generate_embeddings_from_csv(csv_path: str) -> list[dict]:
    """
    Generate embeddings for all extracted_data entries in a processed CSV.

    Returns list of:
    {
        "id": "{opinion_id}_{row_num}",
        "embedding": [float, ...],
        "metadata": {
            "date": "...",
            "tg_channel": "...",
            "category": "...",
            "raw_text": "...",
            "extracted_data": "..."  # original JSON string
        }
    }
    """
```

### Step 3: Create Test Script

Location: `/mnt/c/Users/xmega/PycharmProjects/project_macro_analyst/subproject_database_manager/tests/test_embedding.py`

Simple test that:
1. Loads one processed CSV
2. Embeds 2-3 rows
3. Prints embedding dimensions and sample values
4. Verifies embeddings are valid floats

### Step 4: Create vector_db_orchestrator.py

Location: `/mnt/c/Users/xmega/PycharmProjects/project_macro_analyst/subproject_database_manager/vector_db_orchestrator.py`

Main orchestrator with two nodes:
1. **embedding_node**: Calls `embedding_generation.py`
2. **pinecone_node**: Placeholder (pass-through for now)

Structure following telegram_workflow_orchestrator.py pattern:
```python
def main():
    # Parse args (--input csv path)

    # Step 1: Generate embeddings
    print("Step 1: Generating embeddings...")
    embeddings_data = generate_embeddings_from_csv(input_csv)

    # Step 2: Upsert to Pinecone (placeholder)
    print("Step 2: Pinecone upsert (not implemented)")
    # pinecone_upsert(embeddings_data)  # TODO

    print("Done!")
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `../models.py` | Add `call_openai_embedding()` and `call_openai_embedding_batch()` |
| `embedding_generation.py` | Create - function module |
| `vector_db_orchestrator.py` | Create - main orchestrator |
| `tests/test_embedding.py` | Create - test script |

## Execution Order

1. Add embedding functions to models.py
2. Create embedding_generation.py
3. Create test_embedding.py and verify it works
4. Create vector_db_orchestrator.py with placeholder pinecone node

## Notes

- Embed full `extracted_data` JSON as-is (per user confirmation)
- Use `text-embedding-3-large` model (3072 dimensions, higher quality)
- Batch API can handle up to 2048 texts per call
- No prompts file needed (embeddings don't use prompts)
- Pinecone node left empty for next phase
