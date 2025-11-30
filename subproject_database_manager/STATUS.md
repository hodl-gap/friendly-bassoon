# Project Status - Telegram Financial Message Processing Workflow

**Last Updated**: 2025-11-30

## Current State: Production-Ready with Vector DB Integration

Complete end-to-end workflow for fetching and processing financial research messages from Telegram channels with AI-powered analysis, categorization, structured data extraction, automated QA sampling, and vector database storage.

---

## Session Summary: 2025-11-30

### 1. Embedding Workflow Implemented

Added complete vector embedding pipeline for processed research data.

**New files**:
- `embedding_generation.py` - Generates OpenAI embeddings from processed CSV
- `pinecone_uploader.py` - Upserts vectors to Pinecone
- `vector_db_orchestrator.py` - Main entry point for vector DB workflow

**Added to `models.py`**:
- `call_openai_embedding()` - Single text embedding
- `call_openai_embedding_batch()` - Batch embedding (up to 2048 texts)

**Pinecone index**: `research-papers` (3072 dimensions, cosine metric)

**Usage**:
```bash
python vector_db_orchestrator.py --input data/processed/processed_xxx.csv
```

### 2. Source Entity Normalization

Added LLM-based normalization for institution names in metrics dictionary sources.

**Problem solved**: "GS FICC Desk", "Goldman Sachs", "GS FICC" → all normalize to "Goldman Sachs"

**New functions in `metrics_mapping_utils.py`**:
- `normalize_sources_in_csv()` - Batch normalizes all institution names
- `_batch_normalize_institutions()` - LLM call for entity resolution

**Integration**: Runs automatically after `append_new_metrics()` in pipeline

**Standalone cleanup**:
```bash
python metrics_mapping_utils.py
```

---

## Session Summary: 2025-11-29

### 1. Metrics Dictionary Source Tracking

Added `sources` column to `liquidity_metrics_mapping.csv` to track where metrics were first discovered.

**Format**: `Institution, data_source` (e.g., `UBS, Global equity strategy`)

**Features**:
- Sources are additive - if same metric appears from different sources, they're appended with `|`
- Uses `source` field (institution) + `data_source` field (specific report/data)
- NOT telegram channel names

**Updated files**:
- `metrics_mapping_utils.py` - `collect_new_metrics_from_extractions()` now builds combined source
- `metrics_mapping_utils.py` - `append_new_metrics()` handles additive sources for existing metrics
- `liquidity_metrics_mapping.csv` - Added `sources` column (79 metrics total)

### 2. GPT-5 with Claude Fallback

Switched extraction model from Claude Sonnet to GPT-5 with automatic Claude fallback.

**Configuration** (`process_messages_v3.py`):
```python
EXTRACTION_MODEL = "gpt5"
FALLBACK_MODEL = "claude_sonnet"
```

**Performance comparison** (7 messages, 5 batches):

| Metric | GPT-5 | Claude Sonnet |
|--------|-------|---------------|
| Step 4 Time | 55-132s | 61s |
| Total Time | 101-175s | 92s |
| Cost | ~$0.27 | ~$0.07 |
| Success Rate | 100% | 100% |

GPT-5 extracts more granular metrics but is slower and more expensive.

### 3. QA Sampling Integrated into Orchestrator

QA validation now runs automatically after processing, sampling a subset of extractions.

**Sampling logic**:
- Minimum: 3 samples
- Maximum: 20 samples
- Target: 5% of validatable entries
- Categories: `data_opinion`, `interview_meeting`

**Log output**: `data/qa_logs/qa_sample_{filename}_{timestamp}.txt`

**Test results** (18 entries → 3 sampled):
- PASS: 3/3 (100%)
- Avg Scores: R=0.87, C=0.83, A=0.85

---

## Architecture

