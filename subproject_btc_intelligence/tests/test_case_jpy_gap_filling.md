# Test Case: JPY Rally Gap Filling

## Query
```
On 2026-01-24, JPY/USD rallied to 155.90 rising 1.6% daily, and Japan finance minister warned speculators. What is the BTC impact?
```

## Run Command
```bash
python -m subproject_btc_intelligence "On 2026-01-24, JPY/USD rallied to 155.90 rising 1.6% daily, and Japan finance minister warned speculators. What is the BTC impact?"
```

## Gap Detection Results (5 gaps detected)

| Gap | fill_method | Search Query / Instruments | Result |
|-----|------------|---------------------------|--------|
| historical_precedent_depth | web_search | "BOJ rate hike announcement dates March 2024 January 2025" | FILLED (0.85) - Found March 19, 2024 and July 31, 2024 hike dates |
| quantified_relationships | data_fetch | instruments: [btc, usdjpy, sofr, dxy, sp500, vix] | FILLED (0.90) - Computed BTC vs USDJPY correlation = -0.1748 |
| monitoring_thresholds | web_search | "analyst USD JPY intervention threshold forecast 2026" | FILLED (0.72) - Found 145/150/160 thresholds, 20-31% BTC drawdown per hike |
| event_calendar | web_search | "BOJ monetary policy meeting schedule 2026 FOMC dates" | PARTIALLY_FILLED - Found full FOMC 2026 schedule, missed BOJ dates |
| exit_criteria | web_search | "yen stabilization level after BOJ intervention historical precedent" | UNFILLABLE - Genuinely hard to find in public web content |

## Key Improvements Validated

1. **data_fetch routing**: quantified_relationships skipped web search, computed correlation in-house
2. **Query optimization**: historical_precedent queries ask for DATES not "Bitcoin price impact"
3. **Tavily backend**: Returns Bloomberg/Yahoo Finance/Reuters (vs DDGS returning "Baekjoon Online Judge")
4. **Refinement drift fixed**: Extraction prompt now instructs "ask for raw facts, not derived analysis"

## Evolution Across 3 Runs

| Gap | Run 1 (DDGS) | Run 2 (Tavily, old prompt) | Run 3 (Tavily, optimized prompt) |
|-----|-------------|--------------------------|--------------------------------|
| quantified_relationships | UNFILLABLE | FILLED (web search) | FILLED (data_fetch, computed) |
| historical_precedent_depth | UNFILLABLE | PARTIALLY_FILLED | FILLED (0.85) |
| monitoring_thresholds | UNFILLABLE | PARTIALLY_FILLED | FILLED (0.72) |
| event_calendar | UNFILLABLE | FILLED | PARTIALLY_FILLED |
| exit_criteria | UNFILLABLE | UNFILLABLE | UNFILLABLE |
