"""
FRED-MD Monthly Dataset Collector

Downloads the FRED-MD dataset (McCracken & Ng, 2016) from St. Louis Fed,
extracts specified series, and exports to csv_series/ in date,value format.

Source: https://files.stlouisfed.org/files/htdocs/fred-md/monthly/current.csv

The FRED-MD dataset contains ~130 monthly macroeconomic indicators going back
to 1959. We extract specific series (e.g., NAPM = ISM PMI) that aren't
available via the FRED API (ISM pulled from FRED in 2016).

Usage:
    python subproject_data_collection/fred_md_collector.py                # download + extract
    python subproject_data_collection/fred_md_collector.py --extract-only # re-extract from cached CSV
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "fred_md_raw"
RAW_CSV = RAW_DIR / "current.csv"
CSV_SERIES_DIR = DATA_DIR / "csv_series"

# Primary URL (S3-backed, may require browser-like session)
FRED_MD_URL = "https://files.stlouisfed.org/files/htdocs/fred-md/monthly/current.csv"

# Fallback: dated CSV from stlouisfed.org media server
# Format: https://www.stlouisfed.org/-/media/project/frbstl/stlouisfed/research/fred-md/monthly/YYYY-MM-md.csv
FRED_MD_URL_TEMPLATE = "https://www.stlouisfed.org/-/media/project/frbstl/stlouisfed/research/fred-md/monthly/{year}-{month:02d}-md.csv"

# Series to extract from FRED-MD.
# Key = output filename (without .csv), Value = column name in FRED-MD CSV.
SERIES_TO_EXTRACT = {
    "napm": "NAPM",                    # ISM PMI (Manufacturing)
    "napm_new_orders": "AMDMNOx",      # ISM New Orders (mfg)
    "capacity_util": "CUMFNS",         # Capacity Utilization
    "ind_production": "INDPRO",        # Industrial Production Index
    "housing_starts": "HOUST",         # Housing Starts
    "consumer_expect": "UMCSENTx",     # U Michigan Consumer Sentiment
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}


def download_fred_md():
    """Download FRED-MD current.csv from St. Louis Fed.

    Tries primary URL first, then dated fallback URLs.
    The St. Louis Fed has bot protection, so automated downloads may fail.
    If all attempts fail, download manually from:
      https://www.stlouisfed.org/research/economists/mccracken/fred-databases
    and save as: {RAW_CSV}
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    urls_to_try = [FRED_MD_URL]
    # Add dated fallback URLs (current month and previous month)
    now = datetime.now()
    for month_offset in [0, -1, -2]:
        month = now.month + month_offset
        year = now.year
        while month < 1:
            month += 12
            year -= 1
        urls_to_try.append(FRED_MD_URL_TEMPLATE.format(year=year, month=month))

    for url in urls_to_try:
        print(f"  [try] {url}")
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
            # Verify it's CSV, not an error page
            text = data.decode("utf-8", errors="replace")
            if "sasdate" in text.lower() or "NAPM" in text:
                RAW_CSV.write_bytes(data)
                print(f"  [ok] {RAW_CSV} ({len(data):,} bytes)")
                return True
            else:
                print(f"  [skip] Response is not FRED-MD CSV ({len(data)} bytes)")
        except (HTTPError, URLError) as e:
            print(f"  [error] {e}")

    print(f"  [failed] All download attempts failed.")
    print(f"  [hint] Download manually from:")
    print(f"    https://www.stlouisfed.org/research/economists/mccracken/fred-databases")
    print(f"  Save as: {RAW_CSV}")
    print(f"  Then run: python {__file__} --extract-only")
    return False


def _parse_sasdate(date_str: str) -> str:
    """Parse FRED-MD sasdate format (M/D/YYYY) to YYYY-MM-DD."""
    date_str = date_str.strip()
    if not date_str:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def extract_series():
    """Extract configured series from cached FRED-MD CSV to csv_series/."""
    if not RAW_CSV.exists():
        print(f"  [error] Raw CSV not found: {RAW_CSV}")
        print("  [hint] Run without --extract-only first to download")
        return

    CSV_SERIES_DIR.mkdir(parents=True, exist_ok=True)

    # Read raw CSV
    # Structure: row 0 = series names (header), row 1 = transformation codes, rows 2+ = data
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # Series names
        transform_codes = next(reader)  # Transformation codes (skip)
        data_rows = list(reader)

    # Normalize header (strip whitespace)
    header = [h.strip() for h in header]

    # Find date column (usually "sasdate")
    date_col = None
    for i, h in enumerate(header):
        if h.lower() in ("sasdate", "date"):
            date_col = i
            break

    if date_col is None:
        print("  [error] Cannot find date column in FRED-MD CSV")
        return

    print(f"  [info] FRED-MD: {len(header)} columns, {len(data_rows)} data rows")

    extracted = 0
    for output_name, col_name in SERIES_TO_EXTRACT.items():
        if col_name not in header:
            print(f"  [skip] {col_name} not found in FRED-MD columns")
            continue

        col_idx = header.index(col_name)

        # Extract (date, value) pairs, skipping empty/NA
        pairs = []
        for row in data_rows:
            if len(row) <= max(date_col, col_idx):
                continue
            date = _parse_sasdate(row[date_col])
            val = row[col_idx].strip()
            if not date or not val or val.upper() == "NA":
                continue
            try:
                float(val)
                pairs.append((date, val))
            except ValueError:
                continue

        if not pairs:
            print(f"  [skip] {col_name}: no valid data points")
            continue

        # Write to csv_series/
        out_path = CSV_SERIES_DIR / f"{output_name}.csv"
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "value"])
            for date, value in pairs:
                writer.writerow([date, value])

        extracted += 1
        print(f"  [export] {output_name}.csv ({len(pairs)} rows, "
              f"{pairs[0][0]} to {pairs[-1][0]})")

    print(f"  [done] Extracted {extracted} series to {CSV_SERIES_DIR}")


def main():
    parser = argparse.ArgumentParser(description="FRED-MD Monthly Dataset Collector")
    parser.add_argument("--extract-only", action="store_true",
                        help="Re-extract from cached CSV without downloading")
    args = parser.parse_args()

    if args.extract_only:
        print("[extract] Extracting series from cached FRED-MD CSV...")
        extract_series()
        return

    print("[step 1] Downloading FRED-MD dataset...")
    if download_fred_md():
        print("[step 2] Extracting series...")
        extract_series()

    print("[done]")


if __name__ == "__main__":
    main()
