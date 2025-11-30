# Database Manager Subproject

Vector database management system for financial research papers. Part of the macro analyst project.

## Core Execution Files

### 1. Telegram Workflow (Data Ingestion)

```bash
python telegram_workflow_orchestrator.py \
  --channels "hyottchart" \
  --start-date 2025-11-23 \
  --end-date 2025-11-28
```

**Entry point**: `telegram_workflow_orchestrator.py`

Fetches Telegram messages → categorizes → extracts structured data → QA validation

| File | Purpose |
|------|---------|
| `telegram_workflow_orchestrator.py` | Main orchestrator |
| `telegram_fetcher.py` | Telegram API client (Telethon) |
| `extract_telegram_data.py` | JSON to CSV converter |
| `process_messages_v3.py` | Message processor (categorization + extraction) |
| `qa_validation.py` | QA sampling validation |

### 2. Vector DB Workflow (Embedding & Storage)

```bash
python vector_db_orchestrator.py --input data/processed/processed_xxx.csv
```

**Entry point**: `vector_db_orchestrator.py`

Reads processed CSV → generates embeddings → upserts to Pinecone

| File | Purpose |
|------|---------|
| `vector_db_orchestrator.py` | Main orchestrator |
| `embedding_generation.py` | OpenAI embeddings (text-embedding-3-large) |
| `pinecone_uploader.py` | Pinecone vector upsert |

### 3. Utility Scripts

```bash
# Normalize institution names in metrics dictionary
python metrics_mapping_utils.py

# Standalone QA validation (all entries)
python qa_post_processor.py --input data/processed/processed_xxx.csv
```

## Dependencies

### Python Packages

```bash
pip install pandas openai anthropic pinecone telethon python-dotenv
```

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | >=2.0 | Data manipulation |
| `openai` | >=1.0 | GPT models + embeddings |
| `anthropic` | >=0.18 | Claude models |
| `pinecone` | >=3.0 | Vector database |
| `telethon` | >=1.28 | Telegram API |
| `python-dotenv` | >=1.0 | Environment variables |

### Environment Variables

Create `.env` file in parent directory (`project_macro_analyst/`):

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
PINECONE_API_KEY=pcsk_...

# For Telegram fetcher
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELEGRAM_PHONE=...
```

### External Services

| Service | Purpose | Index/Model |
|---------|---------|-------------|
| OpenAI | Embeddings, GPT-4.1, GPT-5 | `text-embedding-3-large` (3072 dim) |
| Anthropic | Claude Sonnet 4.5 | `claude-sonnet-4-5-20250929` |
| Pinecone | Vector storage | `research-papers` index |
| Telegram | Message source | Telethon client |

## File Structure

```
subproject_database_manager/
├── telegram_workflow_orchestrator.py  # Main: Telegram ingestion
├── vector_db_orchestrator.py          # Main: Vector DB
├── process_messages_v3.py             # Message processing
├── embedding_generation.py            # Embeddings
├── pinecone_uploader.py               # Pinecone upsert
├── metrics_mapping_utils.py           # Metrics + source normalization
├── qa_validation.py                   # QA validation
├── *_prompts.py                       # LLM prompts
├── data/
│   ├── raw/                           # Telegram exports
│   ├── processed/                     # Final CSVs
│   │   └── liquidity_metrics/         # Metrics dictionary
│   └── qa_logs/                       # QA validation logs
├── STATUS.md                          # Development status
├── CLAUDE.md                          # AI assistant context
└── README.md                          # This file

Parent directory (project_macro_analyst/):
├── models.py                          # All AI model functions
└── .env                               # API keys
```

## Quick Start

```bash
# 1. Install dependencies
pip install pandas openai anthropic pinecone telethon python-dotenv

# 2. Set up .env file in parent directory

# 3. Fetch and process Telegram messages
python telegram_workflow_orchestrator.py \
  --channels "hyottchart" \
  --start-date 2025-11-28 \
  --end-date 2025-11-28

# 4. Embed and upload to Pinecone
python vector_db_orchestrator.py \
  --input data/processed/processed_xxx.csv
```

## Output

- `data/processed/processed_*.csv` - Structured extractions with metadata
- `data/processed/liquidity_metrics/liquidity_metrics_mapping.csv` - Metrics dictionary
- Pinecone index `research-papers` - Vector embeddings for retrieval
