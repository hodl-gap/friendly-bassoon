"""
Configuration Management for Database Retriever

Loads environment variables and provides configuration constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent directory
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Pinecone Configuration
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "research-papers")

# Retrieval Settings
DEFAULT_TOP_K = 10  # Number of chunks to retrieve per query
MAX_ITERATIONS = 3  # Maximum agentic refinement iterations
SIMILARITY_THRESHOLD = 0.45  # Minimum similarity score to consider (DEPRECATED - use two-stage retrieval)
MAX_CHUNKS_FOR_ANSWER = 15  # Limit chunks for answer generation to preserve LLM reasoning quality

# Two-Stage Retrieval Settings (addresses 0.45 threshold risk)
ENABLE_LLM_RERANK = True  # Toggle LLM re-ranking (disable for cost savings)
BROAD_RETRIEVAL_TOP_K = 20  # Stage 1: Broad semantic recall (higher for better coverage)
BROAD_SIMILARITY_THRESHOLD = 0.40  # Stage 1: Lower threshold for recall
RERANK_TOP_K = 10  # Stage 2: Keep top N after LLM re-ranking

# Hybrid Retrieval Settings (addresses query expansion dilution)
ORIGINAL_QUERY_TOP_N = 5  # Guaranteed slots for original query's top results

# Embedding Configuration
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
