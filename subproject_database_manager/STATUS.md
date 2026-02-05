# Database Manager - Status

**Last Updated**: 2026-02-05

## Current State: Production-Ready

Full session history archived in `archive/STATUS_database_manager.md`.

## TODO

### High Priority
- [ ] Benchmark parallel vs sequential processing (compare Step 4 times, find optimal `MAX_CONCURRENT_REQUESTS`)
- [ ] Add missing metrics to `liquidity_metrics_mapping.csv`: `fed_funds_rate`, `yield_curve_2y10y`

### Medium Priority
- [ ] Add categorization for `individual_stock_research` (company/stock-specific research messages)
- [ ] Add keyword search support (Telethon supports keyword filtering)

### Low Priority
- [ ] Handle billing quota limits (rate limiting / backoff)
- [ ] Blocking QA mode (halt pipeline on low QA scores)
- [ ] Auto-fix mode for QA (LLM suggests fixes → apply → re-validate)
- [ ] Quality metrics dashboard (track QA scores over time)

## Known Limitations
1. GPT-5 Mini may have lower extraction quality than GPT-5 (cost tradeoff)
2. No keyword search (Telethon supports it)
3. Parallel processing requires ThreadPoolExecutor workaround in async context