```
telegram_workflow_orchestrator.py (MAIN ENTRY POINT)
    │
    ├─→ telegram_fetcher.py          → Fetch messages from Telegram API
    │                                 → Download images
    │                                 → Export to ChatExport format
    │
    ├─→ extract_telegram_data.py     → Convert JSON to CSV
    │
    ├─→ process_messages_v3.py       → Image-first processing
    │       │                         → Categorization (6 types)
    │       │                         → Structured extraction (GPT-5 + Claude fallback)
    │       │                         → Parallel batch processing
    │       │                         → Auto-update metrics dictionary
    │       │
    │       ├─→ models.py            → GPT-5, Claude 4.5 models
    │       │                         → process_batch_parallel_with_retry()
    │       │
    │       └─→ metrics_mapping_utils.py → Metric normalization
    │                                      → Source tracking
    │
    └─→ qa_validation.py             → QA sampling validation (integrated)
                                      → 3-dimensional quality check
                                      → Logs to data/qa_logs/

vector_db_orchestrator.py (SEPARATE ENTRY POINT)
    │
    ├─→ embedding_generation.py      → Generate embeddings (OpenAI text-embedding-3-large)
    │                                 → 3072 dimensions
    │
    └─→ pinecone_uploader.py         → Upsert vectors to Pinecone
                                      → Index: research-papers
                                      → Metadata attachment
```

**Note**: Vector DB workflow is separate from Telegram message processing. Run telegram orchestrator first to generate `processed_*.csv`, then run vector DB orchestrator to embed and upsert.

## File Structure

```
Main Workflow:
├── telegram_workflow_orchestrator.py  ⭐ MAIN ORCHESTRATOR
├── telegram_fetcher.py                  Telegram API fetcher
├── extract_telegram_data.py             JSON to CSV converter
├── process_messages_v3.py               V3 message processor
├── categorization_prompts.py            Categorization prompts
├── data_opinion_prompts.py              Data opinion extraction prompts
├── interview_meeting_prompts.py         Interview/meeting extraction prompts
├── qa_validation.py                     QA validation (with sample_qa_validation)
├── qa_validation_prompts.py             QA validation prompts
├── qa_post_processor.py                 QA validation CLI (standalone)
├── data/processed/liquidity_metrics/
│   └── liquidity_metrics_mapping.csv    Metrics dictionary (auto-grows, with sources)
├── metrics_mapping_utils.py             Metric normalization + source tracking + entity normalization

Vector DB Workflow:
├── vector_db_orchestrator.py         ⭐ VECTOR DB ORCHESTRATOR
├── embedding_generation.py              OpenAI embeddings generator
├── pinecone_uploader.py                 Pinecone vector uploader

Parent Directory:
├── models.py                            AI model functions
│                                        - GPT-5 series + Claude 4.5 series
│                                        - process_batch_parallel_with_retry()
└── .env                                 API keys

Data Folders:
├── data/
│   ├── raw/
│   │   ├── ChatExport_{channel}_{date}/
│   │   │   ├── result.json              Raw Telegram export
│   │   │   └── photos/                  Downloaded images
│   │   └── {channel}_{date}_messages.csv   Intermediate CSV (from JSON)
│   │
│   ├── processed/
│   │   ├── processed_{channel}_{date}.csv           ⭐ FINAL OUTPUT
│   │   ├── qa_validated_{...}.csv                   Full QA validated output (standalone)
│   │   ├── qa_validated_{...}_detailed_log.txt     Full QA validation log (standalone)
│   │   └── liquidity_metrics/
│   │       └── liquidity_metrics_mapping.csv        Metrics dictionary (auto-grows)
│   │
│   └── qa_logs/
│       └── qa_sample_{filename}_{timestamp}.txt    QA sampling log (from orchestrator)
```

## Usage

```bash
# Full workflow (fetch + process + QA sampling)
python telegram_workflow_orchestrator.py \
  --channels "hyottchart" \
  --start-date 2025-11-23 \
  --end-date 2025-11-28

# List available channels
python telegram_workflow_orchestrator.py --list-channels

# Fetch only (no processing)
python telegram_workflow_orchestrator.py \
  --channels "hyottchart" \
  --start-date 2025-11-23 \
  --end-date 2025-11-28 \
  --no-process

# Standalone full QA validation (all entries)
python qa_post_processor.py \
  --input data/processed/processed_xxx.csv \
  --categories data_opinion,interview_meeting
```

## Configuration

