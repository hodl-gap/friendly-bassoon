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
SIMILARITY_THRESHOLD = 0.45  # Minimum similarity score to consider
MAX_CHUNKS_FOR_ANSWER = 15  # Limit chunks for answer generation to preserve LLM reasoning quality

# Embedding Configuration
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
