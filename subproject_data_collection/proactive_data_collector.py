"""
CBOE Put-Call Ratio Data Collector

Downloads historical put-call ratio data from CBOE:
1. Archive CSVs (2003-2019) from cdn.cboe.com — equity + total P/C only
2. Daily JSON API (2019-10-07 to present) — all ratios + volume/OI for 6 main categories
3. Merges into single unified CSV (extra columns empty for archive rows)

Usage:
    python subproject_data_collection/proactive_data_collector.py
    python subproject_data_collection/proactive_data_collector.py --daily-only
    python subproject_data_collection/proactive_data_collector.py --merge-only
"""

import argparse
import csv
import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "cboe_raw"
OUTPUT_CSV = DATA_DIR / "cboe_put_call_ratio.csv"
CSV_SERIES_DIR = DATA_DIR / "csv_series"
PROGRESS_FILE = RAW_DIR / "daily_progress.json"
DAILY_CSV = RAW_DIR / "cboe_daily_2019_2026.csv"

ARCHIVE_URLS = {
    "equitypcarchive.csv": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypcarchive.csv",
    "equitypc.csv": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv",
    "totalpc.csv": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv",
    "totalpcarchive.csv": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpcarchive.csv",
}

DAILY_API_BASE = "https://cdn.cboe.com/data/us/options/market_statistics/daily"
DAILY_MIN_DATE = datetime(2019, 10, 7)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.cboe.com",
    "referer": "https://www.cboe.com/",
}

# ── Column mappings for daily API ──────────────────────────────────────────

# Maps JSON ratio names → CSV column names
RATIO_MAP = {
    "EQUITY PUT/CALL RATIO": "equity_pc_ratio",
    "TOTAL PUT/CALL RATIO": "total_pc_ratio",
    "INDEX PUT/CALL RATIO": "index_pc_ratio",
    "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO": "etp_pc_ratio",
    "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO": "vix_pc_ratio",
    "SPX + SPXW PUT/CALL RATIO": "spx_pc_ratio",
    "OEX PUT/CALL RATIO": "oex_pc_ratio",
    "MRUT PUT/CALL RATIO": "mrut_pc_ratio",
    "MXEA PUT/CALL RATIO": "mxea_pc_ratio",
    "MXEF PUT/CALL RATIO": "mxef_pc_ratio",
    "MXACW PUT/CALL RATIO": "mxacw_pc_ratio",
    "MXWLD PUT/CALL RATIO": "mxwld_pc_ratio",
    "MXUSA PUT/CALL RATIO": "mxusa_pc_ratio",
    "CBTX PUT/CALL RATIO": "cbtx_pc_ratio",
    "MBTX PUT/CALL RATIO": "mbtx_pc_ratio",
    "SPEQX PUT/CALL RATIO": "speqx_pc_ratio",
    "SPEQW PUT/CALL RATIO": "speqw_pc_ratio",
    "MGTN PUT/CALL RATIO": "mgtn_pc_ratio",
    "MGTNW PUT/CALL RATIO": "mgtnw_pc_ratio",
}

# Maps JSON section names → CSV column prefix. Volume/OI extracted for these.
VOLUME_SECTIONS = {
    "EQUITY OPTIONS": "equity",
    "SUM OF ALL PRODUCTS": "total",
    "INDEX OPTIONS": "index",
    "EXCHANGE TRADED PRODUCTS": "etp",
    "CBOE VOLATILITY INDEX (VIX)": "vix",
    "SPX + SPXW": "spx",
}

# ── Fieldnames ─────────────────────────────────────────────────────────────

# Stable column order for the merged CSV
_ratio_cols = list(dict.fromkeys(RATIO_MAP.values()))  # preserves insertion order
_vol_oi_cols = []
for prefix in VOLUME_SECTIONS.values():
    _vol_oi_cols += [f"{prefix}_call", f"{prefix}_put", f"{prefix}_total",
                     f"{prefix}_oi_call", f"{prefix}_oi_put", f"{prefix}_oi_total"]

ALL_FIELDNAMES = ["date"] + _ratio_cols + _vol_oi_cols + ["source"]

# Daily CSV has same columns minus "source"
DAILY_FIELDNAMES = [c for c in ALL_FIELDNAMES if c != "source"]


# ── Step 1: Download archive CSVs ──────────────────────────────────────────


