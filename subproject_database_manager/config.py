import os
from dotenv import load_dotenv

# Load environment variables from parent directory
load_dotenv('../.env')

# Pinecone Configuration
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
PINECONE_ENVIRONMENT = os.getenv('PINECONE_ENVIRONMENT')
PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME')

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
