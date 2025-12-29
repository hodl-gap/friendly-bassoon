#!/usr/bin/env python3
"""
Fetch historical S&P 500 constituents from Wikipedia
Reconstructs monthly constituent lists from 2020-01-01 to 2025-01-01
"""

import json
import requests
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def fetch_wikipedia_page(url, headers):
    """Fetch Wikipedia page with proper User-Agent header"""
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def parse_current_constituents(html_content):
    """Parse current S&P 500 constituents from table[0]"""
    tables = pd.read_html(html_content)
    current_df = tables[0]
    return set(current_df['Symbol'].tolist())

def parse_changes_table(html_content):
    """Parse historical changes from table[1]"""
    tables = pd.read_html(html_content)
    changes_df = tables[1]

    # Handle MultiIndex columns by flattening
    if isinstance(changes_df.columns, pd.MultiIndex):
        changes_df.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in changes_df.columns.values]

    # Strip whitespace from column names
    changes_df.columns = [col.strip() if isinstance(col, str) else col for col in changes_df.columns]

    # Find the date column (it might have different names)
    date_col = None
    for col in changes_df.columns:
        if 'Date' in str(col) or 'date' in str(col).lower():
            date_col = col
            break

    if date_col is None:
        # Use first column as date
        date_col = changes_df.columns[0]

    # Parse dates
    changes_df['Date'] = pd.to_datetime(changes_df[date_col], errors='coerce')

    # Find Added and Removed columns
    added_col = None
    removed_col = None

    for col in changes_df.columns:
        col_str = str(col).lower()
        if 'added' in col_str and 'ticker' in col_str:
            added_col = col
        elif 'added' in col_str and added_col is None:
            added_col = col
        elif 'removed' in col_str and 'ticker' in col_str:
            removed_col = col
        elif 'removed' in col_str and removed_col is None:
            removed_col = col

    # Extract tickers (handle multi-ticker additions/removals)
    if added_col and added_col in changes_df.columns:
        changes_df['Added.Ticker'] = changes_df[added_col].apply(
            lambda x: x.split('(')[0].strip() if pd.notna(x) and str(x).strip() else None
        )
    else:
        changes_df['Added.Ticker'] = None

    if removed_col and removed_col in changes_df.columns:
        changes_df['Removed.Ticker'] = changes_df[removed_col].apply(
            lambda x: x.split('(')[0].strip() if pd.notna(x) and str(x).strip() else None
        )
    else:
        changes_df['Removed.Ticker'] = None

    # Filter out rows without valid dates
    changes_df = changes_df[changes_df['Date'].notna()].copy()

    return changes_df

def reconstruct_backwards(current_tickers, changes_df, start_date, end_date):
    """
    Reconstruct historical constituents by going backwards from current list.
    For each month, reverse any changes that happened after that month.
    """
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    # Generate list of month-end dates
    months = []
    current_month = start_dt.replace(day=1)
    while current_month <= end_dt:
        months.append(current_month.strftime('%Y-%m'))
        current_month += relativedelta(months=1)

    # Start with current constituents
    result = {}

    for month_str in reversed(months):
        month_dt = datetime.strptime(month_str + '-01', '%Y-%m-%d')
        month_end = month_dt + relativedelta(months=1) - relativedelta(days=1)

        # Start with current tickers for this iteration
        if not result:
            # First iteration (most recent month)
            constituents = current_tickers.copy()
        else:
            # Use previous month's result as starting point
            prev_month = (month_dt + relativedelta(months=1)).strftime('%Y-%m')
            constituents = set(result[prev_month])

        # Find changes that happened AFTER this month
        future_changes = changes_df[changes_df['Date'] > month_end]

        # Reverse those changes:
        # - If a ticker was added in the future, remove it now
        # - If a ticker was removed in the future, add it back now
        for _, change in future_changes.iterrows():
            if pd.notna(change['Added.Ticker']) and change['Added.Ticker']:
                constituents.discard(change['Added.Ticker'])
            if pd.notna(change['Removed.Ticker']) and change['Removed.Ticker']:
                constituents.add(change['Removed.Ticker'])

        result[month_str] = sorted(list(constituents))

    # Return in chronological order
    return {k: result[k] for k in sorted(result.keys())}

def main():
    """Main execution function"""
    # Configuration
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    start_date = "2020-01-01"
    end_date = "2025-01-01"

    print("Step 1: Fetching Wikipedia page...")
    html_content = fetch_wikipedia_page(url, headers)
    print(f"✓ Fetched {len(html_content)} characters")

    print("\nStep 2: Parsing current constituents...")
    current_tickers = parse_current_constituents(html_content)
    print(f"✓ Found {len(current_tickers)} current constituents")

    print("\nStep 3: Parsing historical changes...")
    changes_df = parse_changes_table(html_content)
    print(f"✓ Found {len(changes_df)} historical changes")

    print("\nStep 4: Reconstructing historical constituents...")
    monthly_constituents = reconstruct_backwards(
        current_tickers, changes_df, start_date, end_date
    )
    print(f"✓ Reconstructed {len(monthly_constituents)} months")

    print("\nStep 5: Saving output...")
    output_file = "snp500_constituents.json"
    with open(output_file, 'w') as f:
        json.dump(monthly_constituents, f, indent=2)
    print(f"✓ Saved to {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Date range: {start_date} to {end_date}")
    print(f"Total months: {len(monthly_constituents)}")
    print(f"First month: {list(monthly_constituents.keys())[0]} ({len(monthly_constituents[list(monthly_constituents.keys())[0]])} tickers)")
    print(f"Last month: {list(monthly_constituents.keys())[-1]} ({len(monthly_constituents[list(monthly_constituents.keys())[-1]])} tickers)")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    main()
