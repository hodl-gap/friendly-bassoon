# CBOE Put-Call Ratio Data Collection: Discovery & Build Process

## Origin: Case 5 Pipeline Gap

Case 5 (put-call ratio extreme) revealed that the pipeline had no access to CBOE equity put-call ratio (CPCE) data. The pipeline used VIX as a proxy, but VIX measures implied volatility, not directional sentiment. The case rubric expected actual put-call ratio analysis. FRED has zero put-call ratio series (only VIX/volatility indices), and Yahoo Finance doesn't carry CPCE either.

## Step 1: Finding the Data Source

### CBOE website inspection

Navigated to `cboe.com` and found the Market Statistics page at `https://www.cboe.com/us/options/market_statistics/daily/`. This page shows today's put-call ratios — a table with 19 different ratios (equity, total, index, ETP, VIX, SPX, etc.) plus volume and open interest breakdowns for each product category.

### Discovering the daily JSON API

Using Chrome DevTools Network panel on the CBOE page, intercepted the XHR request the page makes:

```
GET https://cdn.cboe.com/data/us/options/market_statistics/daily/2026-02-24_daily_options
```

Response: JSON with `ratios` array (19 put-call ratios) + volume/OI sections for every product. No authentication required — served via CloudFront CDN. Requires `x-requested-with: XMLHttpRequest` and `origin: https://www.cboe.com` headers.

### Discovering the date range

Inspecting the page's JavaScript config (`window.CTX`) found `minDate: "2019-10-07"`. Tested: dates before 2019-10-07 return 404. The daily API covers 2019-10-07 to present.

### Finding historical archive CSVs

Searched the CBOE website for historical data downloads. Found the Options Volume & Put/Call Ratios page linking to static CSV files on `cdn.cboe.com/resources/options/volume_and_call_put_ratios/`:

| File | Date Range | Content |
|------|-----------|---------|
| `equitypcarchive.csv` | 2003-10-17 to 2012-06-07 | Equity P/C ratio + volume |
| `equitypc.csv` | 2006-11-01 to 2019-10-04 | Equity P/C ratio + volume |
| `totalpcarchive.csv` | 2003-10-17 to 2012-06-07 | Total P/C ratio + volume |
| `totalpc.csv` | 2006-11-01 to 2019-10-04 | Total P/C ratio + volume |

### Gap analysis

Initial assumption: archive CSVs end in 2016, daily API starts in 2019 = 3-year gap. **Turned out to be wrong.** `equitypc.csv` actually extends to 2019-10-04 (Friday). Daily API starts 2019-10-07 (Monday). The data is seamless — the "gap" is a weekend.

### Alternative source research

Searched for other free sources of CPCE data as fallback:
- **FRED**: Zero put-call ratio data. Only volatility indices (VIX, VXNCLS, etc.)
- **Quandl/Nasdaq Data Link**: No confirmed CPCE dataset
- **Barchart**: Has $CPCE but free tier limits to 1 CSV download/day
- **StockCharts, YCharts, MacroMicro, TradingView**: All require paid subscriptions for data export
- **Python packages**: No package provides CPCE. The `trading-with-python` library downloads the same CBOE CSV

**Conclusion**: CBOE's own CDN files are the best (and only) free programmatic source.

## Step 2: Building the Scraper

### Archive CSV challenges

The archive CSVs had two issues that weren't obvious upfront:

1. **Disclaimer rows at top**: Each file starts with 1-2 lines of legal disclaimer before the actual CSV header. Had to auto-detect the header row by searching for lines containing both "date" and "call"/"ratio".

2. **Encoding**: `equitypcarchive.csv` uses Latin-1 encoding (non-breaking space `\xa0` in disclaimer text), not UTF-8. Standard `csv.DictReader` with UTF-8 encoding crashes.

3. **Inconsistent column names across files**:
   - `equitypcarchive.csv`: `Date`, `Equity Call Volume`, `Equity Put Volume`
   - `equitypc.csv`: `DATE`, `CALL`, `PUT`
   - `totalpc.csv`: `DATE`, `CALLS`, `PUTS` (plural!)
   - `totalpcarchive.csv`: `Trade_date`, `Call`, `Put`

   Solution: lowercase all column names, match by substring ("call" in key, "put" in key, etc.)

4. **Date format**: `M/D/YYYY` (e.g., `11/1/2006` not `11/01/2006`). Normalized to YYYY-MM-DD.