```python
# process_messages_v3.py
EXTRACTION_MODEL = "gpt5"           # Primary model
FALLBACK_MODEL = "claude_sonnet"    # Fallback if primary fails
MAX_CONCURRENT_REQUESTS = 10        # Parallel API calls
```

## Output Format

**Processed CSV columns:**
- `original_message_num`, `date`, `tg_channel`, `category`
- `entry_type`, `opinion_id`, `raw_text`, `has_photo`
- `extracted_data` - JSON with:
  - `source`, `data_source`, `asset_class`
  - `used_data`, `what_happened`, `interpretation`
  - `tags` (direct_liquidity | indirect_liquidity | irrelevant)
  - `liquidity_metrics[]` - normalized metrics with values/directions
  - `metric_relationships[]` - causal chains between metrics

**Metrics Dictionary CSV columns:**
- `normalized` - Standard metric name
- `variants` - Alternative names/spellings
- `category` - direct | indirect
- `description` - What the metric measures
- `sources` - Where metric was discovered (Institution, data_source)

## API Costs

| Model | Per Call | Notes |
|-------|----------|-------|
| Claude Sonnet 4.5 vision | ~$0.015 | Image analysis |
| GPT-4.1 mini | ~$0.0004 | Categorization |
| GPT-5 | ~$0.05 | Extraction (primary) |
| Claude Sonnet 4.5 text | ~$0.01 | Extraction (fallback) |
| GPT-4.1 | ~$0.01 | QA validation |

**Example run (7 messages, GPT-5):**
- Vision calls: $0.02
- Categorization: $0.003
- Extraction: $0.25
- QA sampling (3): $0.03
- **Total: ~$0.30 USD**

---

## TODO / Next Steps

### High Priority

1. **[x] Implement embedding workflow** ✅ Done 2025-11-30
   - Added `call_openai_embedding()` to models.py
   - Created `embedding_generation.py` function module
   - Created `vector_db_orchestrator.py` with Pinecone integration
   - Tested with processed CSV files (18 vectors upserted)

2. **[x] Source entity normalization** ✅ Done 2025-11-30
   - LLM-based institution name normalization
   - Integrated into pipeline after metrics update
   - Batch processing for efficiency

3. **[ ] Benchmark parallel vs sequential**
   - Compare Step 4 times
   - Document speedup factor
   - Identify optimal `MAX_CONCURRENT_REQUESTS` value

### Medium Priority

3. **[ ] Add categorization for 'individual_stock_research'**
   - Handle company/stock-specific research messages
   - Separate category with appropriate extractor

4. **[ ] Implement incremental updates**
   - Don't re-fetch messages already processed
   - Track processed message IDs

5. **[ ] Add keyword search support**
   - Telethon supports keyword filtering
   - Could reduce messages fetched

### Low Priority

6. **[ ] Blocking QA mode**
   - Halt pipeline on low QA scores
   - Require manual review before proceeding

7. **[ ] Auto-fix mode for QA**
   - LLM suggests fixes → apply automatically → re-validate

8. **[ ] Quality metrics dashboard**
   - Track QA scores over time
   - Identify extraction patterns

9. **[ ] Set up git remote**
   - Create remote repository (GitHub/GitLab)
   - Add origin and push

---

## Development Timeline

- **2025-11-21** - Project setup, basic structure
- **2025-11-22** - V3 processor development
- **2025-11-23** - Telegram fetcher, orchestrator
- **2025-11-25** - QA validation agent
- **2025-11-27** - Liquidity metrics schema enhancement
- **2025-11-28** - GPT-5/Claude 4.5 models, parallel processing
- **2025-11-29** - Source tracking, QA sampling integration, GPT-5 primary model
- **2025-11-30** - Embedding workflow, Pinecone integration, source entity normalization

---

## Known Limitations

1. GPT-5 is slower and more expensive than Claude Sonnet (~4x cost, ~2x time)
2. No incremental updates (re-fetches full date range)
3. No keyword search (Telethon supports it)
4. Metrics dictionary can accumulate duplicate metric names (needs cleaner for metrics, not sources)
5. Parallel processing requires ThreadPoolExecutor workaround in async context