def download_archives():
    """Download archive CSV files from cdn.cboe.com."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in ARCHIVE_URLS.items():
        dest = RAW_DIR / filename
        if dest.exists():
            print(f"  [skip] {filename} already exists ({dest.stat().st_size:,} bytes)")
            continue
        print(f"  [download] {filename} from {url}")
        try:
            req = Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            dest.write_bytes(data)
            print(f"  [ok] {filename} ({len(data):,} bytes)")
        except (HTTPError, URLError) as e:
            print(f"  [error] {filename}: {e}")
        time.sleep(1)


# ── Step 2: Scrape daily JSON API ──────────────────────────────────────────


def _load_progress():
    """Load scrape progress (set of dates already fetched)."""
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text())
        return set(data.get("fetched_dates", []))
    return set()


def _save_progress(fetched: set):
    PROGRESS_FILE.write_text(json.dumps({"fetched_dates": sorted(fetched)}, indent=0))


def _fetch_daily(date_str: str) -> dict | None:
    """Fetch one day from the CBOE daily API. Returns parsed row or None."""
    url = f"{DAILY_API_BASE}/{date_str}_daily_options"
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        if e.code in (404, 403):
            return None  # weekend / holiday / not yet published
        raise
    except (URLError, json.JSONDecodeError):
        return None

    row = {"date": date_str}

    # Extract all ratios
    ratios = {r["name"]: r["value"] for r in data.get("ratios", [])}
    for json_name, col_name in RATIO_MAP.items():
        row[col_name] = ratios.get(json_name, "")

    # Extract volume + OI for main sections
    for json_section, prefix in VOLUME_SECTIONS.items():
        entries = data.get(json_section, [])
        vol = next((r for r in entries if r.get("name") == "VOLUME"), {})
        oi = next((r for r in entries if r.get("name") == "OPEN INTEREST"), {})
        row[f"{prefix}_call"] = vol.get("call", "")
        row[f"{prefix}_put"] = vol.get("put", "")
        row[f"{prefix}_total"] = vol.get("total", "")
        row[f"{prefix}_oi_call"] = oi.get("call", "")
        row[f"{prefix}_oi_put"] = oi.get("put", "")
        row[f"{prefix}_oi_total"] = oi.get("total", "")

    return row


def scrape_daily():
    """Scrape daily API from today back to 2019-10-07."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched = _load_progress()
    print(f"  [resume] {len(fetched)} dates already fetched")

    # Load existing rows from CSV if present (only if columns match)
    existing_rows = []
    if DAILY_CSV.exists():
        with open(DAILY_CSV, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and set(DAILY_FIELDNAMES).issubset(set(reader.fieldnames)):
                existing_rows = list(reader)
            else:
                print("  [reset] Daily CSV has old schema, will re-fetch all dates")
                fetched = set()

    today = datetime.now().date()
    current = today
    min_date = DAILY_MIN_DATE.date()
    new_rows = []
    consecutive_errors = 0

    while current >= min_date:
        date_str = current.strftime("%Y-%m-%d")

        # Skip weekends (Sat=5, Sun=6)
        if current.weekday() >= 5:
            current -= timedelta(days=1)
            continue
        current -= timedelta(days=1)

        if date_str in fetched:
            continue

        try:
            row = _fetch_daily(date_str)
        except HTTPError as e:
            if e.code == 429:
                # Rate limited — exponential backoff
                for wait in [30, 60, 120]:
                    print(f"  [429] Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    try:
                        row = _fetch_daily(date_str)
                        break
                    except HTTPError:
                        continue
                else:
                    print("  [abort] Persistent rate limiting. Saving progress.")
                    break
            else:
                print(f"  [error] {date_str}: HTTP {e.code}")
                consecutive_errors += 1
                if consecutive_errors > 10:
                    print("  [abort] Too many consecutive errors.")
                    break
                continue

        if row is not None:
            new_rows.append(row)
            fetched.add(date_str)
            consecutive_errors = 0
            if len(new_rows) % 50 == 0:
                print(f"  [progress] {len(new_rows)} new rows fetched (at {date_str})")
                _save_progress(fetched)
        else:
            # 404 / holiday — still mark as fetched to skip next time
            fetched.add(date_str)

        # Anti-bot delay
        delay = random.uniform(1.0, 2.0)
        time.sleep(delay)

    # Write all rows (existing + new) to CSV
    all_rows = existing_rows + new_rows
    if all_rows:
        with open(DAILY_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DAILY_FIELDNAMES)
            writer.writeheader()
            for r in sorted(all_rows, key=lambda x: x["date"]):
                writer.writerow({k: r.get(k, "") for k in DAILY_FIELDNAMES})
        print(f"  [saved] {DAILY_CSV} ({len(all_rows)} rows)")

    _save_progress(fetched)
    print(f"  [done] {len(new_rows)} new rows fetched, {len(fetched)} total dates processed")


# ── Step 3: Merge into single CSV ─────────────────────────────────────────


def _parse_date(raw: str) -> str:
    """Normalize M/D/YYYY or MM/DD/YYYY to YYYY-MM-DD."""
    raw = raw.strip()
    if not raw:
        return ""
    # Already YYYY-MM-DD
    if len(raw) == 10 and raw[4] == "-":
        return raw
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _safe_float(val: str) -> str:
    """Return val as string if parseable as float, else empty."""
    try:
        float(val.replace(",", ""))
        return val.replace(",", "")
    except (ValueError, AttributeError):
        return ""


def _find_header_line(path: Path) -> int:
    """Find the CSV header line (skip disclaimer rows at top)."""
    with open(path, newline="", encoding="latin-1") as f:
        for i, line in enumerate(f):
            lower = line.lower().strip()
            # Header row contains "date" and either "call" or "ratio"
            if ("date" in lower or "trade_date" in lower) and ("call" in lower or "ratio" in lower):
                return i
    return 0


def _read_archive_equity(filename: str) -> list[dict]:
    """Read an equity archive CSV with varying column names."""
    path = RAW_DIR / filename
    if not path.exists():
        print(f"  [skip] {filename} not found")
        return []
    header_line = _find_header_line(path)
    rows = []
    with open(path, newline="", encoding="latin-1") as f:
        # Skip lines before the header
        for _ in range(header_line):
            next(f)
        reader = csv.DictReader(f)
        for raw_row in reader:
            # Normalize keys to lowercase for matching
            row = {k.strip().lower(): v.strip() for k, v in raw_row.items()}
            date_key = next((k for k in row if "date" in k), None)
            if not date_key:
                continue
            date = _parse_date(row[date_key])
            if not date:
                continue
            # Find call/put/total/ratio columns
            call_key = next((k for k in row if "call" in k and "ratio" not in k), None)
            put_key = next((k for k in row if "put" in k and "ratio" not in k), None)
            total_key = next((k for k in row if "total" in k), None)
            ratio_key = next((k for k in row if "ratio" in k), None)
            rows.append({
                "date": date,
                "equity_call": _safe_float(row.get(call_key, "")) if call_key else "",
                "equity_put": _safe_float(row.get(put_key, "")) if put_key else "",
                "equity_total": _safe_float(row.get(total_key, "")) if total_key else "",
                "equity_pc_ratio": _safe_float(row.get(ratio_key, "")) if ratio_key else "",
                "source": "archive",
            })
    print(f"  [read] {filename}: {len(rows)} rows")
    return rows


def _read_archive_total(filename: str) -> dict[str, dict]:
    """Read a total archive CSV, return dict keyed by date."""
    path = RAW_DIR / filename
    if not path.exists():
        print(f"  [skip] {filename} not found")
        return {}
    header_line = _find_header_line(path)
    by_date = {}
    with open(path, newline="", encoding="latin-1") as f:
        for _ in range(header_line):
            next(f)
        reader = csv.DictReader(f)
        for raw_row in reader:
            row = {k.strip().lower(): v.strip() for k, v in raw_row.items()}
            date_key = next((k for k in row if "date" in k), None)
            if not date_key:
                continue
            date = _parse_date(row[date_key])
            if not date:
                continue
            call_key = next((k for k in row if "call" in k and "ratio" not in k), None)
            put_key = next((k for k in row if "put" in k and "ratio" not in k), None)
            total_key = next((k for k in row if "total" in k), None)
            ratio_key = next((k for k in row if "ratio" in k), None)
            by_date[date] = {
                "total_call": _safe_float(row.get(call_key, "")) if call_key else "",
                "total_put": _safe_float(row.get(put_key, "")) if put_key else "",
                "total_total": _safe_float(row.get(total_key, "")) if total_key else "",
                "total_pc_ratio": _safe_float(row.get(ratio_key, "")) if ratio_key else "",
            }
    print(f"  [read] {filename}: {len(by_date)} rows")
    return by_date


def _read_daily_csv() -> list[dict]:
    """Read the scraped daily CSV."""
    if not DAILY_CSV.exists():
        print("  [skip] daily CSV not found")
        return []
    rows = []
    with open(DAILY_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["source"] = "daily_api"
            rows.append(row)
    print(f"  [read] daily CSV: {len(rows)} rows")
    return rows


def merge():
    """Merge archive + daily data into single output CSV."""
    # Read equity archives
    equity_rows = _read_archive_equity("equitypcarchive.csv")
    equity_rows += _read_archive_equity("equitypc.csv")

    # Read total archives (keyed by date for joining)
    total_data = _read_archive_total("totalpcarchive.csv")
    total_data.update(_read_archive_total("totalpc.csv"))

    # Join total data into equity rows
    for row in equity_rows:
        t = total_data.get(row["date"], {})
        row["total_call"] = t.get("total_call", "")
        row["total_put"] = t.get("total_put", "")
        row["total_total"] = t.get("total_total", "")
        row["total_pc_ratio"] = t.get("total_pc_ratio", "")

    # Read daily
    daily_rows = _read_daily_csv()

    # Combine and dedup (daily_api wins over archive for overlapping dates)
    by_date = {}
    for row in equity_rows:
        by_date[row["date"]] = row
    for row in daily_rows:
        by_date[row["date"]] = row  # overwrites archive

    # Also add total-only dates that don't have equity data
    for date, t in total_data.items():
        if date not in by_date:
            by_date[date] = {"date": date, "source": "archive", **t}

    # Sort and write
    sorted_rows = sorted(by_date.values(), key=lambda x: x["date"])

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_FIELDNAMES)
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow({k: row.get(k, "") for k in ALL_FIELDNAMES})

    # Summary stats
    dates = [r["date"] for r in sorted_rows]
    eq_ratios = [float(r["equity_pc_ratio"]) for r in sorted_rows
                 if r.get("equity_pc_ratio")]
    daily_count = sum(1 for r in sorted_rows if r.get("source") == "daily_api")
    print(f"  [merged] {OUTPUT_CSV}")
    print(f"  [stats] {len(sorted_rows)} total rows ({len(sorted_rows) - daily_count} archive, {daily_count} daily_api)")
    print(f"  [stats] {len(ALL_FIELDNAMES)} columns")
    print(f"  [stats] Date range: {dates[0]} to {dates[-1]}")
    if eq_ratios:
        print(f"  [stats] Equity P/C ratio: min={min(eq_ratios):.2f}, max={max(eq_ratios):.2f}, "
              f"mean={sum(eq_ratios)/len(eq_ratios):.2f}")

    # Detect gap
    prev = None
    for d in dates:
        if prev:
            dt = datetime.strptime(d, "%Y-%m-%d")
            dt_prev = datetime.strptime(prev, "%Y-%m-%d")
            gap = (dt - dt_prev).days
            if gap > 30:
                print(f"  [gap] {prev} to {d} ({gap} days)")
        prev = d


# ── Step 4: Export long-form CSV per column ────────────────────────────────


def export_long_form():
    """Export wide CSV into normalized date,value files (one per data column).

    Reads OUTPUT_CSV and writes one CSV per non-empty data column to
    CSV_SERIES_DIR. Rows where the value is empty are skipped.
    """
    if not OUTPUT_CSV.exists():
        print(f"  [error] Wide CSV not found: {OUTPUT_CSV}")
        print("  [hint] Run without --export-only first to scrape and merge data")
        return

    CSV_SERIES_DIR.mkdir(parents=True, exist_ok=True)

    # Data columns = everything except "date" and "source"
    data_columns = [c for c in ALL_FIELDNAMES if c not in ("date", "source")]

    rows = []
    with open(OUTPUT_CSV, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    exported = 0
    for col in data_columns:
        # Collect non-empty (date, value) pairs
        pairs = []
        for row in rows:
            val = row.get(col, "").strip()
            if val:
                pairs.append((row["date"], val))

        if not pairs:
            continue

        out_path = CSV_SERIES_DIR / f"{col}.csv"
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "value"])
            for date, value in pairs:
                writer.writerow([date, value])

        exported += 1
        print(f"  [export] {col}.csv ({len(pairs)} rows)")

    print(f"  [done] Exported {exported} series to {CSV_SERIES_DIR}")


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="CBOE Put-Call Ratio Data Collector")
    parser.add_argument("--daily-only", action="store_true", help="Skip archive download, only scrape daily API")
    parser.add_argument("--merge-only", action="store_true", help="Only merge existing data files")
    parser.add_argument("--export-only", action="store_true", help="Re-export long-form CSVs from existing wide CSV")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.export_only:
        print("[export] Exporting long-form CSVs from wide CSV...")
        export_long_form()
        return

    if args.merge_only:
        print("[merge] Merging existing data...")
        merge()
        print("[step 4] Exporting long-form CSVs...")
        export_long_form()
        return

    if not args.daily_only:
        print("[step 1] Downloading archive CSVs...")
        download_archives()

    print("[step 2] Scraping daily API...")
    scrape_daily()

    print("[step 3] Merging all data...")
    merge()

    print("[step 4] Exporting long-form CSVs...")
    export_long_form()

    print("[done] Output: " + str(OUTPUT_CSV))


if __name__ == "__main__":
    main()