### Daily API scraping

- Iterate backwards from today to 2019-10-07
- Skip weekends (Saturday/Sunday) to avoid unnecessary requests
- 403 and 404 both mean "no data" (403 = today not yet published, or weekend; 404 = holiday)
- 1-2 second random delay between requests (anti-bot courtesy)
- Progress saved to JSON after every 50 rows — scraper resumes from where it left off on restart
- ~1,600 trading days = ~40 minutes at 1.5s average delay

### Initial bug: 403 handling

First run failed immediately: the scraper hit 403 on today's date (data not yet published for the current day) and treated it as "anti-bot block", aborting. Fix: treat 403 same as 404 (skip). True rate limiting would be 429.

### Data expansion

The initial implementation only captured equity_pc_ratio and total_pc_ratio (matching archive columns). Later expanded to capture all 19 ratios + volume/OI for 6 main product categories from the daily API. This required re-scraping all daily data (another 40 min).

## Step 3: Merging

1. Read equity archive CSVs → list of rows with equity_call, equity_put, equity_total, equity_pc_ratio
2. Read total archive CSVs → dict keyed by date with total_call, total_put, total_total, total_pc_ratio
3. Join total data into equity rows by date
4. Read daily CSV → rows with all 56 data columns
5. Combine: for overlapping dates, daily_api rows overwrite archive rows
6. Sort by date, write to unified CSV

## Final Dataset

**File**: `subproject_data_collection/data/cboe_put_call_ratio.csv`

| Metric | Value |
|--------|-------|
| Total rows | 5,622 |
| Date range | 2003-10-17 to 2026-02-24 |
| Columns | 57 |
| Archive rows | 4,018 (10 columns populated) |
| Daily API rows | 1,604 (all 57 columns populated) |
| Equity P/C ratio range | 0.00 – 2.40 |
| Equity P/C ratio mean | 0.63 |
| Data gaps | None (archive ends Fri 2019-10-04, daily starts Mon 2019-10-07) |

### Column categories

| Category | Columns | Available from |
|----------|---------|---------------|
| Equity P/C ratio + volume | 4 | 2003 (archive) |
| Total P/C ratio + volume | 4 | 2003 (archive) |
| Other 17 P/C ratios (index, ETP, VIX, SPX, etc.) | 17 | 2019 (daily API) |
| Volume breakdown (index, ETP, VIX, SPX) | 12 | 2019 (daily API) |
| Open interest (all 6 categories) | 18 | 2019 (daily API) |

### Updating

Run `python subproject_data_collection/proactive_data_collector.py --daily-only` to fetch new days. The scraper automatically skips already-fetched dates via `daily_progress.json`.

## Step 4: Long-Form Export (`csv_series/`)

The wide CSV (57 columns) is useful for archival but not compatible with the pipeline's adapters, which expect a single `(date, value)` series per variable. The `export_long_form()` step splits the wide CSV into one file per data column.

### Output

**Directory**: `subproject_data_collection/data/csv_series/`

Each file is named `{column_name}.csv` with two columns: `date,value`. Rows where the value is empty in the wide CSV are skipped. Example files:

| File | Rows | Date range |
|------|------|-----------|
| `equity_pc_ratio.csv` | ~5600 | 2003-2026 |
| `total_pc_ratio.csv` | ~5600 | 2003-2026 |
| `index_pc_ratio.csv` | ~1600 | 2019-2026 |
| `spx_oi_total.csv` | ~1600 | 2019-2026 |
| ...one file per non-empty column | | |

### Usage

```bash
# Re-export from existing wide CSV (no scraping)
python subproject_data_collection/proactive_data_collector.py --export-only

# Full pipeline: scrape + merge + export
python subproject_data_collection/proactive_data_collector.py
```

### Pipeline Integration

The `CSVAdapter` in `adapters/csv_adapter.py` reads these files. To make a CSV series available to the pipeline:

1. Place a `date,value` CSV in `data/csv_series/{series_id}.csv`
2. Add an entry to `shared/data/anchor_variables.json` with `"source": "CSV"` and `"series_id": "{series_id}"`
3. The variable resolver, data grounding agent, and data fetching module all route `CSV` source to the adapter automatically

This is a one-time pattern: future scraped datasets just need to output `date,value` CSVs to `csv_series/` and add an anchor variable entry. No new adapter code per dataset.
